import audera.dal.dsp as dsp_dal
from audera.models.dsp import Band, DSPConfig


def _make_dsp(player_id='abc123') -> DSPConfig:
    return DSPConfig(
        player_id=player_id,
        preamp_db=-6.0,
        bands=[Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0)],
        enabled=True,
    )


def test_dsp_create(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    assert dsp_dal.exists(config.player_id)


def test_dsp_get(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get(config.player_id)
    assert result == config


def test_dsp_update(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    updated = config.model_copy(update={'enabled': False})
    dsp_dal.update(updated)

    result = dsp_dal.get(config.player_id)
    assert result.enabled is False


def test_dsp_delete(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    dsp_dal.delete(config.player_id)
    assert not dsp_dal.exists(config.player_id)


def test_dsp_bands_round_trip(audera_home):
    config = DSPConfig(
        player_id='dsp-bands',
        preamp_db=-3.0,
        bands=[
            Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0, q=0.7),
            Band(id='b2', type='Highshelf', freq=8000.0, gain=6.0, q=0.7),
            Band(id='b3', type='Peaking', freq=1000.0, gain=-3.0, q=2.0, enabled=False),
        ],
    )
    dsp_dal.create(config)

    result = dsp_dal.get(config.player_id)
    assert result == config
    assert [b.type for b in result.bands] == ['Lowshelf', 'Highshelf', 'Peaking']


def test_dsp_get_or_create_creates(audera_home):
    config = _make_dsp()
    assert not dsp_dal.exists(config.player_id)

    dsp_dal.get_or_create(config)
    assert dsp_dal.exists(config.player_id)


def test_dsp_get_or_create_creates_keyed_by_player_id(audera_home):
    # The config file is `dsp/{player_id}.json` — the filename is the link to the player.
    config = dsp_dal.get_or_create(DSPConfig(player_id='abc123'))

    assert config.player_id == 'abc123'
    assert dsp_dal.exists('abc123')
    assert config.bands == []
    assert config.preamp_db == 0.0


def test_dsp_get_or_create_reads(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get_or_create(config)
    assert result == config


def test_dsp_get_or_create_idempotent_after_edit(audera_home):
    dsp_dal.get_or_create(DSPConfig(player_id='abc123'))  # first open creates an empty config

    edited = _make_dsp(player_id='abc123')
    dsp_dal.update(edited)

    # A second open re-reads the edited config — it never re-mints an empty one.
    assert dsp_dal.get_or_create(DSPConfig(player_id='abc123')) == edited
