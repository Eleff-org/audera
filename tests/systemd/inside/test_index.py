"""The Sources tab's choreography, and the process leaks only a real host can show.

Runs inside the privileged systemd container, against a real Snapserver. `tests/ui/test_streamer.py`
drives the same handlers from the page, with `system.systemctl` stubbed out because a developer's
machine has no manager, so it covers what the operator sees and what reaches `~/.audera` and
`snapserver.conf`. Nothing there can show a backend Snapserver forked and never reaped, which keeps
running with every one of those assertions green.

The handlers are awaited as written. `_enable_source` and `_disable_source` are called rather than
re-driven step by step, because the ordering is under test: a test that performed the steps itself would
not fail on a reordering inside `index.py`.

Every assertion about what is running reads the host through this package's probes rather than through
`index`. `stream_status()` asks Snapserver over its own client, and the enabled set is read back from
`index._enabled_ids()` only where the record is the claim being made.

The last tests cover the stop budget every provisioned unit carries and the start rate limit
`toggle.apply` clears its counters against. Both sit beside the choreography rather than beside the seam:
one manager default costs this module's disable path aborting before the restart, and the other costs a
toggle refused outright with Snapserver left dead, reachable only because every toggle restarts it.
"""

import asyncio
import re
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from audera.cli import conf
from audera.domains.sources import CATALOG
from audera.services import system
from audera.ui.streamer.pages import index
from tests.systemd.inside.conftest import (
    WRITTEN_UNITS,
    assign_group,
    await_no_new_zombies,
    await_pids,
    await_process_tree,
    await_settled_group,
    await_stream_status,
    await_unit_state,
    pids_for,
    ppid_of,
    process_tree,
    sampling_main_pid,
    still_alive,
    stream_status,
    unit_state,
    zombies_for,
)

# Every test here provisions. The module asserts on units and on a running Snapserver, and the
# image ships neither.
pytestmark = pytest.mark.usefixtures('provisioned')

# Read from the catalog rather than restated. A source's id, label and units are defined once
# (`audera/domains/sources/catalog.py`), and a test that spelled them again would keep passing
# against a catalog it no longer described.
AIRPLAY = next(source for source in CATALOG if source.id == 'AirPlay')
SPOTIFY = next(source for source in CATALOG if source.id == 'Spotify')
PLEXAMP = next(source for source in CATALOG if source.id == 'PlexAmp')

# The path the Spotify source's URI names, and therefore the process Snapserver forks for it. The
# stub lives at the same path the device's binary does, so neither the catalog nor the conf is
# rewritten for the container.
GO_LIBRESPOT = '/usr/local/bin/go-librespot'

# The stub that ignores SIGTERM, swapped into `nqptp`'s ExecStart by `wedged_nqptp`. It forces the
# SIGTERM to SIGKILL escalation that `TimeoutStopSec` bounds, so the bound is observable rather than
# only the property it is configured through.
STUBBORN_BACKEND = '/usr/local/bin/stubborn-backend'

# `nqptp` is provisioned as a drop-in rather than as a unit, since the device gets the unit itself from
# DietPi's `shairport-sync-airplay2` package, so `WRITTEN_UNITS`, which reads the writer's heredocs,
# cannot see it. It is also the one unit whose stop an operator triggers directly, by toggling AirPlay
# off, so it is the one this module wedges.
UNITS_UNDER_A_STOP_BUDGET = (*WRITTEN_UNITS, 'nqptp')

# The suffixes systemd renders a timespan with, and what each is worth in seconds. `_seconds` reads
# them; there is no bare minutes suffix to disambiguate from milliseconds.
_SCALE = {'us': 1e-6, 'ms': 1e-3, 's': 1.0, 'min': 60.0, 'h': 3600.0}

# How many raw restarts `_wedge_start_limit` will spend looking for the manager's refusal. The
# default burst is five and the `provisioned` fixture has already spent part of it, so the refusal
# normally lands well inside this; the bound is here so a manager with no reachable limit fails the
# test rather than looping.
_START_LIMIT_ATTEMPTS: int = 12

