import audera.dal.dsp as dsp_dal
from audera.models.dsp import DSPConfig

_COMPLEX_PIPELINE = {
    'filters': {
        'low_pass': {'type': 'Biquad', 'parameters': {'type': 'Lowpass', 'freq': 2000, 'q': 0.707}},
        'high_pass': {'type': 'Biquad', 'parameters': {'type': 'Highpass', 'freq': 80, 'q': 0.5}},
    },
    'mixers': {
        'stereo': {
            'channels': {'in': 2, 'out': 2},
            'mapping': [
                {'dest': 0, 'sources': [{'channel': 0, 'gain': 0, 'inverted': False}]},
                {'dest': 1, 'sources': [{'channel': 1, 'gain': 0, 'inverted': False}]},
            ],
        }
    },
    'pipeline': [
        {'type': 'Mixer', 'name': 'stereo'},
        {'type': 'Filter', 'channels': [0], 'names': ['low_pass']},
        {'type': 'Filter', 'channels': [1], 'names': ['high_pass']},
    ],
}


def _make_dsp(player_id='player1') -> DSPConfig:
    return DSPConfig(
        id='dsp-1',
        player_id=player_id,
        pipeline={'filters': {}, 'mixers': {}, 'pipeline': []},
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

    updated = DSPConfig(
        id=config.id,
        player_id=config.player_id,
        pipeline={'filters': {'lp': {}}, 'mixers': {}, 'pipeline': []},
        enabled=False,
    )
    dsp_dal.update(updated)

    result = dsp_dal.get(config.player_id)
    assert result.enabled is False
    assert 'lp' in result.pipeline.get('filters', {})


def test_dsp_delete(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    dsp_dal.delete(config.player_id)
    assert not dsp_dal.exists(config.player_id)


def test_dsp_pipeline_preserved(audera_home):
    config = DSPConfig(
        id='dsp-complex',
        player_id='player-complex',
        pipeline=_COMPLEX_PIPELINE,
        enabled=True,
    )
    dsp_dal.create(config)

    result = dsp_dal.get(config.player_id)
    assert result.pipeline == _COMPLEX_PIPELINE


def test_dsp_get_or_create_creates(audera_home):
    config = _make_dsp()
    assert not dsp_dal.exists(config.player_id)

    dsp_dal.get_or_create(config)
    assert dsp_dal.exists(config.player_id)


def test_dsp_get_or_create_reads(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get_or_create(config)
    assert result == config


def test_dsp_loudness_fields_default(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    result = dsp_dal.get(config.player_id)
    assert result.loudness_enabled is False
    assert result.loudness_reference_level == -25.0


def test_dsp_update_loudness_fields(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    updated = config.model_copy(update={'loudness_enabled': True})
    dsp_dal.update(updated)
    result = dsp_dal.get(config.player_id)
    assert result.loudness_enabled is True


def test_dsp_update_loudness_reference_level(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    updated = config.model_copy(update={'loudness_reference_level': -40.0})
    dsp_dal.update(updated)
    result = dsp_dal.get(config.player_id)
    assert result.loudness_reference_level == -40.0
