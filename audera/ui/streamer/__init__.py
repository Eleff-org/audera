"""Audera app"""

import asyncio

from nicegui import app, ui

import audera
from audera.dal import settings as settings_dal
from audera.dal import sources as sources_dal
from audera.dal import volume as volume_dal
from audera.settings import settings
from audera.ui import components
from audera.ui.streamer import broker, commands
from audera.ui.streamer.pages import Page, connected_pages
from audera.ui.streamer.pages._clients import _load_settings

_loop: asyncio.AbstractEventLoop | None = None
# Last stream_status delivered to Sources via dirty fan-out. Volume/name-only dirties must not
# rebuild Sources (that cancels the Plex claim flow's timers); only a stream map change does.
_prev_stream_status: tuple[tuple[str, str], ...] = ()


def _stream_status_key() -> tuple[tuple[str, str], ...]:
    try:
        return tuple(sorted(broker.get().cache.stream_status.items()))
    except AssertionError:
        return ()


def _on_dirty() -> None:
    """Fan-out: rebuild Players on every dirty; rebuild Sources only when stream_status changed."""
    global _prev_stream_status
    stream_key = _stream_status_key()
    streams_changed = stream_key != _prev_stream_status
    if streams_changed:
        _prev_stream_status = stream_key

    for client, page in connected_pages():
        if page._dialog_open:
            page._deferred_tabs.add('players')
            if streams_changed:
                page._deferred_tabs.add('sources')
            continue
        with client:
            page._build_players_tab.refresh()
            if streams_changed:
                page._build_sources_tab.refresh()


def _on_sources_changed() -> None:
    """Refresh Sources + Players tabs on every connected client after a sources DAL write."""
    if _loop is None:
        return

    def _apply():
        for client, page in connected_pages():
            if page._dialog_open:
                page._deferred_tabs.update(('sources', 'players'))
                continue
            with client:
                page._build_sources_tab.refresh()
                page._build_players_tab.refresh()

    _loop.call_soon_threadsafe(_apply)


def _on_settings_changed() -> None:
    """Reload settings and refresh Players + Settings tabs on every connected client."""
    if _loop is None:
        return
    new_settings = _load_settings()

    def _apply():
        for client, page in connected_pages():
            page.settings = new_settings.model_copy(deep=True)
            if page._dialog_open:
                page._deferred_tabs.update(('players', 'settings'))
                continue
            with client:
                page._build_players_tab.refresh()
                page._build_settings_tab.refresh()

    _loop.call_soon_threadsafe(_apply)


def _on_volume_changed() -> None:
    """Push DAL volumes into the broker cache so NiceGUI bindings propagate to sliders."""
    if _loop is None:
        return
    try:
        b = broker.get()
    except AssertionError:
        return
    cached = volume_dal.get_all()

    def _apply():
        for player_id, percent in cached.items():
            b.cache.volumes[player_id] = percent

    _loop.call_soon_threadsafe(_apply)


def _start() -> None:
    global _loop, _prev_stream_status
    _loop = asyncio.get_event_loop()
    broker.start(settings.snapserver_host, audera.SNAPSERVER_PORT)
    commands.start()
    _prev_stream_status = _stream_status_key()
    broker.get().on_dirty(_on_dirty)
    sources_dal.on_change(_on_sources_changed)
    settings_dal.on_change(_on_settings_changed)
    volume_dal.on_change(_on_volume_changed)


def run() -> None:
    """Runs the Audera app."""
    page = Page()
    page.load()

    components.theme.apply_defaults()

    app.on_startup(_start)
    app.on_shutdown(commands.stop)
    app.on_shutdown(broker.stop)

    try:
        ui.run(host=settings.server_host, port=settings.server_port, title=audera.NAME.capitalize(), show=False, reload=False)
    except KeyboardInterrupt:
        app.shutdown()
