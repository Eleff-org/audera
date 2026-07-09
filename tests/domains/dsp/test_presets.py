from audera.domains.dsp import clone_bands, loudness_preset, response_peak_db
from audera.models.dsp import Band, DSPConfig


def test_loudness_preset_shape():
    bands = loudness_preset()
    assert len(bands) == 2

    low, high = bands
    assert (low.type, low.freq, low.gain, low.q) == ('Lowshelf', 90.0, 10.0, 0.7)
    assert (high.type, high.freq, high.gain, high.q) == ('Highshelf', 8000.0, 6.0, 0.7)
    assert all(band.enabled for band in bands)


def test_loudness_preset_ids_are_unique():
    bands = loudness_preset()
    assert bands[0].id != bands[1].id
    # Fresh ids on every call — presets are editable, not shared singletons.
    assert bands[0].id != loudness_preset()[0].id


def test_loudness_preset_needs_headroom():
    config = DSPConfig(player_id='x', bands=loudness_preset())
    assert response_peak_db(config) > 0.0


def _source_bands() -> list[Band]:
    return [
        Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0, q=0.7),
        Band(id='b2', type='Peaking', freq=1000.0, gain=-3.0, q=2.0, enabled=False),
    ]


def test_clone_bands_preserves_parameters():
    source = _source_bands()
    clones = clone_bands(source)
    assert len(clones) == 2
    for original, clone in zip(source, clones):
        assert (clone.type, clone.freq, clone.gain, clone.q, clone.enabled) == (
            original.type,
            original.freq,
            original.gain,
            original.q,
            original.enabled,
        )


def test_clone_bands_mints_fresh_unique_ids():
    source = _source_bands()
    clones = clone_bands(source)
    # Each clone gets a new id, distinct from its source...
    for original, clone in zip(source, clones):
        assert clone.id != original.id
    # ...and mutually unique across the clones.
    ids = [clone.id for clone in clones]
    assert len(set(ids)) == len(ids)


def test_clone_bands_is_independent():
    source = _source_bands()
    clones = clone_bands(source)
    clones[0].gain = 99.0
    assert source[0].gain == 10.0  # mutating a clone doesn't touch the source
