"""Pure DSP computation layer.

Bands are the source of truth; this package compiles them into a CamillaDSP
pipeline (`compiler`), derives the combined magnitude response, its peak, and the
clip-safe pre-amp ceiling for headroom safety (`headroom`), and mints editable
preset bands (`presets`). It imports only `audera.models` (never `dal`/`clients`),
so it is unit-testable with zero I/O.
"""

from audera.domains.dsp.compiler import compile_pipeline
from audera.domains.dsp.headroom import auto_preamp_db, response_curve, response_peak_db
from audera.domains.dsp.presets import clone_bands, loudness_preset
from audera.domains.dsp.rew import format_rew, parse_rew

__all__ = [
    'compile_pipeline',
    'auto_preamp_db',
    'response_curve',
    'response_peak_db',
    'clone_bands',
    'loudness_preset',
    'format_rew',
    'parse_rew',
]
