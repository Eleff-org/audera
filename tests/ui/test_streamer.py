"""Integration tests for the streamer dashboard UI."""

import pytest
from nicegui import core
from nicegui.client import Client
from nicegui.testing import User

import audera.ui.streamer.pages as streamer_pages
from audera.clients import SnapserverClient
from audera.dal import settings as settings_dal
from audera.models.player import Player
from audera.ui import components
from audera.ui.streamer.pages import Page


@pytest.fixture
def mock_snapserver_empty(monkeypatch):
    def _raise(self):
        raise ConnectionRefusedError()

    monkeypatch.setattr(SnapserverClient, 'get_clients', _raise)


@pytest.fixture
def mock_snapserver_with_client(monkeypatch):
    player = Player(id='abc123', host='192.168.1.50', port=1704, connected=True, volume=80, name='Living Room')

    monkeypatch.setattr(SnapserverClient, 'get_clients', lambda self: [player])
    return player


async def test_index_renders_tabs(audera_home, mock_snapserver_empty, monkeypatch, user: User):
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'inactive')
    Page().load()
    await user.open('/')
    await user.should_see('Players')
    await user.should_see('Services')
    await user.should_see('Settings')


async def test_players_tab_shows_empty_state(audera_home, mock_snapserver_empty, user: User):
    Page().load()
    await user.open('/')
    await user.should_see('No Snapcast clients found.')


async def test_players_tab_shows_connected_client(audera_home, mock_snapserver_with_client, user: User):
    Page().load()
    await user.open('/')
    await user.should_see('Living Room')


async def test_players_tab_shows_latency_control(audera_home, mock_snapserver_with_client, user: User):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    await user.should_see('Latency (ms)')


async def test_services_tab_shows_inactive(audera_home, mock_snapserver_empty, monkeypatch, user: User):
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'inactive')
    Page().load()
    await user.open('/')
    user.find('Services').click()
    await user.should_see('inactive')


async def test_services_tab_shows_unclaimed(audera_home, mock_snapserver_empty, monkeypatch, user: User):
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'inactive')
    Page().load()
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'unclaimed')
    await user.open('/')
    user.find('Services').click()
    await user.should_see('setup required')
    await user.should_see('Connect with Plex')


async def test_services_tab_shows_claimed(audera_home, mock_snapserver_empty, monkeypatch, user: User):
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'claimed')
    Page().load()
    await user.open('/')
    user.find('Services').click()
    await user.should_see('available')


async def test_settings_tab_shows_host_inputs(audera_home, mock_snapserver_empty, user: User):
    Page().load()
    await user.open('/')
    user.find('Settings').click()
    await user.should_see('PlexAmp Host')
    await user.should_see('Snapserver Host')


async def test_settings_save_persists_hosts(audera_home, mock_snapserver_empty, user: User):
    Page().load()
    await user.open('/')
    user.find('Settings').click()
    user.find('PlexAmp Host').clear().type('192.168.1.100')
    user.find('Snapserver Host').clear().type('192.168.1.101')
    user.find('Save').click()
    settings = settings_dal.get()
    assert settings.plexamp_host == '192.168.1.100'
    assert settings.snapserver_host == '192.168.1.101'


async def test_run_preamble_does_not_set_script_mode(audera_home, monkeypatch, user: User):
    """Page.load() followed by apply_defaults() must not set core.script_mode=True.

    In production Client.instances is empty when run() executes.  If apply_defaults()
    calls ui.colors() (a NiceGUI Element), NiceGUI activates script_mode and
    ui.run() raises: RuntimeError: ui.page cannot be used in NiceGUI scripts when
    UI is defined in the global scope.
    """
    monkeypatch.setattr(streamer_pages, '_plexamp_state', lambda: 'inactive')
    Page().load()
    Client.instances.clear()  # replicate production: no pre-existing clients
    components.theme.apply_defaults()
    assert not core.script_mode, (
        'apply_defaults() triggered script_mode via ui.colors(). '
        'Use app.colors() for application-wide theming instead of ui.colors().'
    )
