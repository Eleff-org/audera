"""What a flash installs, read back off the manager that has to load it.

Runs inside the privileged systemd container. The other modules treat provisioning as setup and assert
on what happens next; this one removes the artifacts first and watches `os/dietpi/lib/streamer.sh` put
them back, so its subject is the shell rather than the Python.

The unit state mirroring `dal.sources.DEFAULT_ENABLED` is recorded as an obligation in `AGENTS.md`,
`dal/sources.py` and `os/dietpi/AGENTS.md`. A device that shipped with a `snapserver.conf` naming
AirPlay and `nqptp` left disabled would present as a working streamer with a silent stream, invisibly
on the Sources tab, which reads the enabled set rather than the unit.

The unit files, the mDNS helper, and the `nqptp` drop-in are now rendered by `audera streamer conf`
and redirected into place by `setup.sh`, so the heredoc-quoting failures this module once guarded
(an unquoted heredoc that stopped interpolating, `plexamp.service`'s literal `$(seq 1 30)` expanding
at write time) no longer exist. Byte-equality of every rendered artifact is covered by `tests/cli`;
this module covers what the manager does with the files once they are on disk.

This module covers the artifacts rather than the flash. Not the apt block, the pins, the DietPi repo,
the three-layer `shairport-sync` neutralization, `dietpi.txt`, or the reboot tail; those are still
verified by flashing a device.
"""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from audera.cli import conf
from audera.dal import sources as sources_dal
from audera.domains.sources import CATALOG
from tests.systemd.inside.conftest import (
    WRITTEN_UNITS,
    provision,
    unit_state,
)

# Every test here reprovisions from nothing rather than inheriting the container's state.
pytestmark = pytest.mark.usefixtures('freshly_provisioned')

# Every unit any catalogued source names, in catalog order. Read from `CATALOG` rather than listed,
# so a source whose units provisioning forgets to install fails here the day it lands.
SOURCE_UNITS = tuple(unit for source in CATALOG for unit in source.units)

# The two halves of the unit set, both derived rather than restated. A unit the writer installs and no
# source claims is infrastructure: always enabled, always started. A unit a source claims and the writer
# does not install comes from apt, which today is `nqptp`, bundled in DietPi's `shairport-sync-airplay2`
# package.
INFRASTRUCTURE = tuple(unit for unit in WRITTEN_UNITS if unit not in set(SOURCE_UNITS))
FROM_APT = tuple(unit for unit in SOURCE_UNITS if unit not in set(WRITTEN_UNITS))

# `plexamp-mdns.service`'s ExecStart target, rendered by `render_plexamp_mdns_helper`.
_MDNS_HELPER = '/usr/local/bin/plexamp-mdns.sh'

# Where `nqptp`'s stop budget goes, and the reason it is a drop-in: apt owns the unit.
_NQPTP_DROP_IN = '/etc/systemd/system/nqptp.service.d/timeout.conf'

# Matches the probe budget in this package's `conftest.py`, for the same reason.
_TIMEOUT: float = 15


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    """Runs `systemctl` for the fixture's own bookkeeping, tolerating any exit status.

    `check=False` throughout, because this is called to deprovision: every verb it issues is aimed at a
    unit that may already be stopped, disabled, or gone, each of which exits non-zero while being the
    state the fixture wants.
    """
    return subprocess.run(['systemctl', *args], capture_output=True, text=True, timeout=_TIMEOUT, check=False)


def _deprovision() -> None:
    """Removes every artifact provisioning installs, so its installation is observed rather than assumed.

    Stop precedes disable precedes unlink, and the order must not be changed: `disable` unlinks the wants
    symlink and leaves a running process alone, and unlinking a unit file out from under a running unit
    orphans its process with no unit left to stop it by.

    `nqptp`'s unit file is not removed. It comes from apt on the device and from the image here, so
    removing it would test a state no flash produces; only the drop-in Audera writes goes.
    """
    units = sorted({*WRITTEN_UNITS, *SOURCE_UNITS})
    _systemctl('stop', *units)
    _systemctl('disable', *units)

    for unit in WRITTEN_UNITS:
        Path(f'/etc/systemd/system/{unit}.service').unlink(missing_ok=True)
    Path(_NQPTP_DROP_IN).unlink(missing_ok=True)
    Path(_MDNS_HELPER).unlink(missing_ok=True)

    _systemctl('daemon-reload')
    _systemctl('reset-failed')


@pytest.fixture
def freshly_provisioned(audera_home) -> Iterator[None]:
    """Deprovisions and then reprovisions, so each test reads artifacts this test's flash wrote.

    This module does not use the package's `provisioned` fixture, which re-runs `provision()` over
    whatever the previous test left: a unit file left over from an earlier test would satisfy every
    assertion below without the writer having run.

    Nothing is restored on teardown. Every module in this lane provisions for itself and the driver runs
    each in its own `docker exec`.
    """
    _deprovision()
    provision()

    yield


