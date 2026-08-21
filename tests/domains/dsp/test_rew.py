import json

import pytest
import yaml

from audera.domains.dsp import format_rew, parse_rew
from audera.models.dsp import DEFAULT_Q, Band, DSPConfig


def _biquad(band_type, **parameters) -> dict:
    """Returns a CamillaDSP Biquad filter `dict` with the given `parameters.type`."""
    return {'type': 'Biquad', 'parameters': {'type': band_type, **parameters}}


def _yaml(filters, pipeline=None) -> str:
    """Serializes a CamillaDSP `{filters, pipeline}` document to YAML text."""
    document = {'filters': filters}
    if pipeline is not None:
        document['pipeline'] = pipeline
    return yaml.safe_dump(document, sort_keys=False)


@pytest.mark.parametrize('band_type', ['Peaking', 'Lowshelf', 'Highshelf', 'Lowpass', 'Highpass'])
def test_parse_maps_supported_types(band_type):
    result = parse_rew(_yaml({'f1': _biquad(band_type, freq=1000.0, q=1.0, gain=3.0)}))
    assert [band.type for band in result.bands] == [band_type]
    assert result.skipped == []


def test_parse_reads_numeric_fields():
    (band,) = parse_rew(_yaml({'f1': _biquad('Peaking', freq=1000.0, q=1.41, gain=-3.5)})).bands
    assert band.freq == pytest.approx(1000.0)
    assert band.gain == pytest.approx(-3.5)
    assert band.q == pytest.approx(1.41)


@pytest.mark.parametrize('bypassed, enabled', [(False, True), (True, False)])
def test_parse_bypassed_sets_enabled(bypassed, enabled):
    text = _yaml(
        {'f1': _biquad('Peaking', freq=1000.0, q=1.0, gain=3.0)},
        pipeline=[{'type': 'Filter', 'channels': [0, 1], 'names': ['f1'], 'bypassed': bypassed}],
    )
    (band,) = parse_rew(text).bands
    assert band.enabled is enabled


def test_parse_filter_absent_from_pipeline_defaults_enabled():
    # A filter no pipeline step references is treated as active.
    (band,) = parse_rew(_yaml({'f1': _biquad('Peaking', freq=1000.0, q=1.0, gain=3.0)})).bands
    assert band.enabled is True


@pytest.mark.parametrize('subtype', ['Notch', 'Bandpass', 'Allpass', 'LowshelfFO', 'HighshelfFO'])
def test_parse_skips_unsupported_biquad_subtype(subtype):
    result = parse_rew(_yaml({'weird': _biquad(subtype, freq=1000.0, q=1.0, gain=3.0)}))
    assert result.bands == []
    assert result.skipped == ['weird']


@pytest.mark.parametrize(
    'filter_',
    [
        {'type': 'Gain', 'parameters': {'gain': -3.0}},
        {'type': 'Conv', 'parameters': {'values': [1.0]}},
        {'type': 'BiquadCombo', 'parameters': {'type': 'ButterworthHighpass', 'freq': 40.0, 'order': 4}},
    ],
)
def test_parse_skips_non_biquad_filter(filter_):
    result = parse_rew(_yaml({'foreign': filter_}))
    assert result.bands == []
    assert result.skipped == ['foreign']


def test_parse_skips_supported_type_missing_freq():
    result = parse_rew(_yaml({'f1': _biquad('Peaking', q=1.0, gain=3.0)}))  # no freq
    assert result.bands == []
    assert result.skipped == ['f1']


@pytest.mark.parametrize(
    'parameters',
    [
        {'freq': 'not-a-number', 'q': 1.0, 'gain': 3.0},
        {'freq': 1000.0, 'q': 'bad', 'gain': 3.0},
        {'freq': 1000.0, 'q': 1.0, 'gain': 'bad'},
    ],
    ids=['freq', 'q', 'gain'],
)
def test_parse_skips_malformed_numeric_field_without_crashing(parameters):
    # A supported `type` with a non-numeric field must be skipped, not abort the whole import:
    # `parse_rew` only ever caught `yaml.YAMLError`, so the float coercion crashed it.
    text = _yaml(
        {
            'good': _biquad('Peaking', freq=1000.0, q=1.0, gain=3.0),
            'bad': _biquad('Peaking', **parameters),
        }
    )
    result = parse_rew(text)
    assert [band.freq for band in result.bands] == [1000.0]
    assert result.skipped == ['bad']


