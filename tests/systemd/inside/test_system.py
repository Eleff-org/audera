"""What the systemd seam's arguments produce, read off the real manager.

Runs inside the privileged systemd container, and it is the only coverage `audera.services.system`
has. The seam's whole purpose is effect, so a test that patched `subprocess.run` and compared the
argv would assert the seam calls itself the way it calls itself; `tests/services/test_platform.py`
keeps the one claim that needs no manager, the `@platform.requires('dietpi')` gate that stops any of
this running on a developer's machine.

The effects: that `start` and `stop` move the unit's state and reap its process, that `is_active`
answers False for the two failure shapes systemd exits non-zero for, that a failed unit's reason is
logged rather than swallowed, and that `daemon-reload` is what makes a drop-in take effect.

The units are the container's own stubs from `/usr/lib/systemd/system/` rather than anything
provisioning writes, which keeps this module independent of the order the driver runs the others in:
the container is session-scoped and provisioning leaves units enabled behind it.
"""

import subprocess
from pathlib import Path

import pytest

from audera.services import system
from tests.systemd.inside.conftest import await_no_new_zombies, await_pids, still_alive, unit_state, zombies_for

# Handles SIGTERM and exits 0, so `stop` completes through the ordinary path rather than through
# systemd's SIGKILL escalation. The wedged case is `stubborn-stub.sh`'s, asserted where the stop
# timeout is.
IDLE_UNIT = 'avahi-daemon'

# `Type=oneshot`, `ExecStart=/bin/false`, `Restart=no`, so it settles in `failed` and stays there. The
# seam's `CalledProcessError` path is driven by systemd refusing the job on its own terms rather than
# by a stub raising on command.
FAILING_UNIT = 'audera-test-failing'

UNIT_DIR = Path('/etc/systemd/system')


@pytest.fixture
def idle_unit():
    """Yields `IDLE_UNIT` inactive, and leaves it inactive.

    Normalised before the test as well as after it. `plexamp-mdns.service` declares
    `Requires=avahi-daemon.service`, so another module in this container may have started it, and
    `start` against an already-active unit is a no-op that would make the state assertions vacuous.
    """
    subprocess.run(['systemctl', 'stop', IDLE_UNIT], capture_output=True, timeout=15, check=False)
    subprocess.run(['systemctl', 'reset-failed', IDLE_UNIT], capture_output=True, timeout=15, check=False)

    yield IDLE_UNIT

    subprocess.run(['systemctl', 'stop', IDLE_UNIT], capture_output=True, timeout=15, check=False)
    subprocess.run(['systemctl', 'reset-failed', IDLE_UNIT], capture_output=True, timeout=15, check=False)


@pytest.fixture
def failing_unit():
    """Yields `FAILING_UNIT`, and clears its failed state afterwards.

    A unit left `failed` keeps the manager `degraded`, and `tests/systemd/inside/test_platform.py`
    accepts `degraded` only because `systemd-modules-load` cannot load modules in a container. Leaving
    more failures behind would make that allowance cover this module's litter too.
    """
    yield FAILING_UNIT

    subprocess.run(['systemctl', 'reset-failed', FAILING_UNIT], capture_output=True, timeout=15, check=False)


def test_start_and_stop_move_the_units_state(idle_unit):
    """`start` and `stop` move the unit through the manager's own state.

    `ActiveState`, `SubState` and `MainPID` together, because each alone is satisfiable without the
    others: a unit can be `active` with no process if its type is wrong, and a live pid says nothing
    about what the manager believes it is supervising.
    """
    assert unit_state(idle_unit)['ActiveState'] == 'inactive'
    assert unit_state(idle_unit)['MainPID'] == '0'

    system.systemctl('start', idle_unit)

    started = unit_state(idle_unit)
    assert started['ActiveState'] == 'active'
    assert started['SubState'] == 'running'
    assert int(started['MainPID']) > 0

    system.systemctl('stop', idle_unit)

    stopped = unit_state(idle_unit)
    assert stopped['ActiveState'] == 'inactive'
    assert stopped['SubState'] == 'dead'
    assert stopped['MainPID'] == '0'


def test_stop_leaves_no_process_and_no_zombie(idle_unit):
    """`stop` clears the process table as well as the manager's `MainPID` bookkeeping.

    The two can disagree: systemd forgets a unit it could not stop, and the backend keeps running under
    pid 1 with nothing naming it. The assertion is therefore on the pids the unit's command line
    matched, re-read after the stop.

    The snapshot is taken with `await_pids` rather than `pids_for`, since `start` returns once systemd
    has forked and the command line is not readable yet. The stop side is not polled, because `stop`
    waits for the process to die and a retry there would paper over the leak this asserts.

    Zombies are snapshotted rather than filtered because `comm` is capped at fifteen characters and a
    defunct process has no command line left; the difference from a snapshot cannot be truncated away.
    """
    system.systemctl('start', idle_unit)

    before = await_pids('/usr/local/bin/avahi-publish')
    zombies_before = zombies_for()
    assert before, 'the unit reported active but no process matched its ExecStart'
    assert int(unit_state(idle_unit)['MainPID']) in before

    system.systemctl('stop', idle_unit)

    assert still_alive(before) == {}
    assert await_no_new_zombies(zombies_before) == []


