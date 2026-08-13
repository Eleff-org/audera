"""Unit tests for streamer dirty fan-out: Sources only on stream_status change."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import audera.ui.streamer as streamer
from audera.ui.streamer import broker as broker_mod


def _page(*, dialog_open: bool = False):
    page = SimpleNamespace(
        _dialog_open=dialog_open,
        _deferred_tabs=set(),
        _build_players_tab=MagicMock(),
        _build_sources_tab=MagicMock(),
    )
    page._build_players_tab.refresh = MagicMock()
    page._build_sources_tab.refresh = MagicMock()
    return page


def test_on_dirty_refreshes_sources_only_when_stream_status_changes(monkeypatch):
    b = broker_mod.EventBroker('127.0.0.1', 1780)
    b.cache.stream_status = {'AirPlay': 'idle'}
    monkeypatch.setattr(broker_mod, '_broker', b)
    monkeypatch.setattr(streamer, '_prev_stream_status', (('AirPlay', 'idle'),))

    page = _page()
    monkeypatch.setattr(streamer, 'connected_pages', lambda: [(MagicMock(), page)])

    # Volume-only dirty: stream map unchanged.
    streamer._on_dirty()
    page._build_players_tab.refresh.assert_called_once()
    page._build_sources_tab.refresh.assert_not_called()

    page._build_players_tab.refresh.reset_mock()
    b.cache.stream_status = {'AirPlay': 'idle', 'Spotify': 'idle'}
    streamer._on_dirty()
    page._build_players_tab.refresh.assert_called_once()
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
    assert page._deferred_tabs == {'players', 'sources'}
