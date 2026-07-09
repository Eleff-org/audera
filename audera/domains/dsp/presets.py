"""Editable band presets.

Loudness is now a static preset — two editable shelf bands — rather than a dynamic
filter. The page (WS-4/5) pairs this with the headroom guard to suggest a
protective pre-amp; this module only mints the bands.
"""

import uuid

from audera.models.dsp import Band

_LOUDNESS_LOW_BOOST = 10.0
_LOUDNESS_HIGH_BOOST = 6.0


def loudness_preset() -> list[Band]:
    """Returns two fresh, editable loudness shelf bands.

    A `LowShelf` at 90 Hz (+10 dB) and a `HighShelf` at 8000 Hz (+6 dB), each with
    `q=0.7`, a unique id, and enabled — mirroring the retired dynamic-loudness
    boosts.
    """
    return [
        Band(id=uuid.uuid4().hex, type='LowShelf', freq=90.0, gain=_LOUDNESS_LOW_BOOST, q=0.7),
        Band(id=uuid.uuid4().hex, type='HighShelf', freq=8000.0, gain=_LOUDNESS_HIGH_BOOST, q=0.7),
    ]


def clone_bands(bands: list[Band]) -> list[Band]:
    """Returns deep copies of `bands`, each with a fresh unique id.

    Reused by both applying a saved preset (append onto the current config) and saving
    one (capture the current bands). The fresh ids keep `audera_peq_<id>` filter names
    from colliding within a single compiled config.
    """
    return [band.model_copy(deep=True, update={'id': uuid.uuid4().hex}) for band in bands]