@pytest.fixture
def recorded_home(audera_home_process) -> str:
    """Points the data-access layer and the provisioning shell at one `~/.audera`, and returns the `HOME`.

    `activate_streamer_units` reads the recorded set by shelling out to `audera streamer units`, a process
    of its own that resolves `~/.audera` from its environment. The `audera_home` fixture monkeypatches a
    module attribute, which reaches this process only, so a test that recorded a set through the
    data-access layer and provisioned would watch the shell read the container's empty home and pass for
    the wrong reason.

    The child-home scaffolding is `conftest.py`'s `audera_home_process`, which creates `home/.audera`
    and points `sources_dal.PATH` at it; only the `HOME` string is taken, since `provision(home=...)`
    passes it into the shell's environment itself.
    """
    home, _ = audera_home_process
    return str(home)


def _fragment_path(unit: str) -> str:
    """Returns the path systemd loaded `unit` from, which names who owns the file rather than who wrote it."""
    return subprocess.run(
        ['systemctl', 'show', unit, '-p', 'FragmentPath', '--value'],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        check=False,
    ).stdout.strip()


@pytest.mark.parametrize('unit', sorted({*WRITTEN_UNITS, *SOURCE_UNITS}))
def test_provisioning_installs_a_unit_systemd_can_load(unit: str):
    """Every unit is installed, parseable, and loaded from the path its owner writes.

    A heredoc that writes a syntactically invalid unit leaves a file on disk and `LoadState=error`, and
    nothing on the device reports it: `activate_streamer_units` enables in batches, so one bad unit takes
    the whole line down and `setup.sh` aborts a flash naming the batch rather than the unit.

    A unit under `/etc/systemd/system/` is Audera's and overrides the packaged one; a unit systemd loads
    from `/usr/lib/` is apt's, and a file Audera wrote there would be replaced by the next upgrade with
    nothing reporting the loss. `FragmentPath` distinguishes the two.
    """
    state = unit_state(unit)
    assert state['LoadState'] == 'loaded', f'{unit} did not load: {state}'

    fragment = _fragment_path(unit)
    if unit in FROM_APT:
        assert not fragment.startswith('/etc/systemd/system/'), f'Audera wrote a unit apt owns, at {fragment}'
    else:
        assert fragment == f'/etc/systemd/system/{unit}.service'


@pytest.mark.parametrize('unit', INFRASTRUCTURE)
def test_infrastructure_is_enabled_and_running(unit: str):
    """Infrastructure units are both enabled and started, unconditionally.

    Derived from the renderers rather than listed, so the set is whatever provisioning installs and no
    source claims, the definition `os/dietpi/AGENTS.md` uses. A unit added to `conf.STREAMER_UNITS` for
    a source without being added to `CATALOG` therefore lands here and is asserted running, which a
    source unit is not.
    """
    state = unit_state(unit)
    assert state['UnitFileState'] == 'enabled', f'{unit} was not enabled: {state}'
    assert state['ActiveState'] == 'active', f'{unit} was not started: {state}'


@pytest.mark.parametrize('source', [source for source in CATALOG if source.units], ids=lambda source: source.id)
def test_the_provisioned_unit_state_mirrors_default_enabled(source):
    """With nothing recorded, the provisioned unit state mirrors `dal.sources.DEFAULT_ENABLED`.

    `DEFAULT_ENABLED` is the enabled set a device with no `sources.json` behaves as, and provisioning has
    to put systemd in the state that set implies: enabled and started for a source in it, installed and
    explicitly disabled for one out of it. `activate_streamer_units` names no source, so this is the
    bootstrap default reaching systemd through `audera streamer units`, the same fallback `get_enabled()`
    hands the conf.

    Both directions of a break are silent. A source in the enabled set whose units are left disabled
    ships a `snapserver.conf` naming a stream no backend feeds, and the Sources tab reports it enabled
    because it reads the enabled set rather than the unit. A source out of the set whose units are left
    running ships a backend competing for a port with nothing in the conf naming it.

    Parameterized over the sources that have units. Spotify has none by design, since Snapserver forks
    and reaps its backend; `test_index.py` covers that path at the fork.
    """
    enabled = source.id in sources_dal.DEFAULT_ENABLED

    for unit in source.units:
        state = unit_state(unit)
        assert state['UnitFileState'] == ('enabled' if enabled else 'disabled'), (
            f'{unit} does not mirror DEFAULT_ENABLED={sources_dal.DEFAULT_ENABLED}: {state}'
        )
        assert state['ActiveState'] == ('active' if enabled else 'inactive'), (
            f'{unit} is not in the state DEFAULT_ENABLED={sources_dal.DEFAULT_ENABLED} implies: {state}'
        )


