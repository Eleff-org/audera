"""Integration tests for the streamer dashboard UI."""

import asyncio

import pytest
from nicegui import core, ui
from nicegui.client import Client
from nicegui.testing import User

import audera.ui.streamer.pages as streamer_pages
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import dsp as dsp_dal
from audera.dal import settings as settings_dal
from audera.models.player import Player
from audera.ui import components, features
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


@pytest.fixture
def mock_camilladsp(monkeypatch):
    calls = {}

    def _set_percent_volume(self, percent: int) -> None:
        calls['set_percent_volume'] = percent

    def _get_percent_volume(self) -> int:
        calls['get_percent_volume'] = True
        return 80

    monkeypatch.setattr(CamillaDSPClient, 'set_percent_volume', _set_percent_volume)
    monkeypatch.setattr(CamillaDSPClient, 'get_percent_volume', _get_percent_volume)
    return calls


@pytest.fixture
def mock_camilladsp_config(monkeypatch):
    calls = {}

    def _get_config(self):
        return {'filters': {}, 'pipeline': []}

    def _set_config(self, config):
        calls['set_config'] = config

    monkeypatch.setattr(CamillaDSPClient, 'get_config', _get_config)
    monkeypatch.setattr(CamillaDSPClient, 'set_config', _set_config)
    return calls


@pytest.fixture
def mock_snapserver_volume(monkeypatch):
    calls = {}

    def _set_client_volume(self, client_id: str, percent: int, muted: bool = False):
        calls['set_client_volume'] = (client_id, percent, muted)

    monkeypatch.setattr(SnapserverClient, 'set_client_volume', _set_client_volume)
    return calls


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


async def test_settings_tab_shows_feature_groups(audera_home, mock_snapserver_empty, user: User):
    Page().load()
    await user.open('/')
    user.find('Settings').click()
    for feature in features.FEATURES:
        await user.should_see(feature.label)
        for option in feature.options:
            await user.should_see(option.label)
    await user.should_not_see('PlexAmp Host')
    await user.should_not_see('Snapserver Host')


async def test_settings_tab_selecting_option_persists_to_dal(audera_home, mock_snapserver_empty, user: User):
    """ui.toggle renders as a single q-btn-toggle group; the test harness's generic
    click() doesn't know how to target one button within it (unlike ui.radio/ui.select,
    which it special-cases), so the option is selected the same way the harness selects
    those: by assigning the element's `value` directly, which drives the same on_change
    path a real button click would.
    """
    Page().load()
    await user.open('/')
    user.find('Settings').click()
    with user:
        user.find(kind=ui.toggle, content='Disabled toggle').elements.pop().value = 'disabled'
    await asyncio.sleep(0.1)
    assert settings_dal.get().features['player_selection'] == 'disabled'
    with user:
        user.find(kind=ui.toggle, content='Decibels').elements.pop().value = 'db'
    await asyncio.sleep(0.1)
    assert settings_dal.get().features['volume'] == 'db'


async def test_settings_first_load_seeds_default_features(audera_home, mock_snapserver_empty, user: User):
    Page().load()
    await user.open('/')
    assert settings_dal.get().features == features.default_selections()


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


async def test_volume_slider_seeded_from_dal(
    audera_home,
    mock_snapserver_with_client,
    mock_camilladsp,
    monkeypatch,
    user: User,
):
    monkeypatch.setattr(streamer_pages, '_camilladsp', lambda h: CamillaDSPClient(h))
    Page().load()
    await user.open('/')
    # Volume is read from DAL (default 25) and pushed to CamillaDSP via set_percent_volume
    assert mock_camilladsp.get('set_percent_volume') == 25


async def test_reset_snap_volume_calls_snapserver(
    audera_home,
    mock_snapserver_with_client,
    mock_snapserver_volume,
    user: User,
):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    user.find('Reset').click()
    await user.should_see('Snapcast volume reset to 100%')
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 100, False)


async def test_reset_snap_volume_button(audera_home, mock_snapserver_with_client, monkeypatch, user: User):
    """Player settings dialog contains Snapcast Volume control with Reset button."""
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    await user.should_see('Snapcast Volume')


async def test_settings_dialog_shows_loudness_controls(audera_home, mock_snapserver_with_client, user: User):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    await user.should_see('Loudness')
    await user.should_see('Reference level (dB)')


async def test_loudness_toggle_enables_and_persists(
    audera_home,
    mock_snapserver_with_client,
    mock_camilladsp_config,
    user: User,
):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    user.find(kind=ui.switch).click()
    await asyncio.sleep(0.1)
    assert mock_camilladsp_config.get('set_config') is None
    user.find('Save').click()
    await asyncio.sleep(0.1)
    assert mock_camilladsp_config.get('set_config') is not None
    assert dsp_dal.get(mock_snapserver_with_client.id).loudness_enabled is True


async def test_loudness_toggle_passes_reference_level_to_config(
    audera_home,
    mock_snapserver_with_client,
    mock_camilladsp_config,
    user: User,
):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    user.find(kind=ui.switch).click()
    await asyncio.sleep(0.1)
    assert mock_camilladsp_config.get('set_config') is None
    user.find('Save').click()
    await asyncio.sleep(0.1)
    config = mock_camilladsp_config.get('set_config')
    assert config is not None
    params = config['filters']['audera_loudness']['parameters']
    assert params['reference_level'] == -25.0
