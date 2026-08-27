"""Unit tests for streamer dirty fan-out: Sources only on stream_status change."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import audera.ui.streamer as streamer
from audera.dal import volume as volume_dal
from audera.ui.streamer import broker as broker_mod


class _InlineLoop:
    """Fake event loop whose ``call_soon_threadsafe`` runs the callback inline."""

    def call_soon_threadsafe(self, fn):
        fn()


def _page(*, dialog_open: bool = False):
    page = SimpleNamespace(
        _dialog_open=dialog_open,
        _deferred_tabs=set(),
        _build_players_tab=MagicMock(),
        _build_sources_tab=MagicMock(),
        _build_settings_tab=MagicMock(),
    )
    page._build_players_tab.refresh = MagicMock()
    page._build_sources_tab.refresh = MagicMock()
    page._build_settings_tab.refresh = MagicMock()
    return page


def test_on_dirty_refreshes_sources_only_when_stream_status_changes(monkeypatch):
    b = broker_mod.EventBroker('127.0.0.1', 1780)
    b.cache.stream_status = {'AirPlay': 'idle'}
    monkeypatch.setattr(broker_mod, '_broker', b)
    monkeypatch.setattr(streamer, '_prev_stream_status', (('AirPlay', 'idle'),))

    page = _page()
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    # Volume-only dirty: stream map unchanged. Players and Settings still rebuild.
    streamer._on_dirty()
    page._build_players_tab.refresh.assert_called_once()
    page._build_settings_tab.refresh.assert_called_once()
    page._build_sources_tab.refresh.assert_not_called()

    page._build_players_tab.refresh.reset_mock()
    page._build_settings_tab.refresh.reset_mock()
    b.cache.stream_status = {'AirPlay': 'idle', 'Spotify': 'idle'}
    streamer._on_dirty()
    page._build_players_tab.refresh.assert_called_once()
    page._build_settings_tab.refresh.assert_called_once()
    page._build_sources_tab.refresh.assert_called_once()
    assert streamer._prev_stream_status == (('AirPlay', 'idle'), ('Spotify', 'idle'))


def test_on_dirty_defers_sources_when_dialog_open(monkeypatch):
    b = broker_mod.EventBroker('127.0.0.1', 1780)
    b.cache.stream_status = {'AirPlay': 'playing'}
    monkeypatch.setattr(broker_mod, '_broker', b)
    monkeypatch.setattr(streamer, '_prev_stream_status', (('AirPlay', 'idle'),))

    page = _page(dialog_open=True)
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_dirty()
    page._build_players_tab.refresh.assert_not_called()
    page._build_sources_tab.refresh.assert_not_called()
    page._build_settings_tab.refresh.assert_not_called()
    assert page._deferred_tabs == {'players', 'sources', 'settings'}


def test_on_balance_changed_refreshes_settings_on_every_page(monkeypatch):
    monkeypatch.setattr(streamer, '_loop', _InlineLoop())
    page = _page()
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_balance_changed()
    page._build_settings_tab.refresh.assert_called_once()
    page._build_players_tab.refresh.assert_not_called()
    page._build_sources_tab.refresh.assert_not_called()


def test_on_balance_changed_defers_settings_when_dialog_open(monkeypatch):
    monkeypatch.setattr(streamer, '_loop', _InlineLoop())
    page = _page(dialog_open=True)
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_balance_changed()
    page._build_settings_tab.refresh.assert_not_called()
    assert page._deferred_tabs == {'settings'}


def test_on_balance_changed_noop_without_loop(monkeypatch):
    monkeypatch.setattr(streamer, '_loop', None)
    page = _page()
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_balance_changed()
    page._build_settings_tab.refresh.assert_not_called()


def test_on_volume_changed_pushes_cache_and_refreshes_settings(monkeypatch):
    b = broker_mod.EventBroker('127.0.0.1', 1780)
    monkeypatch.setattr(broker_mod, '_broker', b)
    monkeypatch.setattr(streamer, '_loop', _InlineLoop())
    monkeypatch.setattr(volume_dal, 'get_all', lambda: {'player-1': 50})

    page = _page()
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_volume_changed()
    assert b.cache.volumes['player-1'] == 50
    page._build_settings_tab.refresh.assert_called_once()
    page._build_players_tab.refresh.assert_not_called()


def test_on_volume_changed_defers_settings_when_dialog_open(monkeypatch):
    b = broker_mod.EventBroker('127.0.0.1', 1780)
    monkeypatch.setattr(broker_mod, '_broker', b)
    monkeypatch.setattr(streamer, '_loop', _InlineLoop())
    monkeypatch.setattr(volume_dal, 'get_all', lambda: {'player-1': 50})

    page = _page(dialog_open=True)
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    streamer._on_volume_changed()
    assert b.cache.volumes['player-1'] == 50
    page._build_settings_tab.refresh.assert_not_called()
    assert page._deferred_tabs == {'settings'}
