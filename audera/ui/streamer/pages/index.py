"""Audera app index"""

import asyncio
from typing import TYPE_CHECKING

from nicegui import ui

import audera
from audera.clients import CamillaDSPClient
from audera.dal import settings as settings_dal
from audera.ui import components, features
from audera.ui.streamer.pages import _plex
from audera.ui.streamer.pages._clients import _camilladsp, _snapserver

if TYPE_CHECKING:
    from audera.ui.streamer.pages import Page


def render(page: 'Page') -> None:
    """Renders the main dashboard page."""
    components.header.render(audera.NAME, 'Streamer')

    with ui.tabs().classes('w-full') as tabs:
        players_tab = ui.tab('Players')
        services_tab = ui.tab('Services')
        settings_tab = ui.tab('Settings')

    with ui.tab_panels(tabs, value=players_tab).classes('w-full'):
        with ui.tab_panel(players_tab):
            page._build_players_tab()  # type: ignore
        with ui.tab_panel(services_tab):
            page._build_services_tab()  # type: ignore
        with ui.tab_panel(settings_tab):
            _build_settings_tab(page)

    def _maybe_refresh():
        if not page._dialog_open:
            page._build_players_tab.refresh()

    ui.timer(10.0, _maybe_refresh)


def build_services_tab(page: 'Page') -> None:
    """Renders the Services tab — shows PlexAmp status and a browser-based OAuth claiming flow.

    Called by `Page._build_services_tab`, the `@ui.refreshable` method that owns the refresh
    target (so refreshes are keyed per `Page` instance).
    """
    state = _plex._plexamp_state()

    with ui.card().classes('w-full mb-2'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('PlexAmp Headless').classes('font-medium')
            if state == 'claimed':
                ui.label('available').classes('text-sm text-green-500')
            elif state == 'unclaimed':
                ui.label('setup required').classes('text-sm text-amber-500')
            else:
                ui.label('inactive').classes('text-sm text-red-500')

        if state == 'claimed':
            ui.link('Open PlexAmp', 'https://plexamp.local').classes('text-sm mt-1')

        elif state == 'unclaimed':
            connect_btn = ui.button('Connect with Plex').classes('mt-2')
            status_label = ui.label('').classes('text-sm text-gray-500 mt-1')
            auth_link = ui.link("Didn't open? Click here to authorize with Plex", '#', new_tab=True).classes('text-sm mt-1')
            auth_link.set_visibility(False)

            async def _on_connect():
                connect_btn.disable()
                status_label.set_text('Opening Plex authorization…')

                try:
                    pin_id, pin_code = await asyncio.to_thread(_plex._create_plex_pin)
                except Exception as exc:
                    status_label.set_text(f'Error: {exc}')
                    connect_btn.enable()
                    return

                auth_url = (
                    f'https://app.plex.tv/auth/#!?clientID={_plex._PLEX_CLIENT_ID}'
                    f'&code={pin_code}'
                    f'&context%5Bdevice%5D%5Bproduct%5D={audera.NAME}'
                )
                ui.navigate.to(auth_url, new_tab=True)
                status_label.set_text('Waiting for Plex authorization…')
                auth_link.props(f'href="{auth_url}"')
                auth_link.set_visibility(True)

                deadline = asyncio.get_event_loop().time() + 300  # 5-minute timeout
                poll_timer: list[ui.timer] = []

                async def _poll_auth():
                    if asyncio.get_event_loop().time() > deadline:
                        poll_timer[0].cancel()
                        status_label.set_text('Authorization timed out. Please try again.')
                        connect_btn.enable()
                        return

                    try:
                        auth_token = await asyncio.to_thread(_plex._poll_plex_pin, pin_id)
                    except Exception:
                        return  # transient error; retry on next tick

                    if not auth_token:
                        return

                    poll_timer[0].cancel()
                    status_label.set_text('Authorized. Claiming PlexAmp…')

                    try:
                        claim_token = await asyncio.to_thread(_plex._get_claim_token, auth_token)
                        await asyncio.to_thread(_plex._restart_plexamp_with_claim, claim_token)
                    except Exception as exc:
                        status_label.set_text(f'Claim failed: {exc}')
                        connect_btn.enable()
                        return

                    status_label.set_text('PlexAmp restarting…')

                    port_deadline = asyncio.get_event_loop().time() + 120
                    port_timer: list[ui.timer] = []

                    async def _poll_port():
                        if asyncio.get_event_loop().time() > port_deadline:
                            port_timer[0].cancel()
                            _plex._remove_claim_override()
                            status_label.set_text('PlexAmp did not come up in time. Check the service.')
                            connect_btn.enable()
                            return

                        if _plex._plexamp_state() == 'claimed':
                            port_timer[0].cancel()
                            _plex._remove_claim_override()
                            page._build_services_tab.refresh()

                    port_timer.append(ui.timer(2.0, _poll_port))

                poll_timer.append(ui.timer(2.0, _poll_auth))

            connect_btn.on('click', _on_connect)


def build_players_tab(page: 'Page') -> None:
    """Renders the Players tab — lists Snapcast clients with per-client volume and mute/enable controls.

    Called by `Page._build_players_tab`, the `@ui.refreshable` method that owns the refresh
    target (so refreshes are keyed per `Page` instance).
    """
    snap = _snapserver(page.settings)
    try:
        clients = snap.get_clients()
    except Exception:
        clients = []

    connected_clients = [c for c in clients if c.connected]
    if not connected_clients:
        ui.label('No Snapcast clients found.').classes('text-gray-500')
        return

    # Named after the feature-flag constant so flag-gated UI is obvious to the reader.
    FF_DISABLED_VS_MUTE = features.flag_enabled(page.settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE)

    for client in connected_clients:
        minimized = FF_DISABLED_VS_MUTE and client.muted
        with ui.card().classes('w-full mb-2'):
            mute_cb = None
            with ui.row().classes('items-center justify-between w-full'):
                with ui.row().classes('items-center gap-2'):
                    if FF_DISABLED_VS_MUTE:
                        ui.switch(value=not client.muted, on_change=lambda e, c=client: _on_enabled_change(page, c, e.value))
                    # A disabled player is grayed out to reinforce the "disabled" state.
                    name_label = ui.label(client.name).classes('font-medium')
                    if minimized:
                        name_label.classes('text-gray-400')
                with ui.row().classes('items-center gap-2'):
                    if not FF_DISABLED_VS_MUTE:
                        mute_cb = ui.checkbox(
                            'Mute', value=client.muted, on_change=lambda e, c=client: _on_mute_change(page, c.id, e.value)
                        )
                    # DSP first (left), then settings (right), both plain material icons. An icon reads
                    # as clickable on its own (like the gear), and dropping the bordered circle avoids
                    # the sub-pixel oval it rendered at some viewport widths. As two icon buttons with
                    # identical props they are the same size by construction — no pixel pinning needed.
                    # `sym_o_airwave` (a Material Symbol — hence the `sym_o_` prefix) reads as sound
                    # waves, fitting the DSP page.
                    dsp_btn = (
                        ui.button(on_click=lambda c=client: ui.navigate.to(f'/player/{c.id}/dsp'))
                        .props('icon=sym_o_airwave flat dense round size=sm')
                        .mark('player-dsp')
                    )
                    # A disabled player has no live pipeline to edit, so gray out its DSP button too.
                    if minimized:
                        dsp_btn.set_enabled(False)
                    settings_btn = (
                        ui.button(on_click=lambda c=client: _open_settings_dialog(page, c))
                        .props('icon=settings flat dense round size=sm')
                        .mark('player-settings')
                    )
                    # Disable the settings button for a disabled player, matching the intent of "disable".
                    if minimized:
                        settings_btn.set_enabled(False)

            if minimized:
                continue

            with ui.row(wrap=False).classes('items-center gap-4 w-full'):
                host = client.host
                try:
                    init_vol = _camilladsp(host).get_percent_volume()
                except Exception:
                    init_vol = CamillaDSPClient.DEFAULT_PERCENT_VOLUME
                slider = _build_volume_controls(page, client.id, init_vol, client.host)
                if mute_cb is not None:
                    slider.bind_enabled_from(mute_cb, 'value', backward=lambda v: not v)


async def _on_mute_change(page: 'Page', client_id: str, muted: bool) -> None:
    """Handles the Mute checkbox in the card header for the default Player Selection experience.

    Does not refresh the Players tab afterward, so the volume slider keeps its live
    drag state — see `_reset_snap_volume` for the same rationale.
    """
    await asyncio.to_thread(_snapserver(page.settings).set_client_volume, client_id, 100, muted=muted)


async def _on_enabled_change(page: 'Page', client, enabled: bool) -> None:
    """Handles the 'disabled' Player Selection experience's enable/disable switch.

    Toggling off mutes the Snapcast client (the minimized-card state is derived from
    `client.muted` on the next render); toggling on unmutes it.
    """
    await asyncio.to_thread(_snapserver(page.settings).set_client_volume, client.id, 100, muted=not enabled)
    page._build_players_tab.refresh()


def _open_settings_dialog(page: 'Page', client) -> None:
    """Opens a settings popup for renaming, latency, and Snapcast volume reset."""
    page._dialog_open = True

    with ui.dialog() as dialog, ui.card().classes('w-96'):
        ui.label('Settings').classes('font-medium text-lg mb-2')

        name_input = ui.input('Name', value=client.name).classes('w-full')
        latency_input = (
            ui.number('Latency (ms)', value=client.latency_ms, min=-500, max=500, step=1)
            .classes('w-full')
            .props('hint="Adds playback delay."')
        )

        # Snapcast volume is a sidecar kept at 100/0; CamillaDSP controls actual loudness.
        snap_vol = client.volume
        with ui.row().classes('w-full items-start justify-between mt-2'):
            with ui.column().classes('gap-0'):
                ui.label('Snapcast Volume').classes('text-xs')
                current_vol_label = ui.label(f'Current Volume {snap_vol}%').classes('text-xs text-gray-500')
            ui.button('Reset', on_click=lambda c=client, lbl=current_vol_label: _reset_snap_volume(page, c, lbl)).props(
                'dense'
            ).classes('bg-gray-800 text-white')

        ui.separator().classes('mt-4 mb-2')
        with ui.column().classes('text-xs text-gray-500 gap-1'):
            ui.label(f'ID      {client.id}')
            ui.label(f'Host    {client.host}')
            ui.label(f'Group   {client.group_id or "—"}')

        with ui.row().classes('justify-between w-full mt-4'):

            def _on_cancel():
                page._dialog_open = False
                dialog.close()

            async def _on_save(c=client, ni=name_input, li=latency_input):
                snap = _snapserver(page.settings)
                if ni.value and ni.value != c.name:
                    snap.set_client_name(c.id, ni.value)
                    ui.notify(f'Renamed to "{ni.value}"', type='positive', position='top-right')
                if int(li.value) != c.latency_ms:
                    snap.set_client_latency(c.id, int(li.value))
                    ui.notify(f'Latency set to {int(li.value)} ms', type='positive', position='top-right')

                page._dialog_open = False
                dialog.close()
                page._build_players_tab.refresh()

            ui.button('Cancel', on_click=_on_cancel).props('flat dense')
            ui.button('Save', on_click=_on_save).props('dense').classes('bg-gray-800 text-white')

    dialog.on('hide', lambda: setattr(page, '_dialog_open', False))
    dialog.open()


def _reset_snap_volume(page: 'Page', client, vol_label=None) -> None:
    """Resets the Snapcast client volume to 100% / unmuted.

    If vol_label is provided (from the settings dialog), its text is updated to
    reflect the new value. The players tab is *not* refreshed so that the CamillaDSP
    volume sliders retain their current visual state.
    """
    _snapserver(page.settings).set_client_volume(client.id, 100, muted=False)
    if vol_label is not None:
        vol_label.set_text('Current Volume 100%')
    ui.notify('Snapcast volume reset to 100%', type='positive', position='top-right')


def _build_volume_controls(
    page: 'Page',
    client_id: str,
    initial_volume: float,
    client_host: str = '',
) -> ui.slider:
    """Renders a volume icon, slider, and live value label (routed through CamillaDSP).

    Volume is owned by the CamillaDSP daemon, which persists it durably via its
    `--statefile`; the slider seeds from the daemon (`get_percent_volume`) and writes
    through it (`set_percent_volume`) — the app keeps no replica.

    The slider is **always** a percent (0-100) control regardless of the 'volume'
    feature selection, so the handle sits at the same physical spot when toggling
    between modes. The selection only changes the value label: percent mode shows
    `NN%`, dB mode shows `percent_to_db(value)` as `-N.N dB`. Both modes drive
    CamillaDSP through `set_percent_volume`.

    Mute is anchored at the slider floor (`percent <= 0`, displayed as `MIN_DB` in dB
    mode), never on lossy zero-rounding, so a mid-range edit never silently mutes the
    client on the next refresh. The seed is step-aligned to the integer percent slider
    so the periodic refresh does not fire a phantom `update:model-value`.

    Returns the `ui.slider` element so the caller can bind its enabled state to the
    Mute checkbox built alongside it in the card header.
    """
    camilla = _camilladsp(client_host) if client_host else _camilladsp('localhost')
    # Named after the feature-flag constant so flag-gated UI is obvious to the reader.
    FF_VOLUME_PERC_OR_DB = features.flag_enabled(page.settings, features.VOLUME_KEY, features.FF_VOLUME_PERC_OR_DB)

    async def _persist_and_sync(percent: float) -> None:
        muted = percent <= 0
        await asyncio.to_thread(
            _snapserver(page.settings).set_client_volume,
            client_id,
            0 if muted else 100,
            muted=muted,
        )

    async def _on_volume_percent(e):
        percent = int(e.value)
        try:
            await asyncio.to_thread(camilla.set_percent_volume, percent)
        except Exception:
            pass
        await _persist_and_sync(percent)

    ui.icon('volume_up').classes('text-gray-400')
    slider = ui.slider(min=0, max=100, step=1, value=int(round(initial_volume)), on_change=_on_volume_percent).classes('grow')
    # Fixed width + right-align keeps the slider length constant as the label text
    # changes digit count (e.g. -9.0 dB -> -10.0 dB), so the handle doesn't shift.
    value_label = ui.label().classes('text-xs text-gray-500 shrink-0 whitespace-nowrap text-right w-16')
    if FF_VOLUME_PERC_OR_DB:
        value_label.bind_text_from(slider, 'value', backward=lambda v: f'{camilla.percent_to_db(v):.1f} dB')
    else:
        value_label.bind_text_from(slider, 'value', backward=lambda v: f'{int(v)}%')

    return slider


def _build_settings_tab(page: 'Page') -> None:
    """Renders the Settings tab — one single-select button group per registered UX feature."""
    ui.label('Features').classes('text-lg font-medium mb-2')
    for feature in features.FEATURES:
        ui.label(feature.label).classes('text-sm text-gray-500')
        ui.toggle(
            {option.value: option.label for option in feature.options},
            value=features.selected(page.settings, feature.key),
            on_change=lambda e, key=feature.key: _on_feature_change(page, key, e.value),
        ).classes('mb-4')


def _on_feature_change(page: 'Page', key: str, value: str) -> None:
    """Persists a feature-flag selection and refreshes the Players tab to reflect it."""
    page.settings.features[key] = value
    settings_dal.save(page.settings)
    page._build_players_tab.refresh()
