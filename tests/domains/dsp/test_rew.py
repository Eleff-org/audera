import pytest

from audera.domains.dsp import format_rew, parse_rew
from audera.models.dsp import Band, DSPConfig


@pytest.mark.parametrize(
    'kind, expected',
    [
        ('PK', 'Peaking'),
        ('LS', 'LowShelf'),
        ('LSC', 'LowShelf'),
        ('HS', 'HighShelf'),
        ('HSC', 'HighShelf'),
        ('LP', 'Lowpass'),
        ('HP', 'Highpass'),
    ],
)
def test_parse_maps_supported_kinds(kind, expected):
    result = parse_rew(f'Filter 1: ON {kind} Fc 1000 Hz Gain 3.0 dB Q 1.0')
    assert [band.type for band in result.bands] == [expected]
    assert result.skipped == []


def test_parse_reads_numeric_fields():
    result = parse_rew('Filter 1: ON PK Fc 1000 Hz Gain -3.5 dB Q 1.41')
    (band,) = result.bands
    assert band.freq == pytest.approx(1000.0)
    assert band.gain == pytest.approx(-3.5)
    assert band.q == pytest.approx(1.41)


@pytest.mark.parametrize('state, enabled', [('ON', True), ('OFF', False)])
def test_parse_on_off_sets_enabled(state, enabled):
    (band,) = parse_rew(f'Filter 1: {state} PK Fc 1000 Hz Gain 3.0 dB Q 1.0').bands
    assert band.enabled is enabled


def test_parse_accepts_equalizer_apo_lines_without_index():
    (band,) = parse_rew('Filter: ON PK Fc 1000 Hz Gain 3.0 dB Q 1.0').bands
    assert band.type == 'Peaking'


@pytest.mark.parametrize('kind', ['NO', 'AP', 'BP'])
def test_parse_skips_unsupported_kinds(kind):
    result = parse_rew(f'Filter 1: ON {kind} Fc 1000 Hz Gain 3.0 dB Q 1.0')
    assert result.bands == []
    assert len(result.skipped) == 1


def test_parse_skips_supported_kind_missing_fc():
    result = parse_rew('Filter 1: ON PK Gain 3.0 dB Q 1.0')
    assert result.bands == []
    assert len(result.skipped) == 1


def test_parse_skips_garbage_line():
    result = parse_rew('this is not a filter line')
    assert result.bands == []
    assert result.skipped == ['this is not a filter line']


def test_parse_ignores_blank_lines():
    result = parse_rew('\n   \n\t\n')
    assert result.bands == []
    assert result.skipped == []


def test_parse_recognizes_preamp_without_band_or_skip():
    result = parse_rew('Preamp: -6.5 dB')
    assert result.bands == []
    assert result.skipped == []


def test_parse_preamp_plus_filter_yields_one_band():
    result = parse_rew('Preamp: -6.5 dB\nFilter 1: ON PK Fc 1000 Hz Gain 3.0 dB Q 1.0')
    assert len(result.bands) == 1
    assert result.skipped == []


@pytest.mark.parametrize('kind, expected', [('LP', 'Lowpass'), ('HP', 'Highpass')])
def test_parse_pass_filter_without_q_defaults(kind, expected):
    (band,) = parse_rew(f'Filter 1: ON {kind} Fc 1000 Hz').bands
    assert band.type == expected
    assert band.q == pytest.approx(0.707)


def test_parse_mints_unique_ids():
    result = parse_rew('Filter 1: ON PK Fc 1000 Hz Gain 3.0 dB Q 1.0\nFilter 2: ON PK Fc 2000 Hz Gain 3.0 dB Q 1.0')
    ids = [band.id for band in result.bands]
    assert len(ids) == len(set(ids)) == 2


def test_format_emits_preamp_and_filter_lines():
    text = format_rew(-6.0, [Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, q=1.0)])
    lines = text.splitlines()
    assert lines[0] == 'Preamp: -6.0 dB'
    assert lines[1].startswith('Filter 1:')
    assert 'PK' in lines[1]


def test_format_pass_filter_omits_gain_keeps_q():
    text = format_rew(0.0, [Band(id='b1', type='Lowpass', freq=12000.0, q=0.8)])
    (_, filter_line) = text.splitlines()
    assert 'Gain' not in filter_line
    assert 'Q 0.800' in filter_line


def test_format_disabled_band_emits_off():
    text = format_rew(0.0, [Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, enabled=False)])
    assert ' OFF PK ' in text.splitlines()[1]


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
        id='x',
        preamp_db=-6.3,
        bands=[
            Band(id='b1', type='Peaking', freq=1000.0, gain=-3.5, q=1.41),
            Band(id='b2', type='LowShelf', freq=90.0, gain=4.0, q=0.7),
            Band(id='b3', type='HighShelf', freq=8000.0, gain=6.0, q=0.71, enabled=False),
            Band(id='b4', type='Lowpass', freq=12000.0, q=0.8),
            Band(id='b5', type='Highpass', freq=40.0, q=0.9),
        ],
    )
    reparsed = parse_rew(format_rew(config.preamp_db, config.bands)).bands
    assert len(reparsed) == len(config.bands)
    assert all(_bands_equal(got, expected) for got, expected in zip(reparsed, config.bands))
    # Fresh ids on re-import — bands round-trip modulo id.
    assert all(got.id != expected.id for got, expected in zip(reparsed, config.bands))


def test_round_trip_does_not_reapply_preamp():
    # `format_rew` emits the pre-amp for fidelity, but `parse_rew` recognizes it without
    # producing a band or a skip — the auto-ceiling owns pre-amp on import.
    config = DSPConfig(id='x', preamp_db=-9.9, bands=[Band(id='b1', type='Peaking', freq=1000.0, gain=3.0, q=1.0)])
    text = format_rew(config.preamp_db, config.bands)
    assert 'Preamp: -9.9 dB' in text
    result = parse_rew(text)
    assert len(result.bands) == 1
    assert result.skipped == []
