"""Probes and fixtures for the in-container modules.

Runs inside the privileged systemd container the package's `conftest.py` boots.

Every probe here observes the host through `subprocess.run` rather than through
`audera.services.system`, which is the seam these modules test: a `systemctl` that silently no-ops
would leave every assertion reading the same nothing it wrote. `stream_status` reads Snapserver over
its own client, so an assertion is about the streams the server is serving rather than the streams
the UI believes it is serving.

Leak probes read `systemctl` and `ps`, never `/sys/fs/cgroup`. Docker Desktop on WSL2 is cgroup v1
and GitHub-hosted runners are v2, so every path under `/sys/fs/cgroup` differs between the two.
`TasksCurrent` is unused for the same reason: it depends on the pids controller being delegated,
which is not guaranteed identically across them.
"""

import contextlib
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

import audera
from audera.cli import conf
from audera.clients import SnapserverClient
from audera.dal import sources as sources_dal
from audera.models.player import Group, Player
from audera.ui.streamer import commands
from audera.ui.streamer.pages import index
from audera.ui.streamer.pages._clients import _load_settings

# The properties `unit_state` reads, as one `systemctl show` call. Named explicitly rather than
# taking the full property dump, which is around two hundred lines per unit.
_PROPERTIES = (
    'LoadState',
    'ActiveState',
    'SubState',
    # Why a unit failed, which `ActiveState` and `SubState` both render as a bare `failed`. It is the
    # only property that distinguishes a unit systemd refused to start from one whose `ExecStart`
    # exited non-zero, and `test_index.py`'s start-limit tests depend on that distinction:
    # `start-limit-hit` says the rate limit rather than the stub produced the state.
    'Result',
    'MainPID',
    'UnitFileState',
    'TimeoutStopUSec',
    'DropInPaths',
    'ActiveEnterTimestampMonotonic',
    'Environment',
    'ExecStart',
    # The start rate limit `toggle.apply`'s `reset-failed` clears. Read per-unit even when a unit
    # states neither, because `systemctl show` resolves the inherited default into the unit's own
    # answer, which is the value that decides whether a toggle is refused.
    'StartLimitBurst',
    'StartLimitIntervalUSec',
)

# Long enough that a hung probe fails the test rather than the session, short enough that it fails
# before the driver's own `docker exec` gives up.
_TIMEOUT: float = 15

# The four values `os/dietpi/streamer/automation/setup.sh` passes `write_streamer_units`, and the
# two directories it creates before calling it. Restated here because nothing else in this image sets
# them, and asserted against the script itself by `tests/systemd/inside/test_provisioning.py`.
#
# `COMMON_SH` and `STREAMER_SH` are public because the modules read the files too.
COMMON_SH = '/app/os/dietpi/lib/common.sh'
STREAMER_SH = '/app/os/dietpi/lib/streamer.sh'
SNAPSERVER_HOME = '/var/lib/snapserver'
GO_LIBRESPOT_CONFIG_DIR = f'{SNAPSERVER_HOME}/.config/go-librespot'
CAMILLADSP_CONFIG_DIR = '/etc/camilladsp'
CAMILLADSP_CONFIG = f'{CAMILLADSP_CONFIG_DIR}/config.yml'
CAMILLADSP_STATEFILE = f'{CAMILLADSP_CONFIG_DIR}/state.yml'

# The real snapclient, which the image moves off `/usr/bin/snapclient` so that the path
# `snapclient.service` names keeps the idle stub. Only `listening_player` runs it.
SNAPCLIENT = '/usr/local/bin/snapclient-real'

# Every unit provisioning installs, read out of the writers rather than listed. The heredocs in these
# two files are the only description of a provisioned device's unit set, so a unit added there is
# covered without a test file having to be updated. `test_index.py` parameterizes a stop budget over
# it and `test_provisioning.py` removes and then re-asserts it, so it lives here rather than in either.
#
# `common.sh` writes `camilladsp.service`, which the player installs too; `streamer.sh` writes the other
# five. The order across the two decides only the order of the parameterized ids below, since every
# consumer of `WRITTEN_UNITS` tests membership or sorts first.
_UNIT_WRITERS = (COMMON_SH, STREAMER_SH)

