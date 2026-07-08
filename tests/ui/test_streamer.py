"""Integration tests for the streamer dashboard UI."""

import asyncio

import pytest
from nicegui import core, ui
from nicegui.client import Client
from nicegui.testing import User

import audera.ui.streamer.pages as streamer_pages
from audera.clients import CamillaDSPClient, SnapserverClient
from audera.dal import dsp as dsp_dal
from audera.dal import players as players_dal
from audera.dal import settings as settings_dal
from audera.models.dsp import Band, DSPConfig
from audera.models.player import Player
from audera.models.settings import Settings
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
def mock_snapserver_with_muted_client(monkeypatch):
    player = Player(id='abc123', host='192.168.1.50', port=1704, connected=True, volume=80, muted=True, name='Living Room')

    monkeypatch.setattr(SnapserverClient, 'get_clients', lambda self: [player])
    return player


@pytest.fixture
def mock_camilladsp(monkeypatch):
    # Stateful, like the real daemon: get returns the last-set percent, seeded at 80.
    # The players tab reseeds the slider from get_percent_volume on every (re-)render,
    # so a static mock would revert a drag the moment the refresh timer fires.
    calls = {}
    state = {'volume': 80}

    def _set_percent_volume(self, percent: int) -> None:
        calls['set_percent_volume'] = percent
        state['volume'] = percent

    def _get_percent_volume(self) -> int:
        calls['get_percent_volume'] = True
        return state['volume']

    def _set_volume(self, level: float) -> None:
        calls['set_volume'] = level

    monkeypatch.setattr(CamillaDSPClient, 'set_percent_volume', _set_percent_volume)
    monkeypatch.setattr(CamillaDSPClient, 'get_percent_volume', _get_percent_volume)
    monkeypatch.setattr(CamillaDSPClient, 'set_volume', _set_volume)
    return calls


@pytest.fixture
def mock_camilladsp_dsp(monkeypatch):
    """Mocks the CamillaDSP client for the Advanced DSP editor page.

    Records the Save choreography (get/validate/set config, reset clipped samples) and
    keeps the last-set config so a re-open would see the compiled pipeline. Keeps the
    tests daemon-free while `response_peak_db` still runs the real `camilladsp_plot`.
    """
    calls = {}
    state = {'config': {'devices': {'samplerate': 48000}, 'filters': {}, 'pipeline': []}}

    def _get_config(self) -> dict:
        calls['get_config'] = True
        return state['config']

    def _validate_config(self, config: dict) -> None:
        calls['validate_config'] = config

    def _set_config(self, config: dict) -> None:
        calls['set_config'] = config
        state['config'] = config

    def _get_clipped_samples(self) -> int:
        return 0

    def _reset_clipped_samples(self) -> None:
        calls['reset_clipped_samples'] = True

    monkeypatch.setattr(CamillaDSPClient, 'get_config', _get_config)
    monkeypatch.setattr(CamillaDSPClient, 'validate_config', _validate_config)
    monkeypatch.setattr(CamillaDSPClient, 'set_config', _set_config)
    monkeypatch.setattr(CamillaDSPClient, 'get_clipped_samples', _get_clipped_samples)
    monkeypatch.setattr(CamillaDSPClient, 'reset_clipped_samples', _reset_clipped_samples)
    return calls


@pytest.fixture
def mock_snapserver_volume(monkeypatch):
    calls = {}

    def _set_client_volume(self, client_id: str, percent: int, muted: bool = False):
        calls['set_client_volume'] = (client_id, percent, muted)

    monkeypatch.setattr(SnapserverClient, 'set_client_volume', _set_client_volume)
    return calls


@pytest.fixture
def db_volume_mode(audera_home):
    """Seeds settings so the volume control renders in dB mode (rather than percent)."""
    settings_dal.create(
        Settings(
            plexamp_host='localhost',
            snapserver_host='localhost',
            features={features.VOLUME_KEY: features.FF_VOLUME_PERC_OR_DB},
        )
    )


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
    await user.should_see('Mute')
    await user.should_not_see(kind=ui.switch)


