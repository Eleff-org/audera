"""Import/export parametric-EQ bands as REW / Equalizer APO filter text.

`parse_rew` and `format_rew` are band-inverses: the bands emitted by `format_rew`
round-trip back through `parse_rew` modulo fresh ids and float-format precision. Both
are pure — they import only `audera.models` (+ stdlib `re`/`uuid` and pydantic), so they
are Docker-free and unit-testable with zero I/O.

Pre-amp is intentionally *not* round-tripped: `parse_rew` recognizes a `Preamp:` line but
never applies it (the editor's auto-ceiling owns pre-amp on import), and `format_rew` emits
the honest saved pre-amp only so the exported text stays safe to paste into another tool.
"""

import re
import uuid

from pydantic import BaseModel, Field

from audera.models.dsp import Band

# REW/Equalizer APO filter kinds → `Band.type`. `LSC`/`HSC` are REW's "corner" shelf
# variants, which we treat as ordinary shelves. Unsupported kinds (`NO` notch, `AP`
# allpass, `BP` bandpass) are deliberately absent so their lines land in `skipped`.
_PARSE_TYPES = {
    'PK': 'Peaking',
    'LS': 'LowShelf',
    'LSC': 'LowShelf',
    'HS': 'HighShelf',
    'HSC': 'HighShelf',
    'LP': 'Lowpass',
    'HP': 'Highpass',
}

# `Band.type` → REW filter kind (the inverse of `_PARSE_TYPES`, collapsing the shelf
# variants onto the plain shelf codes).
_FORMAT_TYPES = {
    'Peaking': 'PK',
    'LowShelf': 'LS',
    'HighShelf': 'HS',
    'Lowpass': 'LP',
    'Highpass': 'HP',
}

# Pass filters carry no gain, so `format_rew` omits `Gain` for them (matching the compiler
# and the editor's disabled gain field) while still emitting `Q`.
_PASS_TYPES = {'Lowpass', 'Highpass'}

_DEFAULT_Q = 0.707

_NUMBER = r'[-+]?\d*\.?\d+'

# `Preamp: -6.0 dB` — case-insensitive; recognized so it is never mistaken for garbage.
_PREAMP_RE = re.compile(r'^Preamp\s*:', re.IGNORECASE)

# `Filter [N]: ON|OFF <KIND> Fc <f> Hz [Gain <g> dB] [Q <q>]`, whitespace-tolerant. The
# leading index is optional so Equalizer APO's `Filter: …` lines parse too. `Fc`/`Gain`/`Q`
# are each optional captures so a supported kind that is missing `Fc` can be routed to
# `skipped` rather than silently defaulted.
_FILTER_RE = re.compile(
    r'^Filter\s*\d*\s*:\s*'
    r'(?P<state>ON|OFF)\s+'
    r'(?P<kind>[A-Za-z]+)'
    rf'(?:\s+Fc\s+(?P<fc>{_NUMBER})\s*Hz)?'
    rf'(?:\s+Gain\s+(?P<gain>{_NUMBER})\s*dB)?'
    rf'(?:\s+Q\s+(?P<q>{_NUMBER}))?',
    re.IGNORECASE,
)


class RewImport(BaseModel):
    """A `class` that represents the result of parsing a REW filter export.

    Attributes
    ----------
    bands: `list[audera.models.dsp.Band]`
        The parsed bands, each with a fresh id, ready to append to a configuration.
    skipped: `list[str]`
        The raw lines that could not be parsed (unsupported kind, missing `Fc`, or
        non-filter text), surfaced so nothing is dropped silently.
    """

    bands: list[Band] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)


def parse_rew(text: str) -> RewImport:
    """Returns the bands parsed from a REW / Equalizer APO filter export.

    Parsed line-by-line and never silently dropping: blank lines are ignored, a `Preamp:`
    line is recognized but neither applied nor skipped (the editor's auto-ceiling owns
    pre-amp), a supported filter line becomes a fresh-id `Band`, and everything else —
    unsupported kinds, filter lines missing `Fc`, or non-filter text — is collected in
    `skipped`.

    Parameters
    ----------
    text: `str`
        The REW / Equalizer APO filter export to parse.
    """
    bands: list[Band] = []
    skipped: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _PREAMP_RE.match(line):
            continue  # recognized, not applied, not skipped
        match = _FILTER_RE.match(line)
        mapped = _PARSE_TYPES.get(match.group('kind').upper()) if match else None
        fc = match.group('fc') if match else None
        if match is None or mapped is None or fc is None:
            skipped.append(line)
            continue
        gain = match.group('gain')
        q = match.group('q')
        bands.append(
            Band(
                id=uuid.uuid4().hex,
                type=mapped,  # type: ignore
                freq=float(fc),
                gain=float(gain) if gain is not None else 0.0,
                q=float(q) if q is not None else _DEFAULT_Q,
                enabled=match.group('state').upper() == 'ON',
            )
        )
    return RewImport(bands=bands, skipped=skipped)


def format_rew(preamp_db: float, bands: list[Band]) -> str:
    """Returns a REW-format filter export for a pre-amp and a set of bands.

    The first line is `Preamp: {preamp_db:.1f} dB` (the honest value — for a saved config
    this is the real auto-clamped pre-amp, so the text applies safely in another tool),
    followed by one 1-indexed `Filter` line per band. Pass filters omit `Gain` but still
    emit `Q`, so a pass band's `q` survives the round-trip.

    Parameters
    ----------
    preamp_db: `float`
        The pre-amp attenuation in dB, emitted for fidelity (`parse_rew` does not re-apply
        it).
    bands: `list[audera.models.dsp.Band]`
        The parametric-EQ bands to format.
    """
    lines = [f'Preamp: {preamp_db:.1f} dB']
    for index, band in enumerate(bands, start=1):
        kind = _FORMAT_TYPES[band.type]
        state = 'ON' if band.enabled else 'OFF'
        gain = '' if band.type in _PASS_TYPES else f' Gain {band.gain:.2f} dB'
        lines.append(f'Filter {index}: {state} {kind} Fc {band.freq:.1f} Hz{gain} Q {band.q:.3f}')
    return '\n'.join(lines)
