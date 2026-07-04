"""Audera streamer dashboard pages"""

import asyncio
import os
import socket
import subprocess
import uuid
from importlib.metadata import version as _pkg_version
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from nicegui import ui

import audera
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import dsp as dsp_dal
from audera.dal import settings as settings_dal
from audera.models.dsp import DSPConfig, apply_loudness, remove_loudness
from audera.models.settings import Settings
from audera.ui import components, features

load_dotenv()

_PLEX_CLIENT_ID = str(uuid.uuid4())
_PLEX_HEADERS = {
    'X-Plex-Product': audera.NAME,
    'X-Plex-Version': _pkg_version('audera'),
    'X-Plex-Client-Identifier': _PLEX_CLIENT_ID,
    'X-Plex-Platform': 'Linux',
    'Accept': 'application/json',
}


def _load_settings() -> Settings:
    return settings_dal.get_or_create(
        Settings(
            plexamp_host=os.getenv('AUDERA_PLEXAMP_HOST', 'localhost'),
            snapserver_host=os.getenv('AUDERA_SNAPSERVER_HOST', 'localhost'),
            features=features.default_selections(),
        )
    )


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


def _camilladsp(host: str) -> CamillaDSPClient:
    """Returns a CamillaDSPClient for the given player host."""
    return CamillaDSPClient(host=host)


def _plexamp_state() -> Literal['inactive', 'unclaimed', 'claimed']:
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'plexamp'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip() != 'active':
            return 'inactive'
    except Exception:
        return 'inactive'
    try:
        with socket.create_connection(('127.0.0.1', audera.PLEXAMP_PORT), timeout=1):
            return 'claimed'
    except OSError:
        return 'unclaimed'


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
    subprocess.run(['systemctl', 'stop', 'plexamp'], timeout=15, check=True)
    override_dir = '/etc/systemd/system/plexamp.service.d'
    os.makedirs(override_dir, exist_ok=True)
    with open(f'{override_dir}/claim.conf', 'w') as f:
        f.write(f'[Service]\nEnvironment=PLEXAMP_CLAIM_TOKEN={claim_token}\n')
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10, check=True)
    subprocess.run(['systemctl', 'start', 'plexamp'], timeout=10, check=True)


def _remove_claim_override() -> None:
    override = '/etc/systemd/system/plexamp.service.d/claim.conf'
    if os.path.exists(override):
        os.remove(override)
    subprocess.run(['systemctl', 'daemon-reload'], timeout=10)


