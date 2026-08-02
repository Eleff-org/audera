"""PlexAmp status probing and the browser-OAuth claim/pin flow for the streamer UI."""

import asyncio
import os
import socket
import subprocess
import time
import uuid
from importlib.metadata import version as _pkg_version
from typing import TYPE_CHECKING, Literal, Optional

import httpx
from nicegui import ui

import audera
from audera import io
from audera.dal import sources as sources_dal
from audera.services import system

if TYPE_CHECKING:
    from audera.ui.streamer.pages import Page

# The claim token is passed through a systemd drop-in because PlexAmp consumes it once at
# process start.
PLEXAMP_CLAIM_CONF: str = '/etc/systemd/system/plexamp.service.d/claim.conf'

# The catalog id this flow sets up, which is what a completed claim is recorded against in
# `sources.json`. Stated here rather than passed in, because everything else in this module names
# PlexAmp's units and URLs outright too. A `SourceDefinition.id` is immutable, so this cannot
# drift; `tests/ui/test_streamer.py` pins it against the catalog.
SOURCE_ID: str = 'PlexAmp'

# Where the operator's browser reaches PlexAmp. `settings.plexamp_host` is the address the server
# dials from the device, so it is `localhost` on a real streamer and a link rendered from it sends
# the browser to its own machine. Provisioning publishes this name over mDNS
# (`plexamp-mdns.service`), carries it in the TLS SAN, and gives it an nginx vhost proxying to
# `127.0.0.1:32500`, so the vhost is reachable whatever address PlexAmp itself binds.
PLEXAMP_URL: str = 'https://plexamp.local'

# How long after systemd reports the unit active a closed port still means "not up yet" rather
# than "never claimed". PlexAmp binds 32500 only once it holds a claim, so a closed port is both
# the evidence of an unclaimed device and what a claimed device looks like while it boots. The
# unit's `ExecStartPre` waits up to 60 s for plex.tv to resolve before node starts, so a shorter
# window reports a claimed device as unclaimed on every restart. A longer one delays the claim
# button for an operator who has just enabled PlexAmp for the first time.
STARTUP_GRACE: float = 90

# The chip label and panel selector for that window. Returned by `setup_state()`; the label
# doubles as the discriminator the panel switches on.
STARTING: str = 'starting'

# The label for every other incomplete state: never claimed, or a unit that is not running at
# all. Both leave the operator the same next action, so they render the same word.
SETUP_REQUIRED: str = 'setup required'

# How often the starting panel re-probes. The Sources tab is otherwise unpolled; see
# `_build_starting_panel`.
_STARTING_POLL: float = 5

_PLEX_CLIENT_ID = str(uuid.uuid4())
_PLEX_HEADERS = {
    'X-Plex-Product': audera.NAME,
    'X-Plex-Version': _pkg_version('audera'),
    'X-Plex-Client-Identifier': _PLEX_CLIENT_ID,
    'X-Plex-Platform': 'Linux',
    'Accept': 'application/json',
}


def _active_seconds() -> Optional[float]:
    """Returns how long the `plexamp` unit has been active, or `None` when systemd will not say.

    Read from `ActiveEnterTimestampMonotonic` rather than `ActiveEnterTimestamp`: systemd's
    monotonic timestamps and `time.monotonic()` are both `CLOCK_MONOTONIC` on Linux, so they
    share the boot epoch and subtract directly. The wall-clock field is a locale- and
    timezone-formatted string that would have to be parsed.

    The reading survives a stop. systemd retains it for as long as the unit stays *loaded*,
    whether the stop was clean or the unit failed, and `reset-failed` clears it only for a unit
    that is actually `failed`. It reads `0` only for a unit that has been dropped, is unknown, or
    has not run since being loaded, so the `0` handled below is loadedness rather than exit
    status. A caller reasoning about a stopped unit is reading how long ago it last came up.
    """
    try:
        # Unchecked, since every non-answer is handled below as `None`, and a unit that has
        # never been active reports `0` on exit 0.
        result = system.systemctl('show', 'plexamp', '-p', 'ActiveEnterTimestampMonotonic', '--value', check=False)
    except (RuntimeError, subprocess.SubprocessError, OSError):
        return None
    raw = result.stdout.strip()
    if not raw.isdigit():
        return None
    started = int(raw)
    if not started:
        return None
    elapsed = time.monotonic() - started / 1_000_000
    # A negative reading means the two clocks do not share an epoch, so the window is
    # meaningless; withhold it.
    return elapsed if elapsed >= 0 else None


