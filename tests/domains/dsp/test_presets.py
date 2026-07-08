from audera.domains.dsp import loudness_preset, response_peak_db
from audera.models.dsp import DSPConfig


def test_loudness_preset_shape():
    bands = loudness_preset()
    assert len(bands) == 2

    low, high = bands
    assert (low.type, low.freq, low.gain, low.q) == ('LowShelf', 90.0, 10.0, 0.7)
    assert (high.type, high.freq, high.gain, high.q) == ('HighShelf', 8000.0, 6.0, 0.7)
    assert all(band.enabled for band in bands)


def test_loudness_preset_ids_are_unique():
    bands = loudness_preset()
    assert bands[0].id != bands[1].id
    # Fresh ids on every call — presets are editable, not shared singletons.
    assert bands[0].id != loudness_preset()[0].id


def test_loudness_preset_needs_headroom():
    config = DSPConfig(id='x', bands=loudness_preset())
    assert response_peak_db(config) > 0.0
