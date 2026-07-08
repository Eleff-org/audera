import pytest
from camilladsp_plot import eval_filter

from audera.domains.dsp import response_peak_db
from audera.domains.dsp.compiler import _band_to_biquad
from audera.models.dsp import Band, DSPConfig


def test_single_band_matches_eval_filter_math():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    config = DSPConfig(id='x', preamp_db=-3.0, bands=[band])
    expected = max(eval_filter(_band_to_biquad(band), samplerate=48000)['magnitude']) + config.preamp_db
    assert response_peak_db(config) == pytest.approx(expected)


def test_single_peaking_band_peaks_near_gain():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    config = DSPConfig(id='x', bands=[band])
    assert response_peak_db(config) == pytest.approx(6.0, abs=0.1)


@pytest.mark.parametrize('filter_type', ['Lowpass', 'Highpass'])
def test_high_q_pass_filter_resonates_above_unity(filter_type):
    band = Band(id='b1', type=filter_type, freq=1000.0, q=4.0)
    config = DSPConfig(id='x', bands=[band])
    assert response_peak_db(config) > 0.0


def test_preamp_shifts_peak_by_scalar():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    flat = response_peak_db(DSPConfig(id='x', preamp_db=0.0, bands=[band]))
    shifted = response_peak_db(DSPConfig(id='x', preamp_db=-4.0, bands=[band]))
    assert shifted == pytest.approx(flat - 4.0)


def test_no_enabled_bands_returns_preamp():
    config = DSPConfig(
        id='x',
        preamp_db=-5.0,
        bands=[Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, enabled=False)],
    )
    assert response_peak_db(config) == pytest.approx(-5.0)


def test_empty_config_returns_preamp():
    assert response_peak_db(DSPConfig(id='x', preamp_db=-2.0)) == pytest.approx(-2.0)