@pytest.mark.parametrize('band_type', ['Lowpass', 'Highpass'])
def test_parse_pass_filter_gain_is_zero(band_type):
    (band,) = parse_rew(_yaml({'f1': _biquad(band_type, freq=1000.0, q=0.9, gain=3.0)})).bands
    assert band.gain == 0.0


def test_parse_omitted_q_defaults():
    (band,) = parse_rew(_yaml({'f1': _biquad('Peaking', freq=1000.0, gain=3.0)})).bands  # no q
    assert band.q == pytest.approx(DEFAULT_Q)


def test_parse_accepts_json_paste():
    # JSON is a YAML subset, so a CamillaDSP JSON export parses too.
    text = json.dumps({'filters': {'f1': _biquad('Peaking', freq=1000.0, q=1.0, gain=3.0)}})
    (band,) = parse_rew(text).bands
    assert band.type == 'Peaking'


def test_parse_garbage_input_is_skipped_raw():
    result = parse_rew('this is not a camilladsp document')
    assert result.bands == []
    assert result.skipped == ['this is not a camilladsp document']


def test_parse_yaml_syntax_error_is_skipped_raw():
    result = parse_rew('filters: [unclosed')
    assert result.bands == []
    assert result.skipped == ['filters: [unclosed']


def test_parse_blank_input_yields_nothing():
    result = parse_rew('\n   \n\t\n')
    assert result.bands == []
    assert result.skipped == []


def test_parse_mints_unique_ids():
    text = _yaml(
        {
            'f1': _biquad('Peaking', freq=1000.0, q=1.0, gain=3.0),
            'f2': _biquad('Peaking', freq=2000.0, q=1.0, gain=3.0),
        }
    )
    ids = [band.id for band in parse_rew(text).bands]
    assert len(ids) == len(set(ids)) == 2


def test_format_emits_filters_and_pipeline():
    text = format_rew(-6.0, [Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, q=1.0)])
    assert 'filters:' in text  # the tag REW requires to import
    document = yaml.safe_load(text)
    assert document['filters']['b1'] == {
        'type': 'Biquad',
        'parameters': {'type': 'Peaking', 'freq': 1000.0, 'q': 1.0, 'gain': 3.0},
    }
    assert document['pipeline'] == [{'type': 'Filter', 'channels': [0, 1], 'names': ['b1'], 'bypassed': False}]


def test_format_pass_filter_omits_gain_keeps_q():
    document = yaml.safe_load(format_rew(0.0, [Band(id='b1', type='Lowpass', freq=12000.0, q=0.8)]))
    parameters = document['filters']['b1']['parameters']
    assert 'gain' not in parameters
    assert parameters['q'] == pytest.approx(0.8)


def test_format_disabled_band_is_bypassed():
    document = yaml.safe_load(format_rew(0.0, [Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, enabled=False)]))
    assert document['pipeline'][0]['bypassed'] is True


def test_format_does_not_emit_preamp():
    # Pre-amp is not round-tripped — no Gain filter is written, only band biquads.
    text = format_rew(-9.9, [Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, q=1.0)])
    document = yaml.safe_load(text)
    assert 'preamp' not in text.lower()
    assert all(filter_['type'] == 'Biquad' for filter_ in document['filters'].values())


def _bands_equal(a: Band, b: Band) -> bool:
    return (
        a.type == b.type
        and a.freq == pytest.approx(b.freq)
        and a.gain == pytest.approx(b.gain)
        and a.q == pytest.approx(b.q)
        and a.enabled == b.enabled
    )


def test_round_trip_over_bands_ignoring_ids():
    config = DSPConfig(
        player_id='x',
        preamp_db=-6.3,
        bands=[
            Band(id='b1', type='Peaking', freq=1000.0, gain=-3.5, q=1.41),
            Band(id='b2', type='Lowshelf', freq=90.0, gain=4.0, q=0.7),
            Band(id='b3', type='Highshelf', freq=8000.0, gain=6.0, q=0.71, enabled=False),
            Band(id='b4', type='Lowpass', freq=12000.0, q=0.8),
            Band(id='b5', type='Highpass', freq=40.0, q=0.9),
        ],
    )
    reparsed = parse_rew(format_rew(config.preamp_db, config.bands)).bands
    assert len(reparsed) == len(config.bands)
    assert all(_bands_equal(got, expected) for got, expected in zip(reparsed, config.bands))
    # Fresh ids on re-import — bands round-trip modulo id.
    assert all(got.id != expected.id for got, expected in zip(reparsed, config.bands))