class Page:
    """A `class` that represents the streamer dashboard app."""

    def __init__(self):
        """Initializes an instance of the streamer dashboard app."""
        self.settings = _load_settings()
        self._client = _snapserver(self.settings)
        self._dialog_open: bool = False

    def load(self) -> None:
        """Registers page routes."""
        ui.page('/')(self.index)

    def index(self) -> None:
        """Renders the main dashboard page."""
        components.header.render(audera.NAME, 'Streamer')

        with ui.tabs().classes('w-full') as tabs:
            players_tab = ui.tab('Players')
            services_tab = ui.tab('Services')
            settings_tab = ui.tab('Settings')

        with ui.tab_panels(tabs, value=players_tab).classes('w-full'):
            with ui.tab_panel(players_tab):
                self._build_players_tab()  # type: ignore
            with ui.tab_panel(services_tab):
                self._build_services_tab()  # type: ignore
            with ui.tab_panel(settings_tab):
                self._build_settings_tab()

        def _maybe_refresh():
            if not self._dialog_open:
                self._build_players_tab.refresh()

        ui.timer(10.0, _maybe_refresh)

    @ui.refreshable
    def _build_services_tab(self) -> None:
        """Renders the Services tab — shows PlexAmp status and a browser-based OAuth claiming flow."""
        state = _plexamp_state()

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

                    deadline = asyncio.get_event_loop().time() + 300  # 5-minute timeout
                    poll_timer: list[ui.timer] = []

                    async def _poll_auth():
                        if asyncio.get_event_loop().time() > deadline:
                            poll_timer[0].cancel()
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
                            status_label.set_text(f'Claim failed: {exc}')
                            connect_btn.enable()
                            return

                        status_label.set_text('PlexAmp restarting…')

                        port_deadline = asyncio.get_event_loop().time() + 120
                        port_timer: list[ui.timer] = []

                        async def _poll_port():
                            if asyncio.get_event_loop().time() > port_deadline:
                                port_timer[0].cancel()
                                _remove_claim_override()
                                status_label.set_text('PlexAmp did not come up in time. Check the service.')
                                connect_btn.enable()
                                return

                            if _plexamp_state() == 'claimed':
                                port_timer[0].cancel()
                                _remove_claim_override()
                                self._build_services_tab.refresh()

                        port_timer.append(ui.timer(2.0, _poll_port))

                    poll_timer.append(ui.timer(2.0, _poll_auth))

                connect_btn.on('click', _on_connect)

    @ui.refreshable
    def _build_players_tab(self) -> None:
        """Renders the Players tab — lists Snapcast clients with per-client volume and mute/enable controls."""
        snap = _snapserver(self.settings)
        try:
            clients = snap.get_clients()
        except Exception:
            clients = []

        connected_clients = [c for c in clients if c.connected]
        if not connected_clients:
            ui.label('No Snapcast clients found.').classes('text-gray-500')
            return

        disabled_experience = features.flag_enabled(self.settings, features.PLAYER_SELECTION_KEY, features.FF_DISABLED_VS_MUTE)

        for client in connected_clients:
            minimized = disabled_experience and client.muted
            with ui.card().classes('w-full mb-2'):
                with ui.row().classes('items-center justify-between w-full'):
                    with ui.row().classes('items-center gap-2'):
                        if disabled_experience:
                            ui.switch(value=not client.muted, on_change=lambda e, c=client: self._on_enabled_change(c, e.value))
                        ui.label(client.name).classes('font-medium')
                    ui.button(on_click=lambda c=client: self._open_settings_dialog(c)).props(
                        'icon=edit_square flat dense round size=sm'
                    ).classes('text-gray-400').mark('player-settings')

                if minimized:
                    continue

                with ui.row().classes('items-center gap-4 w-full'):
                    host = client.host
                    dsp_config = dsp_dal.get_or_create(DSPConfig(id=client.id, player_id=client.id))
                    init_vol = dsp_config.volume
                    try:
                        _camilladsp(host).set_percent_volume(init_vol)
                    except Exception:
                        pass
                    self._build_volume_controls(
                        client.id,
                        dsp_config,
                        init_vol,
                        client.muted,
                        client.host,
                        show_mute=not disabled_experience,
                    )

    async def _on_enabled_change(self, client, enabled: bool) -> None:
        """Handles the 'disabled' Player Selection experience's enable/disable switch.

        Toggling off mutes the Snapcast client (the minimized-card state is derived from
        `client.muted` on the next render); toggling on unmutes it.
        """
        await asyncio.to_thread(_snapserver(self.settings).set_client_volume, client.id, 100, muted=not enabled)
        self._build_players_tab.refresh()

    def _open_settings_dialog(self, client) -> None:
        """Opens a settings popup for renaming, latency, and Snapcast volume reset."""
        self._dialog_open = True
        dsp_config = dsp_dal.get_or_create(DSPConfig(id=client.id, player_id=client.id))

        with ui.dialog() as dialog, ui.card().classes('w-96'):
            ui.label('Settings').classes('font-medium text-lg mb-2')

            name_input = ui.input('Name', value=client.name).classes('w-full')
            latency_input = ui.number('Latency (ms)', value=client.latency_ms, min=-500, max=500, step=1).classes('w-full')

            # Snapcast volume is a sidecar kept at 100/0; CamillaDSP controls actual loudness.
            snap_vol = client.volume
            with ui.row().classes('w-full items-start justify-between mt-2'):
                with ui.column().classes('gap-0'):
                    ui.label('Snapcast Volume').classes('text-xs')
                    current_vol_label = ui.label(f'Current Volume {snap_vol}%').classes('text-xs text-gray-500')
                ui.button('Reset', on_click=lambda c=client, lbl=current_vol_label: self._reset_snap_volume(c, lbl)).props(
                    'dense'
                ).classes('bg-gray-800 text-white')

            ui.separator().classes('mt-2 mb-2')
            ui.label('DSP').classes('text-sm font-medium')

            with ui.row().classes('w-full items-center justify-between mt-1'):
                with ui.column().classes('gap-0'):
                    ui.label('Loudness').classes('text-xs')
                    _iso226_url = 'https://cdn.standards.iteh.ai/samples/83117/6afa5bd94e0e4f32812c28c3b0a7b8ac/ISO-226-2023.pdf'
                    ui.html(
                        f'See international standard ISO 226, '
                        f'<a href="{_iso226_url}" target="_blank" class="underline">reference</a>'
                    ).classes('text-xs text-gray-500')
                loudness_switch = ui.switch(
                    value=dsp_config.loudness_enabled,
                    on_change=lambda e: ref_input.set_enabled(e.value),
                )

            ref_input = ui.number(
                'Reference level (dB)',
                value=dsp_config.loudness_reference_level,
                min=-60.0,
                max=0.0,
                step=0.5,
            ).classes('w-full')
            ref_input.set_enabled(dsp_config.loudness_enabled)

            ui.separator().classes('mt-4 mb-2')
            with ui.column().classes('text-xs text-gray-500 gap-1'):
                ui.label(f'ID      {client.id}')
                ui.label(f'Host    {client.host}')
                ui.label(f'Group   {client.group_id or "—"}')

            with ui.row().classes('justify-between w-full mt-4'):

                def _on_cancel():
                    self._dialog_open = False
                    dialog.close()

                async def _on_save(c=client, ni=name_input, li=latency_input):
                    snap = _snapserver(self.settings)
                    if ni.value and ni.value != c.name:
                        snap.set_client_name(c.id, ni.value)
                        ui.notify(f'Renamed to "{ni.value}"', type='positive', position='top-right')
                    if int(li.value) != c.latency_ms:
                        snap.set_client_latency(c.id, int(li.value))
                        ui.notify(f'Latency set to {int(li.value)} ms', type='positive', position='top-right')

                    loudness_on = loudness_switch.value
                    reference_level = float(ref_input.value)
                    if loudness_on and not (-60.0 <= reference_level <= 0.0):
                        ui.notify('Reference level must be between -60 and 0 dB.', type='negative', position='top-right')
                        return
                    if loudness_on != dsp_config.loudness_enabled or reference_level != dsp_config.loudness_reference_level:
                        cdsp = _camilladsp(c.host)
                        pipeline = await asyncio.to_thread(cdsp.get_config)
                        if loudness_on:
                            pipeline = apply_loudness(remove_loudness(pipeline), reference_level)
                        else:
                            pipeline = remove_loudness(pipeline)
                        await asyncio.to_thread(cdsp.set_config, pipeline)
                        dsp_config.loudness_enabled = loudness_on
                        dsp_config.loudness_reference_level = reference_level
                        dsp_dal.update(dsp_config)

                    self._dialog_open = False
                    dialog.close()
                    self._build_players_tab.refresh()

                ui.button('Cancel', on_click=_on_cancel).props('flat dense')
                ui.button('Save', on_click=_on_save).props('dense').classes('bg-gray-800 text-white')

        dialog.on('hide', lambda: setattr(self, '_dialog_open', False))
        dialog.open()

    def _reset_snap_volume(self, client, vol_label=None) -> None:
        """Resets the Snapcast client volume to 100% / unmuted.

        If vol_label is provided (from the settings dialog), its text is updated to
        reflect the new value. The players tab is *not* refreshed so that the CamillaDSP
        volume sliders retain their current visual state.
        """
        _snapserver(self.settings).set_client_volume(client.id, 100, muted=False)
        if vol_label is not None:
            vol_label.set_text('Current Volume 100%')
        ui.notify('Snapcast volume reset to 100%', type='positive', position='top-right')

    def _build_volume_controls(
        self,
        client_id: str,
        dsp_config: DSPConfig,
        initial_volume: int,
        initial_muted: bool,
        client_host: str = '',
        show_mute: bool = True,
    ) -> None:
        """Renders volume slider (routed through CamillaDSP) and, when `show_mute`, a mute checkbox (Snapcast).

        `show_mute=False` is used by the 'disabled' Player Selection experience, where the
        enable/disable switch in the card header already governs Snapcast mute state, so
        the redundant Mute checkbox — and its enabled/disabled binding — is omitted.
        """

        async def _on_volume(e):
            percent = int(e.value)
            camilla = _camilladsp(client_host) if client_host else _camilladsp('localhost')
            try:
                await asyncio.to_thread(camilla.set_percent_volume, percent)
            except Exception:
                pass
            dsp_dal.update(dsp_config.model_copy(update={'volume': percent}))
            await asyncio.to_thread(
                _snapserver(self.settings).set_client_volume,
                client_id,
                0 if percent == 0 else 100,
                muted=(percent == 0),
            )

        async def _on_mute(e):
            await asyncio.to_thread(_snapserver(self.settings).set_client_volume, client_id, 100, muted=e.value)

        slider = ui.slider(min=0, max=100, value=initial_volume, on_change=_on_volume).classes('w-48')
        if show_mute:
            mute_cb = ui.checkbox('Mute', value=initial_muted, on_change=_on_mute)
            slider.bind_enabled_from(mute_cb, 'value', backward=lambda v: not v)

    def _build_settings_tab(self) -> None:
        """Renders the Settings tab — one single-select button group per registered UX feature."""
        ui.label('Features').classes('text-lg font-medium mb-2')
        for feature in features.FEATURES:
            ui.label(feature.label).classes('text-sm text-gray-500')
            ui.toggle(
                {option.value: option.label for option in feature.options},
                value=features.selected(self.settings, feature.key),
                on_change=lambda e, key=feature.key: self._on_feature_change(key, e.value),
            ).classes('mb-4')

    def _on_feature_change(self, key: str, value: str) -> None:
        """Persists a feature-flag selection and refreshes the Players tab to reflect it."""
        self.settings.features[key] = value
        settings_dal.save(self.settings)
        self._build_players_tab.refresh()
