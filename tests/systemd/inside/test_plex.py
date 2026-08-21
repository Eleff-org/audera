"""PlexAmp's claim flow, against the manager whose answers it is built on.

Runs inside the privileged systemd container. `tests/ui/test_streamer.py` covers the same module with
`_plexamp_state` replaced wholesale, so it pins which panel each rung of the ladder renders rather than
whether the rungs exist.

Two assumptions are only checkable here. `_active_seconds()` subtracts systemd's
`ActiveEnterTimestampMonotonic` from `time.monotonic()` on the basis that both are `CLOCK_MONOTONIC`,
and `_restart_plexamp_with_claim` writes a drop-in, reloads, and starts on the basis that the reload is
what makes the drop-in count. Off a real manager the reload is indistinguishable from a no-op.

`STARTUP_GRACE` is patched in exactly one test, the one where its expiry is the assertion. Every other
rung is produced the way a device produces it, by a stub that binds its port late reached through a
drop-in, so the window is real wall-clock. `_active_seconds` is never patched.
"""

import stat
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from audera.services import system
from audera.ui.streamer.pages import _plex
from tests.systemd.inside.conftest import unit_state

# Every test here provisions. `plexamp.service` is written by `write_streamer_units`, and the image
# ships no Audera unit file.
pytestmark = pytest.mark.usefixtures('provisioned')

# The unit file provisioning writes, unlinked by one test to produce the unknown-unit reading.
_PLEXAMP_UNIT = '/etc/systemd/system/plexamp.service'

# A second drop-in beside the one `_plex` owns, for the tests that configure the stub rather than claim
# it. Kept separate so a test can drive `_restart_plexamp_with_claim` for the claim and still have set
# the stub up itself; systemd merges the two.
_STUB_CONF = Path('/etc/systemd/system/plexamp.service.d/stub.conf')

# How long the stub waits before binding :32500, which is how long a claimed PlexAmp reads `starting`.
# Long enough that the rung is unambiguous rather than a race against the poll below, short enough to
# cost one test six seconds.
_STUB_DELAY: float = 6

# Recognisable in a `/proc/<pid>/environ` dump, and not a value any real claim would take.
_CLAIM_TOKEN = 'audera-test-claim-token'

# The ladder's slowest rung is `_STUB_DELAY` plus a restart, so this only has to clear that with room
# for a slow container. Nothing asserts it as a budget: a rung that never arrives fails on the state.
_LADDER_TIMEOUT: float = 30


@pytest.fixture(autouse=True)
def pristine_plexamp(provisioned) -> Iterator[None]:
    """Leaves `plexamp` enabled, stopped and never claimed, the state a claim is submitted from.

    Requesting `provisioned` rather than relying on the module's `pytestmark` orders the two: an autouse
    fixture is instantiated before a `usefixtures` one at the same scope, so without the dependency this
    would run first and `provision()`'s own `daemon-reload` would land after it.

    The `enable` is load-bearing. A stopped disabled unit is garbage-collected, so systemd loads it
    fresh on the next reference and a drop-in written while it is unloaded takes effect with no reload.
    Provisioning leaves PlexAmp disabled, since it is not in `DEFAULT_ENABLED`, so a fixture that only
    stopped the unit would make `_restart_plexamp_with_claim`'s `daemon-reload` redundant; measured with
    `enable` omitted, deleting that reload from `_plex` leaves this module green. An enabled unit is
    referenced by `multi-user.target` and stays loaded across a stop, which is the device's state.

    Two other pieces of state would otherwise read as a claim this test did not make. The drop-ins,
    because `provision()` rewrites the unit but knows nothing of `plexamp.service.d`, so a previous
    test's claim token would still be on disk and still merged. And `failed`, because the claimed stub is
    `socat` and exits non-zero on the `SIGINT` the unit's `KillSignal` sends, so every test that reaches
    `claimed` leaves the unit failed on the way out.

    The `stop` and the `reset-failed` are redundant today, since `provision()` runs
    `activate_streamer_units`, whose `disable` drops the unit and its activation timestamp with it. They
    are kept so this module does not depend on provisioning continuing to leave PlexAmp disabled.
    """
    for path in (_STUB_CONF, Path(_plex.PLEXAMP_CLAIM_CONF)):
        path.unlink(missing_ok=True)
    system.systemctl('enable', 'plexamp')
    system.systemctl('daemon-reload', check=False)
    system.systemctl('stop', 'plexamp', check=False)
    system.systemctl('reset-failed', 'plexamp', check=False)

    # `UnitFileState` rather than `LoadState`: `systemctl show` loads the unit in order to answer, so
    #   `LoadState` reads `loaded` for any unit whose file exists.
    assert unit_state('plexamp')['UnitFileState'] == 'enabled', 'the reload under test would be moot against a dropped unit'

    yield

    system.systemctl('stop', 'plexamp', check=False)
    system.systemctl('reset-failed', 'plexamp', check=False)