async def test_players_tab_shows_latency_control(audera_home, mock_snapserver_with_client, user: User):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    await user.should_see('Latency (ms)')


async def test_players_tab_disabled_experience_shows_switch_and_hides_mute(audera_home, mock_snapserver_with_client, user: User):
    settings_dal.create(
        Settings(
            plexamp_host='localhost',
            snapserver_host='localhost',
            features={features.PLAYER_SELECTION_KEY: features.FF_DISABLED_VS_MUTE},
        )
    )
    Page().load()
    await user.open('/')
    await user.should_see(kind=ui.switch)
    await user.should_not_see(kind=ui.checkbox)


async def test_players_tab_disabled_experience_minimizes_muted_client(
    audera_home, mock_snapserver_with_muted_client, user: User
):
    settings_dal.create(
        Settings(
            plexamp_host='localhost',
            snapserver_host='localhost',
            features={features.PLAYER_SELECTION_KEY: features.FF_DISABLED_VS_MUTE},
        )
    )
    Page().load()
    await user.open('/')
    await user.should_see(kind=ui.switch)
    await user.should_see(marker='player-settings')
    await user.should_not_see(kind=ui.slider)


async def test_players_tab_disabled_experience_toggle_off_mutes_client(
    audera_home, mock_snapserver_with_client, mock_snapserver_volume, user: User
):
    settings_dal.create(
        Settings(
            plexamp_host='localhost',
            snapserver_host='localhost',
            features={features.PLAYER_SELECTION_KEY: features.FF_DISABLED_VS_MUTE},
        )
    )
    Page().load()
    await user.open('/')
    user.find(kind=ui.switch).click()
    await asyncio.sleep(0.1)
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 100, True)


async def test_players_tab_disabled_experience_toggle_on_unmutes_client(
    audera_home, mock_snapserver_with_muted_client, mock_snapserver_volume, user: User
):
    settings_dal.create(
        Settings(
            plexamp_host='localhost',
            snapserver_host='localhost',
            features={features.PLAYER_SELECTION_KEY: features.FF_DISABLED_VS_MUTE},
        )
    )
    Page().load()
    await user.open('/')
    user.find(kind=ui.switch).click()
    await asyncio.sleep(0.1)
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 100, False)


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


async def test_volume_slider_seeded_from_daemon(
    audera_home,
    mock_snapserver_with_client,
    mock_camilladsp,
    user: User,
):
    Page().load()
    await user.open('/')
    # Volume seeds from the daemon via get_percent_volume — no app-side replica, no
    # push-on-render.
    assert mock_camilladsp.get('get_percent_volume') is True
    assert mock_camilladsp.get('set_percent_volume') is None


async def test_players_tab_volume_percent_mode_shows_icon_and_label(
    audera_home, mock_snapserver_with_client, mock_camilladsp, user: User
):
    Page().load()
    await user.open('/')
    await user.should_see(kind=ui.icon, content='volume_up')
    await user.should_see('80%')  # seeded from the daemon's get_percent_volume


async def test_players_tab_volume_db_mode_shows_icon_and_label(
    audera_home, mock_snapserver_with_client, mock_camilladsp, db_volume_mode, user: User
):
    Page().load()
    await user.open('/')
    await user.should_see(kind=ui.icon, content='volume_up')
    await user.should_see('-1.9 dB')  # percent_to_db(80) == -1.938...


async def test_players_tab_volume_percent_slider_change_persists_and_updates_label(
    audera_home, mock_snapserver_with_client, mock_camilladsp, mock_snapserver_volume, user: User
):
    Page().load()
    await user.open('/')
    with user:
        user.find(kind=ui.slider).elements.pop().value = 60
    await asyncio.sleep(0.1)
    await user.should_see('60%')
    assert mock_camilladsp.get('set_percent_volume') == 60
    assert mock_camilladsp.get('set_volume') is None
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 100, False)