# The trailing ` <<` matches a heredoc write and nothing else, which keeps the `nqptp` drop-in
# (`cat > /etc/systemd/system/nqptp.service.d/timeout.conf`) from also matching as a unit.
_UNIT_WRITE = re.compile(r'cat > /etc/systemd/system/(\S+)\.service <<')


def _written_units(path: str) -> tuple[str, ...]:
    """Returns the units one library file installs, and refuses to return none.

    Per file rather than over the union, since the union is non-empty as soon as either file matches:
    a check on it would have passed the day `streamer.sh` was split out of `common.sh` with the
    derivation still pointed at `common.sh` alone, leaving five of six units unasserted.
    """
    units = tuple(_UNIT_WRITE.findall(Path(path).read_text(encoding='utf-8')))
    if not units:
        raise RuntimeError(f'no unit writes matched in {path}, so every derivation from it would silently cover nothing')
    return units


WRITTEN_UNITS = tuple(unit for path in _UNIT_WRITERS for unit in _written_units(path))

# A unit written by both files has two descriptions, and the parameterizations below would run it
# twice and pass. That is what an extraction copied rather than moved looks like.
if len(set(WRITTEN_UNITS)) != len(WRITTEN_UNITS):
    raise RuntimeError(f'a unit is written by more than one library file, so it has two descriptions: {WRITTEN_UNITS}')

# Provisioning installs six units, enables five and starts five, each a round trip to the manager.
# Generous, because the failure this bounds is a wedged `systemctl`.
_PROVISION_TIMEOUT: float = 120

# How long to let a restarted Snapserver take to answer. The handler under test has its own, shorter
# budget in `index._READY_TIMEOUT`, left at its real value; this one only has to be long enough that a
# slow container is not reported as a broken Snapserver.
_SNAPSERVER_TIMEOUT: float = 60


def _run(*args: str) -> str:
    """Runs a probe command and returns its stdout, ignoring the exit status.

    Every probe here answers a question whose negative case exits non-zero (`pgrep` exits 1 when
    nothing matches, `systemctl show` exits non-zero for an unknown unit), so the status carries
    nothing the output does not.
    """
    return subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT, check=False).stdout


def unit_state(unit: str) -> dict[str, str]:
    """Returns `_PROPERTIES` for `unit`, as read from `systemctl show`.

    An unknown unit is not an error: systemd answers for it with `LoadState=not-found` and empty
    values for the rest, so a caller can assert on the unknown case without branching.

    `LoadState` says nothing about whether a unit is enabled, because `systemctl show` *loads* the
    unit in order to answer and reads `loaded` for any unit whose file exists. `UnitFileState` is the
    probe for enablement.
    """
    properties = {}
    for line in _run('systemctl', 'show', unit, *(f'--property={p}' for p in _PROPERTIES)).splitlines():
        key, _, value = line.partition('=')
        if key:
            properties[key] = value
    return properties