def _environ(pid: int) -> dict[str, str]:
    """Returns the environment the process at `pid` was started with.

    Read from `/proc` rather than from `systemctl show -p Environment`, which reports what systemd would
    pass. The two disagree on the case `_remove_claim_override` creates, where the drop-in is gone from
    the unit while the running process still holds the token it was started with.
    """
    raw = Path(f'/proc/{pid}/environ').read_bytes().decode(errors='replace')
    return dict(entry.split('=', 1) for entry in raw.split('\0') if '=' in entry)


def _main_pid() -> int:
    """Returns `plexamp`'s `MainPID`, or `0` when it is not running."""
    value = unit_state('plexamp')['MainPID']
    return int(value) if value.isdigit() else 0


def _configure_stub(**environment: object) -> None:
    """Writes `_STUB_CONF` with `environment` and reloads, so the next start picks it up.

    A drop-in rather than the unit or the container's environment, which makes the `starting` rung
    reachable without patching `STARTUP_GRACE`.
    """
    lines = ''.join(f'Environment={key}={value}\n' for key, value in environment.items())
    _STUB_CONF.parent.mkdir(parents=True, exist_ok=True)
    _STUB_CONF.write_text(f'[Service]\n{lines}', encoding='utf-8')
    system.systemctl('daemon-reload')