def test_provisioning_follows_a_recorded_enabled_set(recorded_home):
    """A reprovision leaves the operator's recorded sources running, rather than the bootstrap default.

    `~/.audera/sources.json` survives a flash, since `setup.sh` writes `/etc`, `/var/lib` and unit files
    only, so a reprovision that rendered `DEFAULT_ENABLED` would strand a device whose operator runs
    PlexAmp: the conf would name AirPlay, Snapserver would reassign every group to it at the first client
    connect, the Sources tab would go on reporting PlexAmp enabled, and `plexamp` would be disabled,
    which the claim probe reads as a device that needs claiming again.

    The conf and the unit state are asserted together, since either alone is still a broken device: a
    stream whose backend is disabled plays nothing, and a running backend no conf names is a process no
    stream reads.

    AirPlay is asserted off in the same pass, because `nqptp` is what a fresh flash leaves enabled and a
    provisioning step that only ever added would pass on the enabled half while leaving the previous
    image's sources running.
    """
    assert sources_dal.adopt(['PlexAmp']) is True

    provision(home=recorded_home)

    assert 'name=PlexAmp' in Path(conf.SNAPSERVER_CONF).read_text(encoding='utf-8')
    assert 'name=AirPlay' not in Path(conf.SNAPSERVER_CONF).read_text(encoding='utf-8')

    for unit in ('plexamp', 'plexamp-mdns'):
        state = unit_state(unit)
        assert state['UnitFileState'] == 'enabled', f'{unit} did not follow the recorded set: {state}'
        assert state['ActiveState'] == 'active', f'{unit} did not follow the recorded set: {state}'

    state = unit_state('nqptp')
    assert state['UnitFileState'] == 'disabled', f'nqptp outlived the recorded set: {state}'
    assert state['ActiveState'] == 'inactive', f'nqptp outlived the recorded set: {state}'


def test_provisioning_seeds_no_enabled_set():
    """Provisioning records no enabled set, so `sources.json` is still absent afterwards.

    `setup.sh` writes `/etc/*`, `/var/lib/*` and unit files only. With no file to seed, `get_enabled()`
    degrades to `DEFAULT_ENABLED`, the same constant the conf was rendered from and the units were moved
    to match.

    Seeding the file would break `index.adopt_running_sources`, which tells an unrecorded device from one
    whose operator chose exactly `DEFAULT_ENABLED` by the file's absence alone.
    """
    assert sources_dal.is_recorded() is False, 'provisioning wrote an enabled set, so adoption can no longer tell'
    assert sources_dal.get_enabled() == list(sources_dal.DEFAULT_ENABLED)


def test_the_mdns_helper_the_unit_names_is_installed_and_executable():
    """`plexamp-mdns.service`'s `ExecStart` target is installed and executable.

    The helper is rendered by `render_plexamp_mdns_helper` alongside the units because
    `index._enable_source(PlexAmp)` runs `enable --now plexamp-mdns`, and a host carrying the unit but not
    its `ExecStart` target fails that step: the unit starts, `/usr/local/bin/plexamp-mdns.sh` is not there,
    systemd reports `status=203/EXEC`, and `plexamp.local` is never published.

    The path is read out of the unit rather than restated, since a helper installed somewhere the unit does
    not name fails the same way as no helper at all.
    """
    exec_start = unit_state('plexamp-mdns')['ExecStart']
    assert _MDNS_HELPER in exec_start, f'the unit names a different helper: {exec_start}'

    assert Path(_MDNS_HELPER).is_file()
    assert os.access(_MDNS_HELPER, os.X_OK), 'the helper is not executable, so the unit fails with 203/EXEC'


def test_nqptps_stop_budget_is_a_drop_in_apt_cannot_replace():
    """`nqptp`'s stop budget is installed as a drop-in, because apt owns the unit file.

    `nqptp` needs the same stop budget as the units Audera writes: toggling AirPlay off is
    `systemctl disable --now nqptp` through the seam, so it is the one unit whose stop an operator triggers
    directly. Its unit file belongs to DietPi's `shairport-sync-airplay2` package, and apt replaces the
    files it owns, so a budget written into the unit would be lost at the next upgrade.

    Both halves are asserted: the drop-in is where provisioning writes it, and there is no
    `/etc/systemd/system/nqptp.service` beside it. `test_index.py` asserts the value systemd ends up with;
    this asserts the file it comes from.
    """
    assert Path(_NQPTP_DROP_IN).is_file()
    assert not Path('/etc/systemd/system/nqptp.service').exists(), 'Audera wrote a unit file apt will replace'

    state = unit_state('nqptp')
    assert _NQPTP_DROP_IN in state['DropInPaths'], f'systemd did not merge the drop-in: {state}'