# The toggle rate an operator on the Sources tab exceeds, and therefore the threshold that makes
# systemd's start limit reachable. One a second is conservative for a switch: a person who changes their
# mind about a source flips it twice in well under that.
_OPERATOR_TOGGLES_PER_SECOND: float = 1.0

# How long `slow_conf_write` holds the conf write back. It only has to exceed the time a restarted
# Snapserver takes to open its configuration and register its streams, which is milliseconds here and
# under a second even on the device. Two makes the interval unambiguous and costs four seconds across the
# one test that uses it.
_WRITE_DELAY: float = 2.0


@pytest.fixture
def slow_conf_write(monkeypatch) -> None:
    """Holds the rendered conf back for `_WRITE_DELAY`, so its position in the sequence decides.

    `toggle.apply` reads `conf.render_snapserver` through the module at call time, which its own comment
    gives as the reason `conf` is imported as a module, so delaying the render delays the write and
    nothing else. Neither the restart nor the units move, and the conf that lands is byte-identical to the
    undilated one.

    Correctly ordered, the write completes before the restart that reads it and the delay is only
    wall-clock. Reordered, the restarted Snapserver opens the file while this call is still inside the
    write, and what it reads is not the conf the call renders: `open(…, 'w')` truncates before the render
    it dilates, so Snapserver finds an empty configuration and falls back to a single built-in `default`
    stream. The undilated reordering can leave the previous conf in place instead. Either way the streams
    served are not the ones the file names, which is what the test asserts; the dilation removes the
    millisecond race that decides which of the two happens.
    """
    render = conf.render_snapserver

    def _slow_render(*args, **kwargs) -> str:
        time.sleep(_WRITE_DELAY)
        return render(*args, **kwargs)

    monkeypatch.setattr(conf, 'render_snapserver', _slow_render)


@pytest.fixture
def wedged_nqptp() -> Iterator[str]:
    """Swaps `STUBBORN_BACKEND` into `nqptp`'s ExecStart, and yields once it is running.

    A drop-in beside the one provisioning wrote rather than an edit to it. `ExecStart=` on its own line
    clears the list systemd already parsed, which is the only way to replace rather than append to it, and
    leaving the stop budget in the file provisioning owns keeps this fixture to one change.

    `nqptp` is the unit to wedge because it is the one an operator's toggle stops. `avahi-publish` would be
    the same escalation against a unit no handler touches.
    """
    drop_in_dir = Path('/etc/systemd/system/nqptp.service.d')
    drop_in = drop_in_dir / 'wedged.conf'
    drop_in_dir.mkdir(parents=True, exist_ok=True)
    drop_in.write_text(f'[Service]\nExecStart=\nExecStart={STUBBORN_BACKEND}\n', encoding='utf-8')
    subprocess.run(['systemctl', 'daemon-reload'], capture_output=True, timeout=15, check=True)
    subprocess.run(['systemctl', 'restart', 'nqptp'], capture_output=True, timeout=15, check=True)

    yield 'nqptp'

    # The drop-in is removed before the reload, so nothing after this test can start the stubborn stub.
    # The `stop` is unconditional because the test may have failed before its own `disable --now`, and a
    # surviving SIGTERM-proof process would outlive every later test in this module.
    drop_in.unlink(missing_ok=True)
    subprocess.run(['systemctl', 'daemon-reload'], capture_output=True, timeout=15, check=False)
    subprocess.run(['systemctl', 'stop', 'nqptp'], capture_output=True, timeout=15, check=False)
    subprocess.run(['systemctl', 'reset-failed', 'nqptp'], capture_output=True, timeout=15, check=False)