def _await_state(expected: str, timeout: float = _LADDER_TIMEOUT) -> str:
    """Polls `_plexamp_state` until it reports `expected`, and returns whatever it last read.

    Returns rather than raises, so a rung that never arrives fails on the caller's own assertion and
    names what it stopped at rather than a bare timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = _plex._plexamp_state()
        if state == expected or time.monotonic() >= deadline:
            return state
        time.sleep(0.1)


def test_the_startup_window_is_measured_against_the_same_clock_python_reads():
    """`ActiveEnterTimestampMonotonic` and `time.monotonic()` share an epoch and a rate.

    Both are `CLOCK_MONOTONIC` on Linux, so they subtract directly. Were systemd's field
    `CLOCK_BOOTTIME`, or microseconds since some other origin, the subtraction would still return a
    number and `STARTUP_GRACE` would compare against garbage.

    The offset is pinned by bracketing the reading between two `time.monotonic()` samples taken around
    the start. The rate is pinned separately because an epoch that agrees at one instant and then drifts
    is indistinguishable from a correct one in a single reading: a field in milliseconds would pass the
    first assertion on a container up for under a fortnight.
    """
    started = time.monotonic()
    system.systemctl('start', 'plexamp')
    elapsed = _plex._active_seconds()
    ceiling = time.monotonic() - started

    assert elapsed is not None, f'systemd reported no activation for a running unit: {unit_state("plexamp")}'
    assert 0 <= elapsed <= ceiling, f'{elapsed}s active, but only {ceiling}s passed here'

    time.sleep(1)
    advanced = _plex._active_seconds()
    assert advanced is not None and advanced - elapsed == pytest.approx(1, abs=0.5)


@pytest.mark.parametrize('withhold', ['never-activated', 'not-found'])
def test_the_window_is_withheld_when_systemd_has_no_activation_to_report(withhold: str):
    """`None` rather than a number, for the two readings that carry no timestamp.

    `systemctl show` answers `0` for both on exit 0, so neither presents as an error the call could
    catch. `_active_seconds` has to recognise the zero: read as a timestamp it would place the
    activation at the machine's boot and put every PlexAmp permanently outside the startup window.

    Both are states a device reaches. `never-activated` is a provisioned PlexAmp the operator has
    enabled but that has not come up yet; `not-found` is a streamer flashed before PlexAmp was
    provisioned. A stopped unit is neither; see the next test.
    """
    if withhold == 'not-found':
        Path(_PLEXAMP_UNIT).unlink()
        system.systemctl('daemon-reload')

    assert unit_state('plexamp')['LoadState'] == ('loaded' if withhold == 'never-activated' else 'not-found')
    assert _plex._active_seconds() is None
    assert _plex._plexamp_state() == 'inactive'
    assert _plex.setup_state() == _plex.SETUP_REQUIRED
    assert _plex.setup_complete() is False


@pytest.mark.parametrize('exit_status', ['clean', 'failed'])
def test_a_stopped_plexamp_reports_inactive_despite_a_retained_window(exit_status: str):
    """systemd keeps a stopped unit's activation timestamp, so `is_active` has to be consulted first.

    systemd retains `ActiveEnterTimestampMonotonic` across a stop for as long as the unit stays loaded,
    and it reads `0` only once the unit is dropped. An enabled unit is referenced by
    `multi-user.target` and never dropped, so on a device with the PlexAmp source enabled the reading
    survives every stop.

    A PlexAmp that stopped seconds ago therefore still answers the startup window with a small number,
    and `_plexamp_state` reading that number would report `starting` over a unit that is not running.
    This pins that `is_active` is consulted first.

    Parameterized over both exit statuses, since neither escapes the retention. `clean` is the unclaimed
    stub, which traps the signal and exits 0, leaving the unit `inactive`; `failed` is the claimed stub,
    which is `socat` and exits non-zero on the `SIGINT` `plexamp.service` sends, leaving it `failed`.
    `is_active` answers False for both, so both must report `inactive`.
    """
    if exit_status == 'failed':
        _configure_stub(PLEXAMP_CLAIM_TOKEN=_CLAIM_TOKEN)
    system.systemctl('start', 'plexamp')
    assert _await_state('claimed' if exit_status == 'failed' else 'starting') != 'inactive'

    system.systemctl('stop', 'plexamp', check=False)

    assert unit_state('plexamp')['ActiveState'] == ('failed' if exit_status == 'failed' else 'inactive')
    retained = _plex._active_seconds()
    assert retained is not None, 'the timestamp was dropped, so the stale window this test is about is absent'
    assert retained < _plex.STARTUP_GRACE, 'the retained timestamp is already outside the window'
    assert _plex._plexamp_state() == 'inactive'
    assert _plex.setup_state() == _plex.SETUP_REQUIRED
    assert _plex.setup_complete() is False


def test_the_ladder_walks_from_inactive_through_starting_to_claimed():
    """`inactive`, `starting` and `claimed`, in one pass and in real time.

    systemd calls a `Type=simple` unit active the moment it forks, so there is a window in which the
    unit is up, the port is closed, and the device is claimed; a closed port is also the only evidence
    `_plexamp_state` has of an unclaimed device. Elapsed time separates the two, which is why
    `STARTUP_GRACE` is not patched here and the window comes from a stub that binds late.

    The claim goes through `_restart_plexamp_with_claim` rather than being staged, so the rung change is
    caused by the production path. It writes its own drop-in beside the one `_configure_stub` left, and
    systemd merges them, so the delay survives the claim.

    `setup_state()` and `setup_complete()` are asserted at each rung rather than only at the end, since
    they are what the Sources tab renders.
    """
    assert _plex._plexamp_state() == 'inactive'
    assert _plex.setup_state() == _plex.SETUP_REQUIRED
    assert _plex.setup_complete() is False

    _configure_stub(PLEXAMP_STUB_DELAY=_STUB_DELAY)
    _plex._restart_plexamp_with_claim(_CLAIM_TOKEN)

    assert _plex._plexamp_state() == 'starting', f'the stub bound its port too early: {unit_state("plexamp")}'
    assert _plex.setup_state() == _plex.STARTING
    assert _plex.setup_complete() is False

    assert _await_state('claimed') == 'claimed'
    assert _plex.setup_state() is None
    assert _plex.setup_complete() is True


def test_an_expired_startup_window_reports_unclaimed():
    """An expired `STARTUP_GRACE` moves an unclaimed PlexAmp from `starting` to `unclaimed`.

    The one test that patches `STARTUP_GRACE`. Ninety seconds is the real value, generous because
    `plexamp.service`'s `ExecStartPre` alone waits up to sixty for `plex.tv` to resolve, so waiting it
    out would cost a minute and a half. The stub is left unclaimed and never binds.

    Nothing changes between the two readings except how long the unit has been up, so elapsed time is
    the discriminator rather than a second cause.
    """
    system.systemctl('start', 'plexamp')
    assert _plex._plexamp_state() == 'starting'
    assert _plex.setup_state() == _plex.STARTING

    grace = 1.0
    while (_plex._active_seconds() or 0) < grace:
        time.sleep(0.1)

    original = _plex.STARTUP_GRACE
    try:
        _plex.STARTUP_GRACE = grace
        assert _plex._plexamp_state() == 'unclaimed'
        assert _plex.setup_state() == _plex.SETUP_REQUIRED
        assert _plex.setup_complete() is False
    finally:
        _plex.STARTUP_GRACE = original

    assert unit_state('plexamp')['ActiveState'] == 'active', 'the unit stopped, so this asserted `inactive`'


def test_the_claim_token_reaches_the_process_environment():
    """The claim token reaches `/proc/<MainPID>/environ`, which is where PlexAmp consumes it.

    A test that asserted on `PLEXAMP_CLAIM_CONF`'s contents would pass against a
    `_restart_plexamp_with_claim` that never reloaded or never restarted, both of which leave the running
    PlexAmp unclaimed.

    Three layers are asserted because each can be right while the next is wrong: the file systemd will
    read, the configuration systemd has parsed, and the environment the process holds. The port opening
    is the fourth.
    """
    _plex._restart_plexamp_with_claim(_CLAIM_TOKEN)

    assert Path(_plex.PLEXAMP_CLAIM_CONF).read_text(encoding='utf-8') == (
        f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={_CLAIM_TOKEN}\n'
    )
    # `/etc/systemd/system` is world-readable and the token is a plex.tv credential, so the file is
    # written `0o600`. Asserted here rather than on the host, where a `chmod` means the read-only bit.
    assert stat.S_IMODE(Path(_plex.PLEXAMP_CLAIM_CONF).stat().st_mode) == 0o600
    state = unit_state('plexamp')
    assert _plex.PLEXAMP_CLAIM_CONF in state['DropInPaths']
    assert f'PLEXAMP_CLAIM_TOKEN={_CLAIM_TOKEN}' in state['Environment']

    pid = _main_pid()
    assert pid, f'the unit is not running, so nothing holds the token: {state}'
    assert _environ(pid).get('PLEXAMP_CLAIM_TOKEN') == _CLAIM_TOKEN
    assert _await_state('claimed') == 'claimed'


def test_the_claim_drop_in_is_inert_until_daemon_reload():
    """Without `daemon-reload`, a restart leaves the token absent from the process.

    systemd parses a unit once and caches it, so a drop-in written beside a loaded unit is on disk and
    has no effect: `systemctl restart` starts the process from the configuration systemd already holds,
    and the only observable difference is a warning on stderr that nothing reads.

    The reload is load-bearing only against a unit systemd still holds parsed. `pristine_plexamp` makes
    that precondition true, and its docstring records the state in which the reload is redundant.
    """
    system.systemctl('start', 'plexamp')
    Path(_plex.PLEXAMP_CLAIM_CONF).parent.mkdir(parents=True, exist_ok=True)
    Path(_plex.PLEXAMP_CLAIM_CONF).write_text(f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={_CLAIM_TOKEN}\n', encoding='utf-8')

    system.systemctl('restart', 'plexamp')

    assert 'PLEXAMP_CLAIM_TOKEN' not in unit_state('plexamp')['Environment']
    assert 'PLEXAMP_CLAIM_TOKEN' not in _environ(_main_pid())
    assert _plex._plexamp_state() == 'starting', 'the stub bound its port without a token'

    system.systemctl('daemon-reload')
    system.systemctl('restart', 'plexamp')

    assert f'PLEXAMP_CLAIM_TOKEN={_CLAIM_TOKEN}' in unit_state('plexamp')['Environment']
    assert _environ(_main_pid()).get('PLEXAMP_CLAIM_TOKEN') == _CLAIM_TOKEN
    assert _await_state('claimed') == 'claimed'


def test_removing_the_claim_override_leaves_the_running_process_claimed():
    """`_remove_claim_override` clears the drop-in without disturbing the claimed process.

    This is why `setup_complete` is not a file check: the drop-in is deleted on success and on timeout
    alike, so its absence is the steady state for both "claimed" and "never claimed", and a predicate
    over `PLEXAMP_CLAIM_CONF` would report every claimed device as `setup required` forever.

    The deletion does not reach the process. `_remove_claim_override` removes the file and reloads, so
    systemd stops carrying the token, while the running PlexAmp was started with it and has already
    exchanged it with plex.tv. `MainPID` is asserted unchanged for that reason: the token surviving in a
    restarted process would be a weaker claim.

    The token is not asserted absent from disk beyond the file being gone; where it ends up on a real
    device is Plex's business, and the stub models none of it.
    """
    _plex._restart_plexamp_with_claim(_CLAIM_TOKEN)
    assert _await_state('claimed') == 'claimed'
    pid = _main_pid()

    _plex._remove_claim_override()

    assert not Path(_plex.PLEXAMP_CLAIM_CONF).exists()
    assert 'PLEXAMP_CLAIM_TOKEN' not in unit_state('plexamp')['Environment']
    assert _main_pid() == pid, 'the unit restarted, so this asserts nothing about the claimed process'
    assert _environ(pid).get('PLEXAMP_CLAIM_TOKEN') == _CLAIM_TOKEN
    assert _plex._plexamp_state() == 'claimed'
    assert _plex.setup_state() is None
    assert _plex.setup_complete() is True
