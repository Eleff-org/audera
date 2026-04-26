""" Audera streamer NiceGUI webserver """

import os

from dotenv import load_dotenv
from nicegui import ui

import audera
from audera.dal import settings as settings_dal
from audera.dal import streams as streams_dal
from audera.models.settings import Settings
from audera.services.plexamp import PlexAmpClient
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


def _plexamp(settings: Settings) -> PlexAmpClient:
    return PlexAmpClient(host=settings.plexamp_host)


def _build_streams_tab(settings_: Settings):
    """ Renders the Streams tab — shows now-playing info with play/pause/skip controls. """
    client = _plexamp(settings_)
    try:
        now_playing = client.get_now_playing()
    except Exception:
        now_playing = None

    if now_playing is None:
        ui.label('Nothing is currently playing.').classes('text-gray-500')
        return

    with ui.card().classes('w-full mb-2'):
        with ui.row().classes('items-center justify-between w-full'):
            ui.label(now_playing.current_track or now_playing.name).classes('font-medium')
            ui.label(now_playing.status).classes('text-sm text-gray-500')
        with ui.row().classes('gap-2'):
            ui.button('Play', on_click=lambda: _plexamp(settings_).play('')).props('flat dense')
            ui.button('Pause', on_click=lambda: _plexamp(settings_).pause('')).props('flat dense')
            ui.button('Skip', on_click=lambda: _plexamp(settings_).skip('')).props('flat dense')


def _build_groups_tab(settings_: Settings):
    """ Renders the Groups tab — lists Snapcast groups with stream assignment and mute/volume controls. """
    snap = _snapserver(settings_)
    try:
        snap_groups = snap.get_groups()
        all_streams = streams_dal.get_all_streams()
    except Exception:
        snap_groups = []
        all_streams = []

    stream_options = {s.id: s.name for s in all_streams}

    if not snap_groups:
        ui.label('No Snapcast groups found.').classes('text-gray-500')
        return

    for group in snap_groups:
        with ui.card().classes('w-full mb-2'):
            ui.label(group.name or group.id).classes('font-medium')
            with ui.row().classes('items-center gap-4 flex-wrap'):
                ui.select(
                    options=stream_options,
                    value=group.stream_id or None,
                    label='Stream',
                    on_change=lambda e, gid=group.id: _snapserver(settings_).set_group_stream(gid, e.value),
                ).classes('w-48')
                ui.checkbox(
                    'Mute',
                    value=group.muted,
                    on_change=lambda e, gid=group.id: _snapserver(settings_).set_group_mute(gid, e.value),
                )
                ui.label('Volume: %d%%' % group.volume)


def _build_players_tab(settings_: Settings):
    """ Renders the Players tab — lists Snapcast clients with per-client volume and mute controls. """
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
                    '%s%s' % (
                        group_map.get(client.group_id, client.group_id),
                        '' if client.connected else ' (disconnected)',
                    )
                ).classes('text-sm text-gray-500')
            with ui.row().classes('items-center gap-4'):
                ui.slider(
                    min=0,
                    max=100,
                    value=client.volume,
                    on_change=lambda e, cid=client.id, m=client.muted: (
                        _snapserver(settings_).set_client_volume(cid, int(e.value), m)
                    ),
                ).classes('w-48')
                ui.checkbox(
                    'Mute',
                    value=client.muted,
                    on_change=lambda e, cid=client.id, v=client.volume: (
                        _snapserver(settings_).set_client_volume(cid, v, e.value)
                    ),
                )


def _build_settings_tab(settings_: Settings):
    """ Renders the Settings tab — configure service hosts and persist to ~/.audera/settings.json. """
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
        streams_tab = ui.tab('Streams')
        groups_tab = ui.tab('Groups')
        players_tab = ui.tab('Players')
        settings_tab = ui.tab('Settings')

    with ui.tab_panels(tabs, value=streams_tab).classes('w-full'):
        with ui.tab_panel(streams_tab):
            _build_streams_tab(settings_)
        with ui.tab_panel(groups_tab):
            _build_groups_tab(settings_)
        with ui.tab_panel(players_tab):
            _build_players_tab(settings_)
        with ui.tab_panel(settings_tab):
            _build_settings_tab(settings_)


def run():
    """ Starts the Audera streamer NiceGUI webserver. """
    ui.run(host='0.0.0.0', port=audera.SERVER_PORT, title=audera.NAME, reload=False)
