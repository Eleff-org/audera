from audera.models.dsp import Band, DSPConfig


def test_band_defaults():
    band = Band(id='b1', freq=1000.0)
    assert band.type == 'Peaking'
    assert band.gain == 0.0
    assert band.q == 0.707
    assert band.enabled is True


def test_band_to_dict():
    band = Band(id='b1', type='LowShelf', freq=90.0, gain=10.0, q=0.7, enabled=False)
    assert band.to_dict() == {
        'id': 'b1',
        'type': 'LowShelf',
        'freq': 90.0,
        'gain': 10.0,
        'q': 0.7,
        'enabled': False,
    }


def test_band_from_dict_round_trip():
    band = Band(id='b1', type='HighShelf', freq=8000.0, gain=6.0, q=0.7)
    assert Band.from_dict(band.to_dict()) == band


def test_dsp_config_defaults():
    config = DSPConfig(id='x')
    assert config.preamp_db == 0.0
    assert config.bands == []
    assert config.enabled is True


def test_dsp_config_to_dict_keys():
    config = DSPConfig(id='x')
    assert set(config.to_dict().keys()) == {'id', 'preamp_db', 'bands', 'enabled'}


def test_dsp_config_bands_round_trip():
    config = DSPConfig(
        id='x',
        preamp_db=-6.0,
        bands=[
            Band(id='b1', type='LowShelf', freq=90.0, gain=10.0),
            Band(id='b2', type='HighShelf', freq=8000.0, gain=6.0),
        ],
    )
    result = DSPConfig.from_dict(config.to_dict())
    assert result == config
    assert result.bands[0].type == 'LowShelf'
    assert result.bands[1].freq == 8000.0


def test_dsp_config_legacy_dict_drops_retired_keys():
    legacy = {
        'id': 'x',
        'player_id': 'player-1',
        'pipeline': {'filters': {}, 'pipeline': []},
        'loudness_enabled': True,
        'loudness_reference_level': -30.0,
        'volume': 40.0,
        'enabled': True,
    }
    config = DSPConfig.from_dict(legacy)
    result = config.to_dict()
    assert set(result.keys()) == {'id', 'preamp_db', 'bands', 'enabled'}
    for retired in ('player_id', 'pipeline', 'loudness_enabled', 'loudness_reference_level', 'volume'):
        assert retired not in result


def test_dsp_config_id_is_identity():
    a = DSPConfig(id='same', preamp_db=-3.0)
    b = DSPConfig(id='same', preamp_db=-3.0)
    assert a == b
    assert a != DSPConfig(id='other', preamp_db=-3.0)