async def test_players_tab_volume_db_slider_change_persists_percent_and_shows_db(
    audera_home, mock_snapserver_with_client, mock_camilladsp, mock_snapserver_volume, db_volume_mode, user: User
):
    Page().load()
    await user.open('/')
    # dB mode uses the same percent (0-100) slider; only the label shows dB.
    with user:
        user.find(kind=ui.slider).elements.pop().value = 50
    await asyncio.sleep(0.1)
    await user.should_see('-6.0 dB')  # percent_to_db(50) == -6.020...
    assert mock_camilladsp.get('set_percent_volume') == 50
    assert mock_camilladsp.get('set_volume') is None
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 100, False)


async def test_players_tab_volume_db_slider_floor_mutes_via_snapcast(
    audera_home, mock_snapserver_with_client, mock_camilladsp, mock_snapserver_volume, db_volume_mode, user: User
):
    Page().load()
    await user.open('/')
    # Floor is 0% (displayed as MIN_DB in dB mode); dragging there mutes via Snapcast.
    with user:
        user.find(kind=ui.slider).elements.pop().value = 0
    await asyncio.sleep(0.1)
    assert mock_snapserver_volume.get('set_client_volume') == ('abc123', 0, True)


async def test_players_tab_volume_db_slider_is_percent_scaled(
    audera_home, mock_snapserver_with_client, mock_camilladsp, db_volume_mode, user: User
):
    Page().load()
    await user.open('/')
    # dB mode keeps the percent (0-100) scale so the handle position matches percent mode.
    slider = user.find(kind=ui.slider).elements.pop()
    assert slider._props['min'] == 0
    assert slider._props['max'] == 100


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


async def test_settings_dialog_no_longer_shows_loudness(audera_home, mock_snapserver_with_client, user: User):
    Page().load()
    await user.open('/')
    user.find(marker='player-settings').click()
    await user.should_see('Snapcast Volume')
    await user.should_not_see('Loudness')
    await user.should_not_see('Reference level (dB)')


# --- Advanced DSP editor (WS-4 / WS-5) ---------------------------------------------------


async def test_players_tab_shows_dsp_icon(audera_home, mock_snapserver_with_client, mock_camilladsp, user: User):
    Page().load()
    await user.open('/')
    await user.should_see(marker='player-dsp')


