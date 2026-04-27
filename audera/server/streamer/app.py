"""Audera streamer NiceGUI webserver"""

import os
import re
import subprocess
from typing import Optional

from dotenv import load_dotenv
from nicegui import ui

import audera
from audera.dal import settings as settings_dal
from audera.models.settings import Settings
from audera.services.snapserver import SnapserverClient

load_dotenv()


def _load_settings() -> Settings:
    if settings_dal.exists():
        return settings_dal.get_settings()
    return Settings(
        plexamp_host=os.getenv('AUDERA_PLEXAMP_HOST', 'localhost'),
        snapserver_host=os.getenv('AUDERA_SNAPSERVER_HOST', 'localhost'),
    )


def _snapserver(settings: Settings) -> SnapserverClient:
    return SnapserverClient(host=settings.snapserver_host, port=audera.SNAPSERVER_PORT)


def _plexamp_status() -> str:
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', 'plexamp'],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return 'unknown'


def _plexamp_claim_url() -> Optional[str]:
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'plexamp', '-n', '200', '--no-pager', '-o', 'cat'],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r'https://plex\.tv/claim/\S+', result.stdout)
        return match.group(0) if match else None
    except Exception:
        return None


def _build_services_tab():
    """Renders the Services tab — shows status and claim URL for background services."""
    status = _plexamp_status()
    with ui.card().classes('w-full mb-2'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label('PlexAmp Headless').classes('font-medium')
            ui.label(status).classes('text-sm ' + ('text-green-500' if status == 'active' else 'text-red-500'))
        claim_url = _plexamp_claim_url()
        if claim_url:
            ui.label('Claim this player:').classes('text-sm text-gray-500 mt-1')
            ui.link(claim_url, claim_url).classes('text-sm break-all')
        elif status == 'active':
            ui.link('Open PlexAmp', 'https://plexamp.local').classes('text-sm mt-1')


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
                ui.label(client.host).classes('font-medium')
                ui.label(
                    '%s%s'
                    % (
                        group_map.get(client.group_id, client.group_id),
                        '' if client.connected else ' (disconnected)',
                    )
                ).classes('text-sm text-gray-500')
            with ui.row().classes('items-center gap-4'):
                ui.slider(
                    min=0,
                    max=100,
                    value=client.volume,
                    on_change=lambda e, cid=client.id, m=client.muted: _snapserver(settings_).set_client_volume(
                        cid, int(e.value), m
                    ),
                ).classes('w-48')
                ui.checkbox(
                    'Mute',
                    value=client.muted,
                    on_change=lambda e, cid=client.id, v=client.volume: _snapserver(settings_).set_client_volume(
                        cid, v, e.value
                    ),
                )


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