def test_is_active_is_false_for_an_unknown_unit():
    """`systemctl is-active` exits 4 for a unit that does not exist.

    Four rather than the three a stopped unit exits, and `is_active` must not distinguish them.
    `_plexamp_state` and the Sources tab both read this as "not running", and an unknown unit is a
    provisioning fault that surfaces where the unit is written. Pinned against the real manager because
    the exit status is systemd's.
    """
    result = subprocess.run(
        ['systemctl', 'is-active', 'audera-no-such-unit'], capture_output=True, text=True, timeout=15, check=False
    )
    assert result.returncode == 4
    assert system.is_active('audera-no-such-unit') is False


def test_is_active_is_false_for_a_genuinely_failed_unit(failing_unit):
    """The `failed` branch, produced by systemd rather than fed in as a string.

    `is_active` reads `failed` as False, and a test that patched `systemctl is-active` to print it
    would pin the comparison rather than that systemd emits that word for this state. Here the unit
    really fails and the string comes from the manager.
    """
    with pytest.raises(subprocess.CalledProcessError):
        system.systemctl('start', failing_unit)

    assert unit_state(failing_unit)['ActiveState'] == 'failed'
    assert system.is_active(failing_unit) is False


def test_a_failed_unit_logs_systemds_own_reason(failing_unit, caplog):
    """Output is captured, so the reason reaches the log only if the seam writes it there.

    `CalledProcessError.__str__` carries the argv and the exit status and never `stderr`, so a caller
    that renders the exception shows "returned non-zero exit status 1" and no cause. What the seam logs
    has to be systemd's own line, including the `journalctl -xeu` pointer.
    """
    with caplog.at_level('ERROR'), pytest.raises(subprocess.CalledProcessError):
        system.systemctl('start', failing_unit)

    assert f'systemctl start {failing_unit}' in caplog.text
    assert f'{failing_unit}.service' in caplog.text
    assert 'journalctl -xeu' in caplog.text


def test_check_false_returns_the_returncode_and_stdout_contract(failing_unit):
    """The contract `services/ap.py` is slated to migrate onto, against a real non-zero exit.

    `ap.py` still shells out to `systemctl` itself and branches on `returncode`, so it needs a status it
    can read and output it can parse, from a call that did not raise.
    """
    with pytest.raises(subprocess.CalledProcessError):
        system.systemctl('start', failing_unit)

    result = system.systemctl('is-active', failing_unit, check=False)
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode != 0
    assert result.stdout.strip() == 'failed'


def test_a_drop_in_is_inert_until_daemon_reload(idle_unit):
    """A drop-in has no effect until `daemon-reload`.

    Every writer in Audera (`write_streamer_units`, `_restart_plexamp_with_claim`,
    `_remove_claim_override`) writes a file and then reloads, and off a real manager that reload is
    indistinguishable from a no-op. Here dropping it has a consequence: the drop-in is on disk, systemd's answer for the property
    it sets is unchanged, and only the reload moves it.

    The unit has to be running for the reload to be observable. Systemd garbage-collects an inactive
    unit nothing references, so it reloads from disk the next time anything asks about it, and a drop-in
    written against a stopped unit appears to take effect with no reload at all. An active unit is
    pinned in memory, which is the state every writer in Audera targets: `plexamp` is running when the
    claim drop-in is written, and the streamer units are running when provisioning rewrites them.

    `TimeoutStopSec` is the property under the drop-in because it is the one the timeout fix uses, and
    the manager's default for it is a value nothing else in this container sets.
    """
    drop_in_dir = UNIT_DIR / f'{idle_unit}.service.d'
    drop_in = drop_in_dir / 'timeout.conf'
    try:
        system.systemctl('start', idle_unit)
        assert unit_state(idle_unit)['ActiveState'] == 'active'
        before = unit_state(idle_unit)['TimeoutStopUSec']
        assert before != '3s', 'the drop-in would be indistinguishable from the default'

        drop_in_dir.mkdir(parents=True, exist_ok=True)
        drop_in.write_text('[Service]\nTimeoutStopSec=3\n')

        assert unit_state(idle_unit)['TimeoutStopUSec'] == before
        assert str(drop_in) not in unit_state(idle_unit)['DropInPaths']

        system.systemctl('daemon-reload')

        assert unit_state(idle_unit)['TimeoutStopUSec'] == '3s'
        assert str(drop_in) in unit_state(idle_unit)['DropInPaths']
    finally:
        # `test_platform.py` asserts this directory is empty of Audera units. A drop-in left here would
        # not break that assertion, which globs `*.service`, but it would change the stop timeout for
        # every module the driver runs after this one.
        drop_in.unlink(missing_ok=True)
        if drop_in_dir.is_dir():
            drop_in_dir.rmdir()
        system.systemctl('daemon-reload')