def _plexamp_state() -> Literal['inactive', 'starting', 'unclaimed', 'claimed']:
    try:
        if not system.is_active('plexamp'):
            return 'inactive'
    except RuntimeError:
        # Off-device the platform gate raises, so a dev-box render of this tab reports
        # `'inactive'` rather than tracebacking.
        return 'inactive'
    try:
        with socket.create_connection(('127.0.0.1', audera.PLEXAMP_PORT), timeout=1):
            return 'claimed'
    except OSError:
        pass

    # systemd calls the unit active as soon as it forks node, well before node binds, and a
    # refused connection returns immediately either way. Elapsed time since activation is what
    # separates a starting PlexAmp from an unclaimed one.
    elapsed = _active_seconds()
    return 'starting' if elapsed is not None and elapsed < STARTUP_GRACE else 'unclaimed'


def _create_plex_pin() -> tuple[int, str]:
    resp = httpx.post(
        'https://plex.tv/api/v2/pins',
        params={'strong': 'true'},
        headers=_PLEX_HEADERS,
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['id'], data['code']


def _poll_plex_pin(pin_id: int) -> Optional[str]:
    resp = httpx.get(
        f'https://plex.tv/api/v2/pins/{pin_id}',
        headers=_PLEX_HEADERS,
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json().get('authToken') or None


def _get_claim_token(auth_token: str) -> str:
    resp = httpx.get(
        'https://plex.tv/api/claim/token.json',
        headers={**_PLEX_HEADERS, 'X-Plex-Token': auth_token},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()['token']


def _restart_plexamp_with_claim(claim_token: str) -> None:
    system.systemctl('stop', 'plexamp')
    # `0o600`: the drop-in carries a plex.tv claim token, which grants whoever holds it a claim on
    # the operator's server. Only the systemd manager, which runs as root, has to read it.
    io.write_text(PLEXAMP_CLAIM_CONF, f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={claim_token}\n', mode=0o600)
    # Load-bearing only for a unit that stayed loaded across the stop, which is the state a device
    # submits a claim from. A stopped *disabled* unit is garbage-collected, and systemd loads it
    # fresh on the next reference with any drop-in included, so the token would reach the
    # environment with no reload at all; an *enabled* unit is referenced by `multi-user.target` and
    # stays loaded, so without this the start below re-execs the pre-claim command line.
    system.systemctl('daemon-reload')
    system.systemctl('start', 'plexamp')


def _remove_claim_override() -> None:
    if os.path.exists(PLEXAMP_CLAIM_CONF):
        os.remove(PLEXAMP_CLAIM_CONF)
    # Unchecked: the override file is already gone, so a failed reload does not need to abort
    # the caller.
    system.systemctl('daemon-reload', check=False)


def setup_complete() -> bool:
    """Returns whether PlexAmp is claimed.

    The `PLEXAMP_CLAIM_CONF` drop-in is deleted on success and on timeout alike, so its absence
    is the steady state for both "never claimed" and "claimed"; a file predicate would report
    every claimed device as `setup required` forever.

    `_plexamp_state` is resolved as a module global on each call so the test seam
    (`monkeypatch.setattr(_plex, '_plexamp_state', …)`) keeps working.
    """
    return _plexamp_state() == 'claimed'


def setup_state() -> Optional[str]:
    """Returns the chip label for `setup='plex_claim'`, or `None` once the claim is done.

    A label rather than a boolean because the flow has two incomplete states with different words
    and different panels: a PlexAmp still coming up after a restart has nothing for the operator
    to do, and an unclaimed one does.
    """
    state = _plexamp_state()
    if state == 'claimed':
        return None
    return STARTING if state == 'starting' else SETUP_REQUIRED


def build_setup_panel(page: 'Page', pending: Optional[str]) -> None:
    """Renders PlexAmp's post-enable panel on its Sources-tab card.

    Parameters
    ----------
    page: `audera.ui.streamer.pages.Page`
        An instance of the streamer dashboard app.
    pending: `Optional[str]`
        The chip label from `setup_state()`, resolved once by the caller so the chip and the
        panel cannot disagree within a render.
    """
    if pending is None:
        ui.link('Open PlexAmp', PLEXAMP_URL).classes('text-sm mt-1')
        return
    if pending == STARTING:
        _build_starting_panel(page)
        return
    _build_claim_flow(page)


def _build_starting_panel(page: 'Page') -> None:
    """Renders the panel for a PlexAmp that systemd has started but that has not bound its port yet.

    No claim button: within the startup window a closed port is not evidence of an unclaimed
    device.

    This timer is the Sources tab's one poll. `_plexamp_state` stops reporting `'starting'` once
    the port opens or `STARTUP_GRACE` passes, and the refresh that replaces the panel deletes the
    timer with it. The probe runs off-thread because it shells out to `systemctl` twice.

    Parameters
    ----------
    page: `audera.ui.streamer.pages.Page`
        An instance of the streamer dashboard app.
    """
    label = ui.label('PlexAmp is starting…').classes('text-sm text-gray-500 mt-1')
    timer: list[ui.timer] = []

    async def _poll_started() -> None:
        # The tab was refreshed out from under the panel; stop rather than refresh it again.
        if label.is_deleted:
            timer[0].cancel()
            return
        if await asyncio.to_thread(_plexamp_state) == 'starting':
            return
        timer[0].cancel()
        page._build_sources_tab.refresh()

    timer.append(ui.timer(_STARTING_POLL, _poll_started))


def _build_claim_flow(page: 'Page') -> None:
    """Renders the browser-OAuth pin/claim flow that turns an unclaimed PlexAmp into a claimed one.

    Parameters
    ----------
    page: `audera.ui.streamer.pages.Page`
        An instance of the streamer dashboard app.
    """
    connect_btn = ui.button('Connect with Plex').classes('mt-2').mark('plex-connect')
    status_label = ui.label('').classes('text-sm text-gray-500 mt-1')
    auth_link = ui.link("Didn't open? Click here to authorize with Plex", '#', new_tab=True).classes('text-sm mt-1')
    auth_link.set_visibility(False)

    async def _on_connect():
        connect_btn.disable()
        status_label.set_text('Opening Plex authorization…')

        try:
            pin_id, pin_code = await asyncio.to_thread(_create_plex_pin)
        except Exception as exc:
            status_label.set_text(f'Error: {exc}')
            connect_btn.enable()
            return

        auth_url = (
            f'https://app.plex.tv/auth/#!?clientID={_PLEX_CLIENT_ID}'
            f'&code={pin_code}'
            f'&context%5Bdevice%5D%5Bproduct%5D={audera.NAME}'
        )
        ui.navigate.to(auth_url, new_tab=True)
        status_label.set_text('Waiting for Plex authorization…')
        auth_link.props(f'href="{auth_url}"')
        auth_link.set_visibility(True)

        # A refresh of the Sources tab deletes these elements and cancels the timers below
        # with them, so the flow is in flight from here until a terminal state. The Sources tab
        # reads the flag to refuse a toggle that would abandon an OAuth in progress; every
        # terminal path clears it.
        page._claim_in_flight = True

        deadline = asyncio.get_event_loop().time() + 300  # 5-minute timeout
        poll_timer: list[ui.timer] = []

        async def _poll_auth():
            # The tab was refreshed out from under the flow; stop polling rather than write
            # to a deleted label.
            if status_label.is_deleted:
                poll_timer[0].cancel()
                return

            if asyncio.get_event_loop().time() > deadline:
                poll_timer[0].cancel()
                page._claim_in_flight = False
                status_label.set_text('Authorization timed out. Please try again.')
                connect_btn.enable()
                return

            try:
                auth_token = await asyncio.to_thread(_poll_plex_pin, pin_id)
            except Exception:
                return  # transient error; retry on next tick

            if not auth_token:
                return

            poll_timer[0].cancel()
            status_label.set_text('Authorized. Claiming PlexAmp…')

            try:
                claim_token = await asyncio.to_thread(_get_claim_token, auth_token)
                await asyncio.to_thread(_restart_plexamp_with_claim, claim_token)
            except Exception as exc:
                # A failed `systemctl` reports the reason in `stderr`; `CalledProcessError`'s
                # `__str__` is only the argv and the exit status. `getattr` because the other
                # call in this block raises `httpx` errors, which carry no `stderr` and whose
                # `__str__` is the useful part.
                detail = (getattr(exc, 'stderr', '') or str(exc)).strip()
                page._claim_in_flight = False
                status_label.set_text(f'Claim failed: {detail}')
                connect_btn.enable()
                return

            status_label.set_text('PlexAmp restarting…')

            port_deadline = asyncio.get_event_loop().time() + 120
            port_timer: list[ui.timer] = []

            async def _poll_port():
                if status_label.is_deleted:
                    port_timer[0].cancel()
                    return

                # Both branches below shell out: `_plexamp_state()` runs `systemctl` (bounded by
                # `system.TIMEOUT`) and then opens a socket, and `_remove_claim_override()` runs
                # `systemctl` again, so a synchronous call would block the event loop for up to
                # half a minute every 2 s.
                if asyncio.get_event_loop().time() > port_deadline:
                    port_timer[0].cancel()
                    page._claim_in_flight = False
                    await asyncio.to_thread(_remove_claim_override)
                    status_label.set_text('PlexAmp did not come up in time. Check the service.')
                    connect_btn.enable()
                    return

                if await asyncio.to_thread(setup_complete):
                    port_timer[0].cancel()
                    page._claim_in_flight = False
                    # Recorded before the override is removed, so a failure removing it still
                    # leaves the claim recorded. This is the moment the claim is known to have
                    # worked; the live probe that detected it reads `unclaimed` again the moment
                    # provisioning stops the unit, and the record is what stops the tab asking a
                    # second time for a claim that already happened.
                    await asyncio.to_thread(sources_dal.set_setup_complete, SOURCE_ID, True)
                    await asyncio.to_thread(_remove_claim_override)
                    page._build_sources_tab.refresh()

            port_timer.append(ui.timer(2.0, _poll_port))

        poll_timer.append(ui.timer(2.0, _poll_auth))

    connect_btn.on('click', _on_connect)
