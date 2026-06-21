import pytest

from audera.models.dsp import (
    _LOUDNESS_FILTER_KEY,
    _LOUDNESS_HIGH_BOOST,
    _LOUDNESS_LOW_BOOST,
    DSPConfig,
    apply_loudness,
    remove_loudness,
)


@pytest.fixture
def empty_pipeline():
    return {'filters': {}, 'pipeline': []}


@pytest.fixture
def user_pipeline():
    return {
        'filters': {'user_filter': {'type': 'Biquad', 'parameters': {}}},
        'pipeline': [{'type': 'Filter', 'channels': [0], 'names': ['user_filter']}],
    }


@pytest.fixture
def applied_pipeline(empty_pipeline):
    return apply_loudness(empty_pipeline)


def test_apply_loudness_inserts_filter(applied_pipeline):
    assert _LOUDNESS_FILTER_KEY in applied_pipeline['filters']


def test_apply_loudness_fader_param(applied_pipeline):
    params = applied_pipeline['filters'][_LOUDNESS_FILTER_KEY]['parameters']
    assert params['fader'] == 'Main'
    assert params['reference_level'] == -25.0


def test_apply_loudness_custom_reference_level(empty_pipeline):
    result = apply_loudness(empty_pipeline, -40.0)
    params = result['filters'][_LOUDNESS_FILTER_KEY]['parameters']
    assert params['reference_level'] == -40.0


def test_apply_loudness_boost_values(applied_pipeline):
    params = applied_pipeline['filters'][_LOUDNESS_FILTER_KEY]['parameters']
    assert params['low_boost'] == _LOUDNESS_LOW_BOOST
    assert params['high_boost'] == _LOUDNESS_HIGH_BOOST


def test_apply_loudness_adds_pipeline_steps(applied_pipeline):
    loudness_steps = [s for s in applied_pipeline['pipeline'] if _LOUDNESS_FILTER_KEY in s.get('names', [])]
    assert len(loudness_steps) == 2


def test_remove_loudness_cleans_filter_and_steps(applied_pipeline):
    result = remove_loudness(applied_pipeline)
    assert _LOUDNESS_FILTER_KEY not in result['filters']
    assert all(_LOUDNESS_FILTER_KEY not in s.get('names', []) for s in result['pipeline'])


def test_apply_then_remove_is_idempotent(empty_pipeline):
    result = remove_loudness(apply_loudness(empty_pipeline))
    assert result['filters'] == empty_pipeline['filters']
    assert result['pipeline'] == empty_pipeline['pipeline']


def test_apply_loudness_does_not_touch_user_filters(user_pipeline):
    applied = apply_loudness(user_pipeline)
    assert 'user_filter' in applied['filters']
    removed = remove_loudness(applied)
    assert 'user_filter' in removed['filters']
    assert any('user_filter' in s.get('names', []) for s in removed['pipeline'])


def test_apply_loudness_idempotent_steps(empty_pipeline):
    once = apply_loudness(empty_pipeline)
    twice = apply_loudness(once)
    loudness_steps = [s for s in twice['pipeline'] if _LOUDNESS_FILTER_KEY in s.get('names', [])]
    assert len(loudness_steps) == 2


def test_dsp_config_loudness_defaults():
    config = DSPConfig(id='x', player_id='x')
    assert config.loudness_enabled is False
    assert config.loudness_reference_level == -25.0


def test_dsp_config_to_dict_includes_loudness_fields():
    config = DSPConfig(id='x', player_id='x', loudness_enabled=True)
    d = config.to_dict()
    assert d['loudness_enabled'] is True
    assert d['loudness_reference_level'] == -25.0