async def test_dsp_page_renders(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    Page().load()
    await user.open('/player/abc123/dsp')
    await user.should_see('Advanced DSP')
    await user.should_see('Pre-amp (dB)')
    await user.should_see('Presets')
    await user.should_see('Save')
    await user.should_see('Reset')
    await user.should_see('Bands (0)')


async def test_dsp_page_unknown_player_shows_message(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    Page().load()
    await user.open('/player/nope/dsp')
    await user.should_see('Player not found or unreachable.')


@pytest.mark.parametrize(
    'steps',
    [
        # Each step is (find-kwargs, expected footer label), applied in order. The
        # intermediate `Bands (2)` on the flat/reset cases is load-bearing: their end state
        # (0 bands) equals the initial state, so without it a silently no-op loudness click
        # would let the test pass vacuously.
        pytest.param([({'marker': 'preset-loudness'}, 'Bands (2)')], id='loudness-seeds-two'),
        pytest.param(
            [({'marker': 'preset-loudness'}, 'Bands (2)'), ({'marker': 'preset-flat'}, 'Bands (0)')],
            id='flat-clears',
        ),
        pytest.param([({'content': '+ Add band'}, 'Bands (1)')], id='add-appends-one'),
        pytest.param(
            [({'marker': 'preset-loudness'}, 'Bands (2)'), ({'content': 'Reset'}, 'Bands (0)')],
            id='reset-discards',
        ),
    ],
)
async def test_dsp_band_count_reflects_actions(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User, steps):
    Page().load()
    await user.open('/player/abc123/dsp')
    for find_kwargs, expected in steps:
        user.find(**find_kwargs).click()
        await user.should_see(expected)


def _seed_linked_dsp(config: DSPConfig) -> None:
    """Persists a DSP config and links player 'abc123' to it (the page's load path).

    The editor recovers the config via `players_dal` → `resolve_for_player`, so a linked
    player record is required for the seeded config to open instead of a fresh empty one.
    """
    dsp_dal.create(config)
    players_dal.create(Player(id='abc123', host='192.168.1.50', port=1704, connected=True, dsp_id=config.id))


async def test_dsp_bandless_shows_chart_message_and_hides_chart(
    audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User
):
    Page().load()
    await user.open('/player/abc123/dsp')
    await user.should_see('Add a band')
    await user.should_not_see(kind=ui.echart)


async def test_dsp_adding_band_reveals_chart(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    Page().load()
    await user.open('/player/abc123/dsp')
    await user.should_not_see(kind=ui.echart)
    user.find(content='+ Add band').click()
    await user.should_see(kind=ui.echart)


async def test_dsp_preamp_clamp_keeps_below_ceiling_value(
    audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User
):
    # A +6 dB boost sets the ceiling at ~-6 dB; -10 is below it, so the clamp leaves it.
    _seed_linked_dsp(DSPConfig(id='cfg1', preamp_db=-6.0, bands=[Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)]))
    Page().load()
    await user.open('/player/abc123/dsp')
    with user:
        user.find(kind=ui.number, content='auto-protected').elements.pop().value = -10.0
    await asyncio.sleep(0.1)
    assert user.find(kind=ui.number, content='auto-protected').elements.pop().value == pytest.approx(-10.0)


async def test_dsp_preamp_clamp_pulls_above_ceiling_value_down(
    audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User
):
    # Raising the pre-amp to -2 dB over a +6 dB boost would clip, so the clamp snaps it back
    # down to the ~-6 dB clip-safe ceiling.
    _seed_linked_dsp(DSPConfig(id='cfg1', preamp_db=-6.0, bands=[Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)]))
    Page().load()
    await user.open('/player/abc123/dsp')
    with user:
        user.find(kind=ui.number, content='auto-protected').elements.pop().value = -2.0
    await asyncio.sleep(0.1)
    assert user.find(kind=ui.number, content='auto-protected').elements.pop().value == pytest.approx(-6.0, abs=0.2)


async def test_dsp_over_hot_saved_config_opens_clean(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    # Saved with a hot 0 dB pre-amp above the +6 dB boost ceiling; the load-time baseline
    # clamp pulls it down so the editor opens without a false "Unsaved changes" flag.
    _seed_linked_dsp(DSPConfig(id='cfg1', preamp_db=0.0, bands=[Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)]))
    Page().load()
    await user.open('/player/abc123/dsp')
    await user.should_see(kind=ui.echart)
    await user.should_not_see('Unsaved changes')


async def test_dsp_protect_button_removed(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    Page().load()
    await user.open('/player/abc123/dsp')
    user.find(marker='preset-loudness').click()
    await user.should_see('Bands (2)')
    await user.should_not_see('protect headroom')


async def test_dsp_save_applies_and_persists(audera_home, mock_snapserver_with_client, mock_camilladsp_dsp, user: User):
    Page().load()
    await user.open('/player/abc123/dsp')
    user.find(marker='preset-loudness').click()
    await user.should_see('Bands (2)')
    user.find('Save').click()
    await user.should_see('Saved')

    # The compiled pipeline is both validated and pushed, and carries `audera_peq_*` filters.
    assert 'validate_config' in mock_camilladsp_dsp
    compiled = mock_camilladsp_dsp['set_config']
    assert any(name.startswith('audera_peq_') for name in compiled['filters'])
    assert 'reset_clipped_samples' in mock_camilladsp_dsp

    # The config is persisted with the two bands and the player is linked to it.
    config_id = players_dal.get('abc123').dsp_id
    assert config_id
    assert len(dsp_dal.get(config_id).bands) == 2
