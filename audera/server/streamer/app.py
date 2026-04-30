"""Audera streamer NiceGUI webserver"""

import asyncio
import json
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
from audera.dal import settings as settings_dal
from audera.models.settings import Settings
from audera.services.snapserver import SnapserverClient

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
    if settings_dal.exists():
        return settings_dal.get_settings()
    return Settings(
        plexamp_host=os.getenv('AUDERA_PLEXAMP_HOST', 'localhost'),
        snapserver_host=os.getenv('AUDERA_SNAPSERVER_HOST', 'localhost'),
    )


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


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


@ui.refreshable
def _build_services_tab():
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
                            _build_services_tab.refresh()

                    port_timer.append(ui.timer(2.0, _poll_port))

                poll_timer.append(ui.timer(2.0, _poll_auth))

            connect_btn.on('click', _on_connect)


def _build_volume_controls(client_id: str, initial_volume: int, initial_muted: bool, settings_: Settings):
    """Renders volume slider and mute checkbox with live cross-references to avoid stale closure bugs."""

    def _on_volume(e):
        _snapserver(settings_).set_client_volume(client_id, int(e.value), mute_cb.value)

    def _on_mute(e):
        _snapserver(settings_).set_client_volume(client_id, int(slider.value), e.value)

    slider = ui.slider(min=0, max=100, value=initial_volume, on_change=_on_volume).classes('w-48')
    mute_cb = ui.checkbox('Mute', value=initial_muted, on_change=_on_mute)


def _build_players_tab(settings_: Settings):
    """Renders the Players tab — lists Snapcast clients with per-client volume and mute controls."""
    snap = _snapserver(settings_)
    try:
        clients = snap.get_clients()
        snap_groups = snap.get_groups()
    except Exception:
        clients = []
        snap_groups = []

    group_map = {g.id: g.name or g.id for g in snap_groups}

    if not clients:
        ui.label('No Snapcast clients found.').classes('text-gray-500')
        return

    for client in clients:
        with ui.card().classes('w-full mb-2'):
            with ui.row().classes('items-center justify-between w-full'):
                ui.label(client.name).classes('font-medium')
                with ui.row().classes('items-center gap-2'):
                    ui.label(
                        '%s%s'
                        % (
                            group_map.get(client.group_id, client.group_id),
                            '' if client.connected else ' (disconnected)',
                        )
                    ).classes('text-sm text-gray-500')
                    with ui.dialog() as detail_dialog, ui.card():
                        ui.label(client.name).classes('font-medium mb-2')
                        ui.code(
                            json.dumps({**client.to_dict(), 'name': client.name}, indent=2),
                            language='json',
                        ).classes('text-xs')
                        ui.button('Close', on_click=detail_dialog.close).props('flat dense').classes('mt-2')
                    ui.button(on_click=detail_dialog.open).props('icon=info flat dense round size=xs').classes(
                        'text-gray-400'
                    )
            with ui.row().classes('items-center gap-4'):
                _build_volume_controls(client.id, client.volume, client.muted, settings_)


def _build_settings_tab(settings_: Settings):
    """Renders the Settings tab — configure service hosts and persist to ~/.audera/settings.json."""
    plexamp_input = ui.input('PlexAmp Host', value=settings_.plexamp_host).classes('w-64')
    snapserver_input = ui.input('Snapserver Host', value=settings_.snapserver_host).classes('w-64')
    status_label = ui.label('').classes('text-sm text-gray-500')

    def _save():
        settings_.plexamp_host = plexamp_input.value
        settings_.snapserver_host = snapserver_input.value
        settings_dal.save(settings_)
        status_label.set_text('Settings saved.')

    ui.button('Save', on_click=_save).props('flat dense')


@ui.page('/')
def index():
    settings_ = _load_settings()

    with ui.header().classes('bg-primary text-white items-center'):
        ui.label(audera.NAME).classes('text-xl font-bold')
        ui.label('Streamer').classes('text-sm ml-2 opacity-75')

    with ui.tabs().classes('w-full') as tabs:
        players_tab = ui.tab('Players')
        services_tab = ui.tab('Services')
        settings_tab = ui.tab('Settings')

    with ui.tab_panels(tabs, value=players_tab).classes('w-full'):
        with ui.tab_panel(players_tab):
            _build_players_tab(settings_)
        with ui.tab_panel(services_tab):
            _build_services_tab()
        with ui.tab_panel(settings_tab):
            _build_settings_tab(settings_)


def run():
    """Starts the Audera streamer NiceGUI webserver."""
    ui.run(host='0.0.0.0', port=audera.SERVER_PORT, title=audera.NAME, reload=False)