def _seconds(timespan: str) -> float:
    """Parses systemd's rendered timespan (`5s`, `1min 30s`, `infinity`) into seconds.

    `systemctl show` renders these properties rather than emitting the microseconds their names promise, so
    a comparison against `system.TIMEOUT` has to go through this. It raises on a string it could not read a
    single component out of, because an unparseable value summing to `0.0` would satisfy every
    `< system.TIMEOUT` assertion below, and an unknown unit answers with that empty string.
    """
    if timespan.strip() == 'infinity':
        return float('inf')

    components = re.findall(r'(\d+)(us|ms|min|h|s)', timespan)
    if not components:
        raise ValueError(f'unparseable systemd timespan: {timespan!r}')
    return sum(int(value) * _SCALE[suffix] for value, suffix in components)


def _manager_default(name: str) -> str:
    """Returns one of the manager's own `Default*` properties, rendered.

    `systemctl show` with no unit answers for the manager, a different scope from `unit_state`'s, so this
    is its own helper. It `check`s, because a manager that cannot state its own configuration should not be
    read out of an empty string.
    """
    result = subprocess.run(
        ['systemctl', 'show', f'--property={name}', '--value'],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    return result.stdout.strip()


def _wedge_start_limit(unit: str) -> float:
    """Restarts `unit` until the manager refuses, and returns the deadline past which an assertion is moot.

    Raw `subprocess.run` rather than the seam, for the reason this package's `conftest.py` gives, and
    `restart` rather than `stop` then `start` because `restart` is the verb a toggle issues.

    Restarts until refused rather than exactly `StartLimitBurst` times, since the counter is not at zero
    when a test begins: the `provisioned` fixture starts Snapserver twice inside its own setup, so how many
    restarts remain is not knowable in advance.

    The counter is a trailing window, so the wedge is not permanent: once the oldest of the counted starts
    ages out the unit becomes startable again with nothing having repaired it. A caller that took that long
    to reach its assertion would pass whether or not the code under test cleared a counter, so it has to
    fail as inconclusive instead.

    The deadline is one interval from before the first restart rather than from the refusal, which is the
    tighter of the two: the priming restarts take about a second, so a deadline measured from the refusal
    would sit a second past the point the wedge can lift. It bounds the harness's pacing rather than
    proving anything, since starts the `provisioned` fixture already put in the window are older still and
    their ages are not knowable from here. The margin makes that immaterial: a handler call is a second or
    two against a ten-second interval.
    """
    started = time.monotonic()
    for _ in range(_START_LIMIT_ATTEMPTS):
        result = subprocess.run(['systemctl', 'restart', unit], capture_output=True, text=True, timeout=15, check=False)
        if result.returncode != 0:
            break
    else:
        raise AssertionError(f'{unit} accepted {_START_LIMIT_ATTEMPTS} restarts, so it has no reachable start limit')

    state = await_unit_state(unit, 'failed')
    assert state['ActiveState'] == 'failed', f'{unit} was refused but is not failed: {state}'
    assert state['Result'] == 'start-limit-hit', f'{unit} failed for another reason: {state}'
    return started + _seconds(state['StartLimitIntervalUSec'])


def _conf_stream_ids() -> list[str]:
    """Returns the stream ids `/etc/snapserver.conf` currently names, in file order.

    Parsed out of the `source =` lines rather than compared against `render_snapserver()`. The renderer
    wrote the file, so rendering again and diffing would assert that a pure function is deterministic,
    while reading the ids back out says the file on disk names the streams the test expects. `name` is the
    stream id per `CATALOG`'s rule 1, so this is directly comparable with `stream_status()`'s keys.
    """
    ids: list[str] = []
    for line in Path(conf.SNAPSERVER_CONF).read_text(encoding='utf-8').splitlines():
        key, separator, value = line.partition('=')
        if separator and key.strip() == 'source':
            ids.extend(parse_qs(urlsplit(value.strip()).query).get('name', []))
    return ids


def _failures(notifications: list[tuple[str, str]]) -> list[str]:
    """Returns the `negative` notification messages, which carry `systemctl`'s own `stderr`.

    Asserted empty in every test here, before the assertion the test is about. Both handlers catch every
    exception and report it through `_notify_failure`, which renders `getattr(exc, 'stderr', '')`, so
    without this a `systemctl` that refused the job surfaces as a missing process with the reason systemd
    gave nowhere in the failure message.
    """
    return [message for message, type_ in notifications if type_ == 'negative']


async def test_enabling_spotify_makes_snapserver_fork_its_backend(page, notifications):
    """Spotify has `units=()`, so the enable is conf, then restart, then Snapserver's own fork.

    The assertion is on the parent rather than on the existence of the process. go-librespot under
    Snapserver's `MainPID` is a backend Snapserver owns and will reap; the same process under pid 1 is the
    orphan `os/dietpi/AGENTS.md` records, and it would satisfy a bare "is it running" check.

    `await_pids` rather than `pids_for`, because `restart` returns once systemd has forked Snapserver and
    Snapserver forks its backends later still. The stream registration is polled for the same reason,
    through Snapserver's own answer rather than the UI's reading of it.
    """
    assert pids_for(GO_LIBRESPOT) == {}, 'the baseline conf already names Spotify'

    await index._enable_source(page, SPOTIFY)

    assert _failures(notifications) == []
    pids = await_pids(GO_LIBRESPOT)
    assert pids, 'Snapserver restarted with Spotify in the conf but forked no backend'
    assert {ppid_of(pid) for pid in pids} == {int(unit_state('snapserver')['MainPID'])}
    assert 'Spotify' in await_stream_status()


async def test_disabling_spotify_reaps_the_backend_snapserver_forked(page, notifications):
    """With no unit, `restart snapserver` is the only thing that reaps the backend.

    Dropping that restart from the disable path leaves go-librespot running against a conf that no longer
    names it, which every argv assertion in `tests/ui/test_streamer.py` accepts. Here it fails on
    `still_alive`.

    Zombies are asserted separately from orphans because the two failures need different fixes: an orphan
    steals CPU from playback, sync and DSP on a Pi Zero 2 W, while a zombie consumes a pid-table slot its
    parent will never release. The second is the shape `os/dietpi/AGENTS.md` records, at around ten a
    second, while the Sources tab reported the source healthy.
    """
    await index._enable_source(page, SPOTIFY)
    before = await_pids(GO_LIBRESPOT)
    zombies_before = zombies_for()
    assert before, 'nothing to leak — the enable did not fork a backend'

    await index._disable_source(page, SPOTIFY, None)

    assert _failures(notifications) == []
    assert still_alive(before) == {}
    assert await_no_new_zombies(zombies_before) == []
    assert 'Spotify' not in _conf_stream_ids()
    assert 'Spotify' not in stream_status()


@pytest.mark.parametrize('source', [source for source in CATALOG if source.units], ids=lambda source: source.id)
async def test_disabling_a_source_leaves_no_process_from_its_units(page, notifications, source):
    """Every unit-backed source, read from the catalog so a new one is covered the day it lands.

    Spotify is enabled first as the companion the guard requires: `_disable_source` refuses the last
    enabled source, and Spotify has no units of its own, so it cannot contribute a process to the trees
    below. When the parameter is AirPlay, which the baseline already enabled, the enable below is skipped.

    The process tree rather than a pattern match, because `plexamp.service` is `bash -c '… exec node …'`:
    its `ExecStart` path is an interpreter half the container shares, while the process that would leak is
    the node beneath it. `await_process_tree` settles on two identical reads rather than on a per-unit
    expected size, since `start` returns before a wrapper unit has exec'd its payload.

    The manager's bookkeeping is asserted alongside the process table because the two can disagree: systemd
    forgets a unit it could not stop, and the backend keeps running under pid 1 with nothing naming it.
    """
    await index._enable_source(page, SPOTIFY)
    if source.id not in index._enabled_ids():
        await index._enable_source(page, source)

    before: dict[int, str] = {}
    for unit in source.units:
        main_pid = int(unit_state(unit)['MainPID'])
        assert main_pid > 0, f'{unit} is not running, so this test would assert nothing'
        before |= await_process_tree(main_pid)
    zombies_before = zombies_for()

    await index._disable_source(page, source, None)

    assert _failures(notifications) == []
    assert still_alive(before) == {}
    assert await_no_new_zombies(zombies_before) == []
    for unit in source.units:
        state = unit_state(unit)
        assert state['ActiveState'] == 'inactive'
        assert state['SubState'] == 'dead'
        assert state['MainPID'] == '0'
        assert state['UnitFileState'] == 'disabled'


async def test_disabling_a_source_moves_its_listeners_to_the_chosen_destination(page, notifications, listening_player):
    """`_reassign_groups` against a real group, which is the only thing that distinguishes it from a no-op.

    The other tests here pass `destination=None`, and until `listening_player` there was no client, so
    `get_groups()` answered `[]` and a destination that never reached `Group.SetStream` would have looked
    identical to one that did.

    PlexAmp is the destination rather than AirPlay so that Snapserver's own fallback cannot stand in for
    the handler's work. `catalog.py`'s rule 3: a group whose stream the conf stops providing is reassigned
    to `default_source`, which is the first `CATALOG` entry still enabled and so AirPlay here. Asking for
    AirPlay would let a destination that never reached `Group.SetStream` arrive there anyway and pass.
    Measured with that call removed, this reads `Spotify` and fails — Snapserver leaves a group on the
    departed stream until something moves it.

    It covers the id-versus-label class by effect for the same reason. `Group.SetStream` takes the stream
    name, which is the source *id*; sending the label `'Spotify Connect'` mis-routes with no error, and the
    group then reads as anything but `PlexAmp`.
    """
    await index._enable_source(page, SPOTIFY)
    await index._enable_source(page, PLEXAMP)

    assign_group(listening_player, SPOTIFY.id)
    assert await_settled_group(listening_player) == SPOTIFY.id, 'the group never reached the stream it is moved off'

    await index._disable_source(page, SPOTIFY, PLEXAMP.id)

    assert _failures(notifications) == []
    assert SPOTIFY.id not in _conf_stream_ids()
    assert await_settled_group(listening_player) == PLEXAMP.id


async def test_the_running_streams_match_the_conf_on_disk(page, notifications, slow_conf_write):
    """The streams Snapserver serves match the conf on disk, which a restart before the write would not.

    Both sides of the equality are read from outside `index`: the ids out of the file itself, and the
    status from Snapserver over its own client. The claim is that the server is serving what the file says
    rather than that the UI believes it applied a change.

    `slow_conf_write` is what makes a reordering fail deterministically. Undilated, a reordered
    `toggle.apply` still passes: `systemctl restart` returns once systemd has forked, milliseconds before
    Snapserver opens its configuration, and a write issued on the next line wins that race on a fast
    container almost every time. The reordered code is racily wrong, and a Pi Zero 2 W is the machine that
    loses the race. An outcome assertion cannot deterministically catch a race, so the fixture widens the
    interval until the outcome is decided by the order alone. Measured both directions: reordered and
    dilated, this fails on the stream set; correctly ordered and dilated, it passes.

    Asserted after an enable and again after a disable, because the two write the conf from different sets,
    `set_enabled`'s return in one direction and the remainder in the other, and a stale read-back would
    only show on one of them.
    """
    await index._enable_source(page, SPOTIFY)

    assert _failures(notifications) == []
    assert set(_conf_stream_ids()) == {AIRPLAY.id, SPOTIFY.id}
    assert set(await_stream_status()) == {AIRPLAY.id, SPOTIFY.id}

    await index._disable_source(page, SPOTIFY, None)

    assert _failures(notifications) == []
    assert set(_conf_stream_ids()) == {AIRPLAY.id}
    assert set(await_stream_status()) == {AIRPLAY.id}


async def test_the_last_enabled_source_is_refused_without_touching_the_host(page, notifications):
    """The guard's effect on the host, which is that nothing moves.

    `CATALOG`'s rule 2 gives the reason: `getDefaultStream()` returns `nullptr` for an empty stream list and
    Snapserver dereferences it at the first client connect, so a zero-stream conf crashes the server.
    `render_snapserver()` raises rather than emitting one, so a refusal that reached the conf write would
    fail loudly. The failure this asserts against is the quieter one where the units move first and the
    render then raises.

    The conf's `st_mtime_ns` rather than its contents, because a rewrite of the identical bytes is still a
    rewrite of `/etc/`, and `nqptp`'s `MainPID` alongside Snapserver's because the units are the step that
    would run before the render raised.
    """
    assert index._enabled_ids() == [AIRPLAY.id]
    mtime = Path(conf.SNAPSERVER_CONF).stat().st_mtime_ns
    snapserver_pid = unit_state('snapserver')['MainPID']
    nqptp_pid = unit_state('nqptp')['MainPID']
    assert nqptp_pid != '0', 'nqptp is not running, so its pid could not change'

    await index._disable_source(page, AIRPLAY, None)

    assert _failures(notifications) == []
    assert (index._LAST_SOURCE_MESSAGE, 'warning') in notifications
    assert Path(conf.SNAPSERVER_CONF).stat().st_mtime_ns == mtime
    assert unit_state('snapserver')['MainPID'] == snapserver_pid
    assert unit_state('nqptp')['MainPID'] == nqptp_pid
    assert index._enabled_ids() == [AIRPLAY.id]


async def test_a_second_toggle_waits_for_the_first(page, notifications):
    """`_CHOREOGRAPHY_LOCK` against a real restart, which is what it exists to serialize.

    Two enables are gathered, so the second contends. Interleaved, they would render the conf twice and
    restart twice with the second restart landing inside the first's `_await_snapserver`, which the lock's
    own comment says it prevents.

    `MainPID` is sampled rather than compared either side, because one restart and ten look identical from
    the endpoints. Three distinct values is the baseline instance plus one restart per choreography; two
    would mean the toggles collapsed into a single restart and one source was applied to a server that
    never reloaded.

    Non-interleaving in the notification list is the mutual-exclusion assertion, and it is deterministic.
    An uncontended `asyncio.Lock.acquire()` does not yield, so the first coroutine `gather` schedules holds
    the lock before the second runs, and neither handler awaits between releasing it and its own `enabled`
    notification, so a serialized pair cannot produce these four messages in any other order. The messages
    are matched on the catalog's labels rather than on `index`'s f-strings, so rewording a notification does
    not fail this.
    """
    with sampling_main_pid('snapserver') as main_pids:
        await asyncio.gather(index._enable_source(page, SPOTIFY), index._enable_source(page, PLEXAMP))

    assert _failures(notifications) == []
    assert len(main_pids) == 3, f'snapserver did not restart exactly twice: {main_pids}'

    messages = [message for message, _ in notifications]
    assert len(messages) == 4, messages
    spotify = [position for position, message in enumerate(messages) if SPOTIFY.label in message]
    plexamp = [position for position, message in enumerate(messages) if PLEXAMP.label in message]
    assert len(spotify) == 2 and len(plexamp) == 2, messages
    assert max(spotify) < min(plexamp), messages

    assert set(_conf_stream_ids()) == {AIRPLAY.id, SPOTIFY.id, PLEXAMP.id}
    assert set(await_stream_status()) == {AIRPLAY.id, SPOTIFY.id, PLEXAMP.id}
    assert process_tree(int(unit_state('plexamp')['MainPID']))


@pytest.mark.parametrize('unit', UNITS_UNDER_A_STOP_BUDGET)
def test_every_audera_unit_stops_within_the_seams_budget(unit: str):
    """No unit may take longer to stop than the seam that stops it is willing to wait.

    `os/dietpi/lib/streamer.sh`'s `write_streamer_units` sets the budget and says why. The comparison is
    against `system.TIMEOUT` rather than against the literal five seconds, so raising or lowering the seam's
    budget moves what this asserts.

    `LoadState` first, because `systemctl show` answers for a unit that does not exist with empty values,
    and an empty `TimeoutStopUSec` is what a typo in the unit list looks like.
    """
    state = unit_state(unit)
    assert state['LoadState'] == 'loaded', f'{unit} is not loaded: {state}'
    assert _seconds(state['TimeoutStopUSec']) < system.TIMEOUT


def test_the_manager_default_would_exceed_the_seams_budget():
    """The `TimeoutStopSec` override in `streamer.sh` is load-bearing.

    Without this, the assertions above are satisfiable by a manager whose default already fits. The default
    is six times the seam's budget, which is the gap those lines close.

    The value is asserted as well as the comparison, so a manager that shipped a different default fails
    here rather than only on the inequality.
    """
    default = _manager_default('DefaultTimeoutStopUSec')

    assert default == '1min 30s'
    assert _seconds(default) > system.TIMEOUT


def test_a_wedged_backend_is_killed_inside_the_budget(wedged_nqptp):
    """A SIGTERM-proof backend is escalated to SIGKILL inside the seam's timeout.

    This was a measured defect. A backend that ignored SIGTERM made `systemctl disable --now` outlive the
    seam, 90 seconds against a 15-second `subprocess.run`, raising `TimeoutExpired`, which
    `system.systemctl` does not catch, so `_disable_source`'s `except Exception` fired and the
    `restart snapserver` after it never ran, leaving the conf and the running server divergent with no path
    back.

    The escalation is asserted as an interval from both sides. Below `system.TIMEOUT` because that is the
    budget, and at or above the unit's own `TimeoutStopUSec` because that is what shows systemd had to
    escalate to SIGKILL: a stub that died on SIGTERM would return in milliseconds and satisfy the upper
    bound while testing nothing. The lower bound is read from the unit rather than restated, so it is the
    budget provisioning wrote.

    The process table is checked afterwards for the reason
    `test_stop_leaves_no_process_and_no_zombie` gives: a SIGKILL systemd did not wait for leaves the backend
    alive and the unit `inactive`, and `MainPID=0` would report that as a clean stop.

    The unit ends `failed` rather than `inactive`, which is systemd recording that it had to force the stop,
    and that is the state the UI reads. Both `_plexamp_state` and the Sources tab go through `is_active`,
    which answers False for `failed`, so a forced stop presents as "not running" rather than as an error the
    operator has to clear.
    """
    budget = _seconds(unit_state(wedged_nqptp)['TimeoutStopUSec'])
    before = await_pids(STUBBORN_BACKEND)
    zombies_before = zombies_for()
    assert before, 'the wedged stub is not running, so nothing here would need killing'

    started = time.monotonic()
    system.systemctl('disable', '--now', wedged_nqptp)
    elapsed = time.monotonic() - started

    assert budget <= elapsed < system.TIMEOUT, f'{elapsed}s against a {budget}s budget'
    assert still_alive(before) == {}
    assert await_no_new_zombies(zombies_before) == []
    assert unit_state(wedged_nqptp)['ActiveState'] == 'failed'
    assert unit_state(wedged_nqptp)['MainPID'] == '0'
    assert system.is_active(wedged_nqptp) is False


def test_snapserver_takes_the_managers_start_limit():
    """The limit `toggle.apply`'s `reset-failed` works around is still reachable.

    `snapserver.service` states no `StartLimit*` of its own and so inherits the manager's, which records the
    rejected alternative: clearing the counter was chosen over `StartLimitIntervalSec=0` on the unit, and a
    later change that took the other route would leave `toggle.apply`'s `reset-failed` reading as a
    superstition with nothing failing. `camilladsp.service` already carries that line, so it is not a
    hypothetical edit.

    Reachability is a rate rather than a count. One toggle is one restart, so
    `StartLimitBurst / StartLimitIntervalSec` is the sustained toggles per second systemd will accept, and
    against a manager whose default were in the hundreds the `reset-failed` would be moot. The size of
    `CATALOG` does not bound it: three switches cannot supply five distinct toggles, but a toggle need not
    be distinct. Flipping one source off and on is two, and an operator who changes their mind twice about a
    source has spent four.
    """
    state = unit_state('snapserver')

    assert state['StartLimitBurst'] == _manager_default('DefaultStartLimitBurst')
    assert state['StartLimitIntervalUSec'] == _manager_default('DefaultStartLimitIntervalUSec')

    interval = _seconds(state['StartLimitIntervalUSec'])
    assert interval > 0, 'the limit is disabled, so nothing here is reachable'
    assert int(state['StartLimitBurst']) / interval < _OPERATOR_TOGGLES_PER_SECOND, 'the limit is faster than an operator'


async def test_a_toggle_revives_a_snapserver_the_start_limit_wedged(page, notifications):
    """A toggle that lands on a rate-limited Snapserver applies, rather than reporting a failure.

    Each toggle restarts Snapserver, `snapserver.service` carries `Restart=on-failure` and so takes the
    manager's five starts per ten seconds, and the sixth toggle inside that window is refused. The unit is
    then `failed`, port 1780 is closed, every source chip reads down, and audio has stopped. The manager will
    not retry, since `Restart=on-failure` is what the limit refused.

    Driven from an already-wedged server rather than by six toggles in a row, because the six-toggle version
    can go vacuous: if the handlers are slow enough that the calls straddle the interval, the counter ages
    out and the last toggle is accepted for a reason unrelated to the code under test. Wedging with raw
    restarts makes the precondition an assertion, since `_wedge_start_limit` confirms `start-limit-hit`
    before returning, and the deadline it returns fails the test as inconclusive if the assertion arrives
    after the window.

    Without `toggle.apply`'s `reset-failed`, the `systemctl restart snapserver` at the end of the handler
    raises, `_disable_source`'s `except Exception` reports it, and `_failures` is non-empty.
    """
    inconclusive_after = _wedge_start_limit('snapserver')
    assert stream_status() == {}, 'the wedged Snapserver is still answering, so it is not down'

    await index._enable_source(page, SPOTIFY)

    assert time.monotonic() < inconclusive_after, 'the start-limit window elapsed before the assertion'
    assert _failures(notifications) == []
    state = unit_state('snapserver')
    assert state['ActiveState'] == 'active', f'the toggle did not revive Snapserver: {state}'
    assert set(await_stream_status()) == {AIRPLAY.id, SPOTIFY.id}


async def test_a_toggle_starts_a_source_unit_the_start_limit_wedged(page, notifications):
    """The same limit against a source's own units, the half `snapserver` alone would miss.

    `reset-failed` covers `(*source.units, 'snapserver')` rather than just the server, because the units are
    startable from the tab too: PlexAmp is one switch and two units, so toggling it off and on three times is
    six starts each. Audera does not own `nqptp`'s unit file, so a per-unit `StartLimitIntervalSec=0` could
    not have covered it at all.

    PlexAmp rather than AirPlay because the baseline leaves its units disabled and stopped, so the enable
    below is a real `enable --now` against a unit systemd is refusing to start. AirPlay is already running,
    and a `reset-failed` on a running unit would show nothing.
    """
    inconclusive_after = _wedge_start_limit('plexamp')

    await index._enable_source(page, PLEXAMP)

    assert time.monotonic() < inconclusive_after, 'the start-limit window elapsed before the assertion'
    assert _failures(notifications) == []
    state = unit_state('plexamp')
    assert state['ActiveState'] == 'active', f'the toggle did not start plexamp: {state}'
    assert state['UnitFileState'] == 'enabled'
    assert process_tree(int(state['MainPID']))
