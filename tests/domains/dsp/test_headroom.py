import pytest
from camilladsp_plot import eval_filter
from camilladsp_plot.eval_filterconfig import logspace

from audera.domains.dsp import auto_preamp_db, response_curve, response_peak_db
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


def test_response_curve_lengths_match_and_frequency_is_strictly_increasing():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    frequencies, magnitudes = response_curve(DSPConfig(id='x', bands=[band]))
    assert len(frequencies) == len(magnitudes)
    assert all(later > earlier for earlier, later in zip(frequencies, frequencies[1:]))


def test_response_curve_no_enabled_bands_synthesizes_full_flat_line():
    # The axis is synthesized from `logspace`, not borrowed from a band's `eval_filter`
    # result, so the full grid + flat pre-amp line exists with no band firing.
    config = DSPConfig(id='x', preamp_db=-3.0, bands=[Band(id='b1', freq=1000.0, gain=6.0, enabled=False)])
    frequencies, magnitudes = response_curve(config, npoints=400)
    assert frequencies == logspace(1.0, 48000 * 0.95 / 2.0, 400)
    assert len(magnitudes) == 400
    assert magnitudes == pytest.approx([-3.0] * 400)


def test_response_peak_db_equals_curve_max_on_fine_grid():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    config = DSPConfig(id='x', preamp_db=-2.0, bands=[band])
    assert response_peak_db(config) == pytest.approx(max(response_curve(config, npoints=1000)[1]))


def test_auto_preamp_db_zero_for_no_enabled_bands():
    assert auto_preamp_db([]) == pytest.approx(0.0)
    assert auto_preamp_db([Band(id='b1', freq=1000.0, gain=6.0, enabled=False)]) == pytest.approx(0.0)


def test_auto_preamp_db_zero_for_all_cut():
    # A net cut never exceeds 0 dBFS, so no attenuation is needed.
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=-6.0, q=1.0)
    assert auto_preamp_db([band]) == pytest.approx(0.0)


def test_auto_preamp_db_cancels_boost_peak_so_clamped_config_never_clips():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    ceiling = auto_preamp_db([band])
    assert ceiling == pytest.approx(-6.0, abs=0.1)
    clamped = DSPConfig(id='x', preamp_db=ceiling, bands=[band])
    assert response_peak_db(clamped) <= 1e-6


def test_auto_preamp_db_honours_margin():
    band = Band(id='b1', type='Peaking', freq=1000.0, gain=6.0, q=1.0)
    no_margin = auto_preamp_db([band])
    with_margin = auto_preamp_db([band], margin_db=3.0)
    assert with_margin == pytest.approx(no_margin - 3.0)
