"""DSP configuration"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field


class Band(BaseModel):
    """A `class` that represents a single parametric-EQ band.

    Attributes
    ----------
    id: `str`
        The band identifier (stable key for UI rows).
    type: `Literal['Peaking', 'LowShelf', 'HighShelf', 'Lowpass', 'Highpass']`
        The biquad filter type.
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
    type: Literal['Peaking', 'LowShelf', 'HighShelf', 'Lowpass', 'Highpass'] = 'Peaking'
    freq: float
    gain: float = 0.0
    q: float = 0.707
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
    id: `str`
        The DSP configuration identifier and file key.
    preamp_db: `float`
        The pre-amp Gain filter attenuation in dB.
    bands: `list[Band]`
        The parametric-EQ bands (source of truth).
    enabled: `bool`
        Whether the DSP configuration is active.
    """

    id: str
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
            'id': self.id,
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
    (`model_dump()`/`model_validate`) — there is no legacy on-disk shape to preserve.

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
