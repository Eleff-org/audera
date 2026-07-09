"""Import/export parametric-EQ bands as CamillaDSP YAML (the format REW interops with).

REW (v5.20.14+) natively round-trips CamillaDSP YAML: it exports the same structured
`filters:`/`pipeline:` shape our compiler emits, and it is the only format REW can
re-import. `parse_rew` and `format_rew` are band-inverses — the bands emitted by
`format_rew` round-trip back through `parse_rew` modulo fresh ids. Both are pure (they
import only `audera.models` + `audera.domains.dsp.compiler`, plus stdlib `uuid`, `yaml`,
and pydantic), so they are Docker-free and unit-testable with zero I/O.

Pre-amp is intentionally not round-tripped: `format_rew` emits only the band biquads (the
editor's auto-ceiling owns the pre-amp on import), so a pasted export re-derives a
clip-safe pre-amp rather than carrying a stale one.
"""

import uuid
from typing import Any, Optional, get_args

import yaml
from pydantic import BaseModel, Field

from audera.domains.dsp.compiler import _band_to_biquad
from audera.models.dsp import DEFAULT_Q, PASS_TYPES, Band

# CamillaDSP Biquad `parameters.type` values we support, derived from the model literal so
# the parser can never drift from `audera.models.dsp.Band`. Every other biquad subtype
# (Notch, Bandpass, Allpass, the first-order shelves, …) and non-Biquad filter (Conv,
# BiquadCombo, Gain, …) is unsupported and routed to `skipped`, mirroring REW's own
# "unsupported filter types are skipped with a warning".
_SUPPORTED_TYPES = frozenset(get_args(Band.model_fields['type'].annotation))


class RewImport(BaseModel):
    """A `class` that represents the result of parsing a CamillaDSP YAML export.

    Attributes
    ----------
    bands: `list[audera.models.dsp.Band]`
        The parsed bands, each with a fresh id, ready to append to a configuration.
    skipped: `list[str]`
        The names of filters that could not be parsed (unsupported biquad subtype or
        non-Biquad filter), or the raw text when the document itself is unparseable —
        surfaced so nothing is dropped silently.
    """

    bands: list[Band] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


def _bypassed_by_name(pipeline: Any) -> dict[str, bool]:
    """Returns a `{filter_name: bypassed}` map from a CamillaDSP pipeline.

    A filter absent from every pipeline step is treated as active (`enabled=True`); a
    referencing step's `bypassed` flag (default `False`) sets the band's enabled state.

    Parameters
    ----------
    pipeline: `Any`
        The `pipeline` value from a parsed CamillaDSP document (a list of steps, or any
        other type when the field is malformed or absent).
    """
    bypassed: dict[str, bool] = {}
    if not isinstance(pipeline, list):
        return bypassed
    for step in pipeline:
        if not isinstance(step, dict) or step.get('type') != 'Filter':
            continue
        flag = bool(step.get('bypassed', False))
        for name in step.get('names', []) or []:
            bypassed[str(name)] = flag
    return bypassed


def _filter_to_band(filter_: Any, enabled: bool) -> Optional[Band]:
    """Returns a fresh-id `Band` for a supported CamillaDSP Biquad filter, else `None`.

    Parameters
    ----------
    filter_: `Any`
        A single entry from the document's `filters` mapping.
    enabled: `bool`
        Whether the filter's pipeline step is active (derived from `bypassed`).
    """
    if not isinstance(filter_, dict) or filter_.get('type') != 'Biquad':
        return None
    parameters = filter_.get('parameters')
    if not isinstance(parameters, dict):
        return None
    band_type = parameters.get('type')
    freq = parameters.get('freq')
    if band_type not in _SUPPORTED_TYPES or freq is None:
        return None
    return Band(
        id=uuid.uuid4().hex,
        type=band_type,
        freq=float(freq),
        gain=0.0 if band_type in PASS_TYPES else float(parameters.get('gain', 0.0)),
        q=float(parameters.get('q', DEFAULT_Q)),
        enabled=enabled,
    )


def parse_rew(text: str) -> RewImport:
    """Returns the bands parsed from a CamillaDSP YAML (or JSON) export.

    `yaml.safe_load` parses YAML — and JSON, a YAML subset, so REW/CamillaDSP JSON pastes
    parse too. Each `filters` entry that is a supported `Biquad` becomes a fresh-id `Band`
    (its enabled state read from the pipeline's `bypassed`); every unsupported filter is
    collected in `skipped`, and an unparseable document falls back to a single skipped
    entry (its raw text) so nothing is dropped silently.

    Parameters
    ----------
    text: `str`
        The CamillaDSP YAML/JSON export to parse.
    """
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        document = None
    if not isinstance(document, dict):
        stripped = text.strip()
        return RewImport(bands=[], skipped=[stripped] if stripped else [])
    filters = document.get('filters')
    if not isinstance(filters, dict):
        stripped = text.strip()
        return RewImport(bands=[], skipped=[stripped] if stripped else [])
    bypassed = _bypassed_by_name(document.get('pipeline'))
    bands: list[Band] = []
    skipped: list[str] = []
    for name, filter_ in filters.items():
        band = _filter_to_band(filter_, enabled=not bypassed.get(str(name), False))
        if band is None:
            skipped.append(str(name))
        else:
            bands.append(band)
    return RewImport(bands=bands, skipped=skipped)


def format_rew(preamp_db: float, bands: list[Band]) -> str:
    """Returns a CamillaDSP YAML fragment for a set of bands, importable by REW.

    Emits a `{filters, pipeline}` fragment — one `Biquad` per band (built by the shared
    `compiler._band_to_biquad`, so export and compile can never drift) plus a stereo
    pipeline step per band whose `bypassed` mirrors the band's enabled state. The leading
    `filters:` tag is the shape REW requires to import. The pre-amp is intentionally not
    emitted (the editor's auto-ceiling owns it on import), so `preamp_db` is accepted for
    call-site symmetry with the saved config but not serialized.

    Parameters
    ----------
    preamp_db: `float`
        The pre-amp attenuation in dB. Accepted for signature symmetry with the editor's
        saved config; not written to the fragment (pre-amp is not round-tripped).
    bands: `list[audera.models.dsp.Band]`
        The parametric-EQ bands to format.
    """
    filters: dict[str, dict] = {}
    pipeline: list[dict] = []
    for band in bands:
        filters[band.id] = _band_to_biquad(band)
        pipeline.append({'type': 'Filter', 'channels': [0, 1], 'names': [band.id], 'bypassed': not band.enabled})
    return yaml.safe_dump({'filters': filters, 'pipeline': pipeline}, sort_keys=False)
