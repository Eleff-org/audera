"""DSP configuration"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

# Butterworth Q ≈ 1/√2 — the maximally-flat response with no resonant peak; the standard
# default when a filter specifies no Q.
DEFAULT_Q = 0.707

# Pass filters (`Lowpass`/`Highpass`) carry no gain; every other band type does. Centralized
# here so the compiler, REW interop, and the editor share one type taxonomy.
PASS_TYPES = frozenset({'Lowpass', 'Highpass'})


class Band(BaseModel):
    """A `class` that represents a single parametric-EQ band.

    Attributes
    ----------
    id: `str`
        The band identifier (stable key for UI rows).
    type: `Literal['Peaking', 'Lowshelf', 'Highshelf', 'Lowpass', 'Highpass']`
        The biquad filter type, cased to match CamillaDSP's own parameter names.
    freq: `float`
        The center/corner frequency in Hz.
    gain: `float`
        The gain in dB (ignored for `Lowpass`/`Highpass`).
    q: `float`
        The filter Q (width).
    enabled: `bool`
        Whether the band is active.
    """

    id: str
    type: Literal['Peaking', 'Lowshelf', 'Highshelf', 'Lowpass', 'Highpass'] = 'Peaking'
    freq: float
    gain: float = 0.0
    q: float = DEFAULT_Q
    enabled: bool = True

    @classmethod
    def from_dict(cls, dict_object: dict) -> 'Band':
        """Returns a `Band` object from a `dict`."""
        return cls.model_validate(dict_object)

    def to_dict(self) -> dict:
        """Returns a `Band` object as a `dict`."""
        return {
            'id': self.id,
            'type': self.type,
            'freq': self.freq,
            'gain': self.gain,
            'q': self.q,
            'enabled': self.enabled,
        }

    def __repr__(self) -> str:
        """Returns a `Band` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)


class DSPConfig(BaseModel):
    """A `class` that represents a parametric-EQ configuration.

    Bands are the source of truth; the CamillaDSP pipeline is a derived artifact
    compiled from `preamp_db` + `bands` on Save (see `audera/domains/dsp/`).

    Attributes
    ----------
    player_id: `str`
        The player identifier and file key (the config lives at `dsp/{player_id}.json`,
        so the filename is the link — no separate FK is needed).
    preamp_db: `float`
        The pre-amp Gain filter attenuation in dB.
    bands: `list[Band]`
        The parametric-EQ bands (source of truth).
    enabled: `bool`
        Whether the DSP configuration is active.
    """

    player_id: str
    preamp_db: float = 0.0
    bands: list[Band] = Field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, dict_object: dict) -> 'DSPConfig':
        """Returns a `DSPConfig` object from a `dict`."""
        return cls.model_validate(dict_object)

    def to_dict(self) -> dict:
        """Returns a `DSPConfig` object as a `dict`."""
        return {
            'player_id': self.player_id,
            'preamp_db': self.preamp_db,
            'bands': [band.to_dict() for band in self.bands],
            'enabled': self.enabled,
        }

    def __repr__(self) -> str:
        """Returns a `DSPConfig` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)


class Preset(BaseModel):
    """A `class` that represents a named, reusable set of parametric-EQ bands.

    A preset is its own entity (not a flavored `DSPConfig`): a display name plus a
    list of bands that can be cloned and appended onto any player's configuration.
    Unlike `Band`/`DSPConfig`, it serializes via pydantic directly
    (`model_dump()`/`model_validate`) — a brand-new type with no hand-written on-disk
    shape to preserve.

    Attributes
    ----------
    id: `str`
        The preset identifier (uuid; identity + file key).
    name: `str`
        The display name (not identity — duplicate names are allowed).
    bands: `list[Band]`
        The parametric-EQ bands captured by the preset.
    """

    id: str
    name: str
    bands: list[Band] = Field(default_factory=list)