def await_unit_state(unit: str, active_state: str, timeout: float = 2) -> dict[str, str]:
    """Polls `unit_state` until `ActiveState` reads `active_state`, and returns the last reading.

    A `systemctl` verb's exit status is not a barrier for the properties `systemctl show` answers
    with. A refused job returns as soon as it is refused, while the unit's transition into `failed`
    and the `Result` that explains why land a moment afterwards, so a `show` on the next line can read
    the state the unit was in before. Measured as `test_index.py`'s `_wedge_start_limit`
    intermittently reporting a unit that was refused but not yet `failed`.

    Returns whatever it last read at the deadline, so the caller's assertion reports the state it got
    rather than a timeout. The budget is short because every caller is racing the start limit's
    trailing interval, so a wrong state has to fail before that window closes.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = unit_state(unit)
        if state.get('ActiveState') == active_state or time.monotonic() >= deadline:
            return state
        time.sleep(0.05)


def pids_for(pattern: str) -> dict[int, str]:
    """Returns `{pid: cmdline}` for every live process whose command line matches `pattern`.

    `pgrep -af`, so the pattern is matched against the full command line rather than against `comm`,
    which the kernel caps at fifteen characters. The units and the catalog URIs name a path, and
    `still_alive` compares against the same.
    """
    pids = {}
    for line in _run('pgrep', '-af', pattern).splitlines():
        pid, _, cmdline = line.partition(' ')
        if pid.strip().isdigit():
            pids[int(pid)] = cmdline
    return pids


def await_pids(pattern: str, timeout: float = 5) -> dict[int, str]:
    """Polls `pids_for` until something matches, and returns it, or an empty dict if the deadline passes.

    `systemctl start` is not a barrier for the process table. Every unit Audera writes is the default
    `Type=simple`, and systemd calls such a unit active as soon as it has forked, before the child has
    reached `execve`, so `/proc/<pid>/cmdline` is briefly still systemd's. A `pids_for` issued on the
    line after a `start` therefore matches nothing, intermittently, on a fast machine.

    Only the transition into running needs this. `stop` is a barrier, since systemd waits for the
    process to die before completing the job, and polling `still_alive` after a stop would hide the
    leak it exists to find.
    """
    deadline = time.monotonic() + timeout
    while True:
        pids = pids_for(pattern)
        if pids or time.monotonic() >= deadline:
            return pids
        time.sleep(0.05)


def still_alive(before: dict[int, str]) -> dict[int, str]:
    """Returns the subset of `before` that is still running the same command.

    The command is re-read because these tests restart Snapserver, which frees a burst of pids the next
    fork may reuse, and a liveness check alone would report a recycled pid as a leak.
    """
    alive = {}
    for pid, cmdline in before.items():
        current = _run('ps', '-p', str(pid), '-o', 'args=').strip()
        if current and current == cmdline:
            alive[pid] = cmdline
    return alive


def zombies_for(pattern: str = '') -> list[str]:
    """Returns `<stat> <ppid> <args>` rows for processes in state `Z`, optionally filtered.

    A separate probe from `still_alive` because the two failures need different fixes: an orphan
    steals CPU from playback, sync and DSP, while a zombie consumes a pid-table slot its parent will
    never release. `os/dietpi/AGENTS.md` records an occurrence of the second, snapserver re-forking a
    failed backend around ten times a second while the Sources tab reported the source healthy.

    A zombie has no command line left to read, so `ps` renders it as `[comm] <defunct>`, where `comm`
    is the fifteen characters the kernel kept. `pattern` therefore only matches a name short enough to
    survive the cap; passing no pattern and asserting on the difference from a snapshot cannot be
    fooled by truncation. `ppid` is in the row because the parent identifies the failure: a zombie
    under snapserver's MainPID is the reported failure, and one under pid 1 is systemd reaping.
    """
    rows = []
    for line in _run('ps', '-eo', 'stat=,ppid=,args=').splitlines():
        if line.strip().startswith('Z') and pattern in line:
            rows.append(line.strip())
    return rows


def await_no_new_zombies(before: list[str], timeout: float = 5) -> list[str]:
    """Returns the zombie rows not in `before` that are still zombies after settling.

    A zombie is not a leak until it persists, and the tests here create transient ones through no
    fault of the code under test: a Snapserver restart kills the stub backends, and each is a shell
    script whose own `dd` child is defunct between its death and its parent's `wait`. Comparing two
    `zombies_for()` snapshots caught that `[dd] <defunct>` roughly one run in four.

    Polling does not weaken the assertion, since the failure this is aimed at is unbounded:
    `os/dietpi/AGENTS.md` records snapserver re-forking a failed backend around ten times a second and
    reaping none of them, so the set is never empty and never the same twice.
    """
    deadline = time.monotonic() + timeout
    while True:
        new = [row for row in zombies_for() if row not in before]
        if not new or time.monotonic() >= deadline:
            return new
        time.sleep(0.05)


def ppid_of(pid: int) -> int:
    """Returns `pid`'s parent, or `0` if it is not running.

    A backend under Snapserver's `MainPID` is one Snapserver forked, which is what "no unit" means for
    the Spotify source; the same process under pid 1 has been orphaned.
    """
    value = _run('ps', '-p', str(pid), '-o', 'ppid=').strip()
    return int(value) if value.isdigit() else 0


def process_tree(pid: int) -> dict[int, str]:
    """Returns `{pid: cmdline}` for `pid` and every descendant of it.

    The unit's cgroup is not readable by these probes. One `ps -eo pid=,ppid=,args=` and a walk gives
    the same set from the process table, which is identical under cgroup v1 and v2.

    A pattern match cannot stand in: `plexamp.service` starts `/bin/bash -c '… exec /usr/bin/node …'`,
    so its `ExecStart` path is an interpreter half the container shares, while the process that leaks
    is the node beneath it.
    """
    commands: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for line in _run('ps', '-eo', 'pid=,ppid=,args=').splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        commands[int(parts[0])] = parts[2]
        children.setdefault(int(parts[1]), []).append(int(parts[0]))

    tree: dict[int, str] = {}
    frontier = [pid]
    while frontier:
        current = frontier.pop()
        if current in tree or current not in commands:
            continue
        tree[current] = commands[current]
        frontier.extend(children.get(current, ()))
    return tree


def await_process_tree(pid: int, timeout: float = 5) -> dict[int, str]:
    """Polls `process_tree` until it stops growing, and returns it.

    `await_pids`' problem one level down. `systemctl start` returns once systemd has forked, so a unit
    that wraps its real process (`plexamp.service` is `bash -c … exec node`) reports a tree of one for
    a moment and its payload a moment later. Snapshotting the tree of one and then asserting nothing
    survived the stop would say nothing about the process that matters.

    Settles on two consecutive identical reads rather than counting, which needs no per-unit expected
    size and is immediate for a unit that forks nothing.
    """
    deadline = time.monotonic() + timeout
    previous: dict[int, str] = {}
    while True:
        tree = process_tree(pid)
        if tree and tree.keys() == previous.keys():
            return tree
        if time.monotonic() >= deadline:
            return tree
        previous = tree
        time.sleep(0.05)


def stream_status() -> dict[str, str]:
    """Returns Snapserver's own status word per stream id, or `{}` when it is unreachable.

    `index._stream_status` reads the same thing through `page.settings`, and the tests do not call it,
    since the assertion is about what the server is serving and must not be routed through the module
    whose ordering is under test.
    """
    try:
        return SnapserverClient(host='127.0.0.1', port=audera.SNAPSERVER_PORT).get_stream_status()
    except Exception:
        return {}


def await_stream_status(timeout: float = _SNAPSERVER_TIMEOUT) -> dict[str, str]:
    """Polls `stream_status` until Snapserver answers, returning an empty dict if the deadline passes."""
    deadline = time.monotonic() + timeout
    while True:
        status = stream_status()
        if status or time.monotonic() >= deadline:
            return status
        time.sleep(0.25)


def groups() -> list[Group]:
    """Returns Snapserver's own groups, or `[]` when it is unreachable.

    `stream_status`' counterpart for the other half of the ownership split: Snapcast owns which stream
    a group listens to, persisted in its own `server.json`, so a test asserting where a listener ended
    up has to ask the server rather than `index._reassign_groups`' own client.
    """
    try:
        return SnapserverClient(host='127.0.0.1', port=audera.SNAPSERVER_PORT).get_groups()
    except Exception:
        return []


def assign_group(group_id: str, stream_id: str) -> None:
    """Puts `group_id` on `stream_id`, as the Players tab's move control does.

    Setup rather than a probe. A caller seeds and then reads back through `await_settled_group`, so a
    write that did not land fails the seed instead of the assertion the test is about.
    """
    SnapserverClient(host='127.0.0.1', port=audera.SNAPSERVER_PORT).set_group_stream(group_id, stream_id)


def await_settled_group(group_id: str, timeout: float = _SNAPSERVER_TIMEOUT) -> str:
    """Returns the stream `group_id` listens to, once every client in it has reconnected.

    Read at a settled point rather than immediately, because the reassignment Snapserver performs for
    itself happens at *client connect* (`catalog.py`'s rule 3): a group whose stream the conf no longer
    provides keeps that stream in `server.json` until a client reconnects. Every toggle restarts
    Snapserver, so a read taken before the client is back can see the pre-restart value.

    Returns whatever it last saw when the deadline passes, so the assertion reports the stream rather
    than a timeout.
    """
    deadline = time.monotonic() + timeout
    stream = ''
    while True:
        stream = next((group.stream_id for group in groups() if group.id == group_id), stream)
        members = [client for client in _clients() if client.group_id == group_id]
        if members and all(client.connected for client in members):
            return stream
        if time.monotonic() >= deadline:
            return stream
        time.sleep(0.25)


def _clients() -> list[Player]:
    """Returns Snapserver's own clients, or `[]` when it is unreachable."""
    try:
        return SnapserverClient(host='127.0.0.1', port=audera.SNAPSERVER_PORT).get_clients()
    except Exception:
        return []


@contextlib.contextmanager
def sampling_main_pid(unit: str, interval: float = 0.01) -> Iterator[list[int]]:
    """Records the ordered, distinct, non-zero `MainPID`s `unit` holds while the block runs.

    Two `systemctl show` calls either side of a block cannot count restarts, since one restart and ten
    look identical from the endpoints. Sampling makes "restarted exactly twice" observable, which
    `test_a_second_toggle_waits_for_the_first` needs to distinguish two serialized choreographies from
    two that collapsed into one restart.

    Zeros are dropped: `MainPID` reads `0` between a unit's stop and its start, so keeping them would
    make the sequence's length a function of how often the sampler landed mid-restart.

    The interval has to stay well under the life of one Snapserver instance, which is a restart plus
    `index._await_snapserver`'s first successful poll, hundreds of milliseconds. `systemctl show` paces
    the loop above the nominal interval and releases the GIL, so the sampler does not contend with the
    handler it is watching.
    """
    pids: list[int] = []
    stop = threading.Event()

    def _sample() -> None:
        while not stop.is_set():
            value = unit_state(unit).get('MainPID', '0')
            pid = int(value) if value.isdigit() else 0
            if pid and (not pids or pids[-1] != pid):
                pids.append(pid)
            stop.wait(interval)

    thread = threading.Thread(target=_sample, daemon=True)
    thread.start()
    try:
        yield pids
    finally:
        stop.set()
        thread.join(timeout=_TIMEOUT)


def provision(home: str | None = None) -> None:
    """Brings the container to the state a freshly flashed streamer boots in.

    The image ships no Audera unit file, so everything the modules here assert on is installed by the
    device's own `os/dietpi/lib/streamer.sh`, invoked with the arguments
    `os/dietpi/streamer/automation/setup.sh` passes it.

    `common.sh` is sourced alongside it, as `setup.sh` sources both: `write_streamer_units` calls its
    `write_camilladsp_service`, which the player's setup calls too.

    Three things happen in Python instead, since on the device they are `audera streamer conf`
    redirects rather than shell functions: the two configuration directories, the rendered
    `snapserver.conf`, and the rendered go-librespot and CamillaDSP configurations. The Snapserver
    configuration is rendered from `get_enabled()`, as the CLI the device redirects renders it.

    Nothing writes `sources.json`, matching the device's behaviour: `get_enabled()` degrades an absent
    file to `DEFAULT_ENABLED`, which keeps the enabled set and the conf in agreement with no file to
    seed. A test that toggles a source creates the file itself, under the `audera_home` the fixture
    points the data-access layer at.

    The three shell functions are invoked as bare commands, as `setup.sh` invokes them. `set -e` is
    suppressed inside a function called in condition context, so wrapping one in
    `if write_streamer_units; then` would stop this script failing on a failure that would not stop
    `setup.sh` either.

    Parameters
    ----------
    home: `str | None`
        The `HOME` the provisioning shell runs under, or `None` for the container's own. This is the
        one input the shell reads that the `audera_home` fixture cannot supply: `activate_streamer_units`
        shells out to `audera streamer units`, a separate process that resolves `~/.audera` from its
        environment rather than from a monkeypatched `PATH`. A test recording an enabled set therefore
        points both at one directory.
    """
    os.makedirs(GO_LIBRESPOT_CONFIG_DIR, exist_ok=True)
    os.makedirs(CAMILLADSP_CONFIG_DIR, exist_ok=True)
    Path(conf.SNAPSERVER_CONF).write_text(conf.render_snapserver(sources_dal.get_enabled()), encoding='utf-8')
    Path(GO_LIBRESPOT_CONFIG_DIR, 'config.yml').write_text(conf.render_go_librespot(), encoding='utf-8')
    Path(CAMILLADSP_CONFIG).write_text(conf.render_camilladsp(), encoding='utf-8')

    subprocess.run(
        [
            '/bin/bash',
            '-c',
            f'set -e\n'
            f'source {COMMON_SH}\n'
            f'source {STREAMER_SH}\n'
            f'write_plexamp_mdns_helper\n'
            f'write_streamer_units {SNAPSERVER_HOME} {conf.SNAPSERVER_CONF} '
            f'{CAMILLADSP_CONFIG} {CAMILLADSP_STATEFILE}\n'
            f'activate_streamer_units\n',
        ],
        capture_output=True,
        text=True,
        timeout=_PROVISION_TIMEOUT,
        check=True,
        env={**os.environ, 'HOME': home} if home else None,
    )


@pytest.fixture
def provisioned(audera_home) -> Iterator[None]:
    """Re-provisions the container, so each test starts from a freshly flashed device.

    Not autouse. `tests/systemd/inside/test_platform.py` asserts that `/etc/systemd/system/` ships no
    Audera unit, so an autouse fixture here would write the units that test exists to prove are absent.
    A module that wants this state says so with `pytestmark = pytest.mark.usefixtures('provisioned')`.

    One step precedes `provision()` and two follow it:

    - Snapserver's start-limit counter is reset. `snapserver.service` takes the manager's
      `DefaultStartLimitBurst` of five starts per `DefaultStartLimitIntervalSec`, deliberately, since
      it also carries `Restart=on-failure` and the pathology `os/dietpi/AGENTS.md` records is a backend
      re-forked at ten hertz. The reset covers this fixture's own restarts, none of which go through
      `toggle.apply`; the handler path clears the same counters itself, which
      `test_a_toggle_revives_a_snapserver_the_start_limit_wedged` asserts.
    - The units of every source outside the enabled set are stopped by `activate_streamer_units`
      itself, which disables them `--now`. Nothing here repeats that: a second stop would hide the day
      provisioning stopped doing it.
    - Snapserver is restarted. `activate_streamer_units` ends in `systemctl start snapserver`, which is
      a no-op against the instance the previous test left running, and that instance serves the conf
      that test wrote rather than the baseline this fixture just rendered.
    """
    subprocess.run(['systemctl', 'reset-failed', 'snapserver'], capture_output=True, timeout=_TIMEOUT, check=False)

    provision()

    subprocess.run(['systemctl', 'restart', 'snapserver'], capture_output=True, timeout=_TIMEOUT, check=True)
    if not await_stream_status():
        raise RuntimeError(
            f'Snapserver did not answer within {_SNAPSERVER_TIMEOUT}s of provisioning: {unit_state("snapserver")}'
        )

    yield


@pytest.fixture
def listening_player(provisioned) -> Iterator[str]:
    """Connects a real snapclient and yields the id of the group Snapserver puts it in.

    Opt-in, and the only fixture here that runs a process no provisioned unit names. Every other
    module runs against the image's idle stub at `/usr/bin/snapclient`, because a real client under
    `snapclient.service` restart-loops against the `hw:Loopback,0` no container has and settles
    `failed`. This runs the binary directly with `--player stdout` discarded, so it is a participant in
    the protocol and nothing else: no unit, no ALSA, nothing for the leak probes to attribute.

    A group is the one thing a client-less Snapserver cannot produce. Without it `get_groups()` answers
    `[]`, so `index._reassign_groups` loops over nothing and every test that passes a destination
    asserts only that no exception was raised.

    `--player stdout` rather than `file`, matching `tests/docker/snapserver/entrypoint.sh`.
    """
    process = subprocess.Popen([SNAPCLIENT, '--host', '127.0.0.1', '--player', 'stdout'], stdout=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + _SNAPSERVER_TIMEOUT
        while True:
            connected = [group for group in groups() if group.client_ids]
            if connected:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f'no snapclient reached Snapserver within {_SNAPSERVER_TIMEOUT}s: {stream_status()}')
            time.sleep(0.25)
        yield connected[0].id
    finally:
        process.terminate()
        process.wait(timeout=_TIMEOUT)


@pytest.fixture(autouse=True)
async def _command_queue(monkeypatch):
    """Starts a command queue for each test and tears it down afterwards."""
    q = commands.CommandQueue()
    q.start()
    monkeypatch.setattr(commands, '_queue', q)
    yield
    await q.stop()


@pytest.fixture
def notifications(monkeypatch) -> list[tuple[str, str]]:
    """Captures `ui.notify` as an ordered `[(message, type)]` list.

    `ui.notify` resolves `context.client` through NiceGUI's slot stack and raises outside a client, so
    the handlers cannot be called without either this or a NiceGUI server, which
    `tests/ui/test_streamer.py`'s `user` fixture already covers.

    Ordered, because on two paths the report is the assertion: the refusal of the last enabled source is
    only observable as a notification, and mutual exclusion under contention is observable as the
    absence of interleaving in this list. Every test also asserts no `negative` entry, which surfaces a
    `systemctl` failure's own `stderr` in the failure message instead of a bare missing-process
    assertion.
    """
    captured: list[tuple[str, str]] = []

    def _notify(message: str, *args, **kwargs) -> None:
        captured.append((str(message), str(kwargs.get('type', ''))))

    monkeypatch.setattr(index.ui, 'notify', _notify)
    return captured


class _Refreshable:
    """Stands in for a `@ui.refreshable` tab builder, recording refreshes rather than rendering."""

    def __init__(self) -> None:
        self.refreshes: int = 0

    def refresh(self) -> None:
        self.refreshes += 1


class _PageStub:
    """The `page` the handlers read, without the `Page` that would provision itself.

    Not the real `Page`: `Page.load()` calls `index.adopt_running_sources`, which writes
    `sources.json` from the streams Snapserver is currently serving, so inside this container it would
    record an enabled set from the previous test's conf before the current test's first line ran.

    `settings` is loaded exactly as `Page.__init__` loads it, so `snapserver_host` comes from the
    image's `AUDERA_SNAPSERVER_HOST` and reaches the real Snapserver on loopback.
    """

    def __init__(self) -> None:
        self.settings = _load_settings()
        self._dialog_open: bool = False
        self._deferred_tabs: set[str] = set()
        self._claim_in_flight: bool = False
        self._build_sources_tab = _Refreshable()


@pytest.fixture
def page(audera_home) -> _PageStub:
    """Yields the `page` stub the handlers take as their first argument."""
    return _PageStub()
