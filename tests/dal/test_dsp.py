import audera.dal.dsp as dsp_dal
import audera.dal.players as players_dal
from audera.models.dsp import Band, DSPConfig
from audera.models.player import Player


def _make_dsp(id='dsp-1') -> DSPConfig:
    return DSPConfig(
        id=id,
        preamp_db=-6.0,
        bands=[Band(id='b1', type='LowShelf', freq=90.0, gain=10.0)],
        enabled=True,
    )


def _make_player(id='abc123', dsp_id='') -> Player:
    return Player(id=id, host='192.168.1.50', port=1704, connected=True, dsp_id=dsp_id)


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


def test_resolve_for_player_mints_and_links(audera_home):
    player = _make_player(dsp_id='')
    players_dal.create(player)

    config = dsp_dal.resolve_for_player(player)

    # The minted config is saved, keyed by its own id
    assert dsp_dal.exists(config.id)
    assert config.bands == []
    assert config.preamp_db == 0.0

    # The player is linked (dsp_id persisted) and the returned config re-reads
    assert players_dal.get(player.id).dsp_id == config.id
    assert dsp_dal.get(config.id) == config


def test_resolve_for_player_returns_existing(audera_home):
    existing = _make_dsp(id='dsp-existing')
    dsp_dal.create(existing)
    player = _make_player(dsp_id='dsp-existing')
    players_dal.create(player)

    config = dsp_dal.resolve_for_player(player)
    assert config == existing
