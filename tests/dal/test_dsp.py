import audera.dal.dsp as dsp_dal
import audera.dal.presets as presets_dal
from audera.models.dsp import Band, DSPConfig, Preset
from audera.models.player import Player


def _make_dsp(id='dsp-1') -> DSPConfig:
    return DSPConfig(
        id=id,
        preamp_db=-6.0,
        bands=[Band(id='b1', type='LowShelf', freq=90.0, gain=10.0)],
        enabled=True,
    )


def _make_player(id='abc123') -> Player:
    return Player(id=id, host='192.168.1.50', port=1704, connected=True)


def test_dsp_create(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    assert dsp_dal.exists(config.id)


def test_dsp_get(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get(config.id)
    assert result == config


def test_dsp_update(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    updated = config.model_copy(update={'enabled': False})
    dsp_dal.update(updated)

    result = dsp_dal.get(config.id)
    assert result.enabled is False


def test_dsp_delete(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    dsp_dal.delete(config.id)
    assert not dsp_dal.exists(config.id)


def test_dsp_bands_round_trip(audera_home):
    config = DSPConfig(
        id='dsp-bands',
        preamp_db=-3.0,
        bands=[
            Band(id='b1', type='LowShelf', freq=90.0, gain=10.0, q=0.7),
            Band(id='b2', type='HighShelf', freq=8000.0, gain=6.0, q=0.7),
            Band(id='b3', type='Peaking', freq=1000.0, gain=-3.0, q=2.0, enabled=False),
        ],
    )
    dsp_dal.create(config)

    result = dsp_dal.get(config.id)
    assert result == config
    assert [b.type for b in result.bands] == ['LowShelf', 'HighShelf', 'Peaking']


def test_dsp_get_or_create_creates(audera_home):
    config = _make_dsp()
    assert not dsp_dal.exists(config.id)

    dsp_dal.get_or_create(config)
    assert dsp_dal.exists(config.id)


def test_dsp_get_or_create_reads(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get_or_create(config)
    assert result == config


def test_resolve_for_player_creates_keyed_by_player_id(audera_home):
    player = _make_player()

    config = dsp_dal.resolve_for_player(player)

    # The config is created keyed by the player's own id — the filename is the link.
    assert config.id == player.id
    assert dsp_dal.exists(player.id)
    assert config.bands == []
    assert config.preamp_db == 0.0


def test_resolve_for_player_idempotent_after_edit(audera_home):
    player = _make_player()
    dsp_dal.resolve_for_player(player)  # first open creates an empty config

    edited = _make_dsp(id=player.id)
    dsp_dal.update(edited)

    # A second open re-reads the edited config — it never re-mints an empty one.
    assert dsp_dal.resolve_for_player(player) == edited


def test_resolve_for_player_returns_existing(audera_home):
    existing = _make_dsp(id='abc123')
    dsp_dal.create(existing)
    player = _make_player(id='abc123')

    config = dsp_dal.resolve_for_player(player)
    assert config == existing


def test_resolve_for_player_ignores_preset_namespace(audera_home):
    # A preset keyed with the same id lives under `dsp/presets/`, not `dsp/`.
    presets_dal.save_preset(Preset(id='abc123', name='Bass', bands=[Band(id='b1', type='LowShelf', freq=90.0, gain=6.0)]))

    config = dsp_dal.resolve_for_player(_make_player(id='abc123'))

    # The preset is never returned — the player config is a fresh, empty one.
    assert config.bands == []
