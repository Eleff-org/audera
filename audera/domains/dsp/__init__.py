"""Pure DSP computation layer.

Bands are the source of truth; this package compiles them into a CamillaDSP
pipeline (`compiler`), computes the combined magnitude peak for headroom safety
(`headroom`), and mints editable preset bands (`presets`). It imports only
`audera.models` (never `dal`/`clients`), so it is unit-testable with zero I/O.
"""

from audera.domains.dsp.compiler import compile_pipeline
from audera.domains.dsp.headroom import response_peak_db
from audera.domains.dsp.presets import loudness_preset

__all__ = ['compile_pipeline', 'response_peak_db', 'loudness_preset']
