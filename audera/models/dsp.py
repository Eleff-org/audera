"""DSP configuration"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, field_validator

_LOUDNESS_LOW_BOOST: float = 10.0
_LOUDNESS_HIGH_BOOST: float = 6.0
_LOUDNESS_FILTER_KEY: str = 'audera_loudness'
_PREAMP_FILTER_KEY: str = 'audera_preamp_attenuation'
_PREAMP_ATTENUATION_DB: float = -_LOUDNESS_LOW_BOOST


class DSPConfig(BaseModel):
    """A `class` that represents a CamillaDSP pipeline configuration.

    Attributes
    ----------
    id: `str`
        The DSP configuration identifier.
    player_id: `str`
        The identifier of the player this configuration belongs to.
    pipeline: `dict`
        The CamillaDSP pipeline configuration as a dictionary.
    enabled: `bool`
        Whether the DSP pipeline is active.
    """

    id: str
    player_id: str
    pipeline: dict = Field(default_factory=dict)
    enabled: bool = True
    loudness_enabled: bool = False
    loudness_reference_level: float = -25.0
    volume: int = 25

    @field_validator('loudness_reference_level', mode='before')
    @classmethod
    def _clamp_reference_level(cls, v: float) -> float:
        return max(-60.0, min(0.0, float(v)))

    @classmethod
    def from_dict(cls, dict_object: dict) -> 'DSPConfig':
        """Returns a `DSPConfig` object from a `dict`."""
        return cls.model_validate(dict_object)

    def to_dict(self) -> dict:
        """Returns a `DSPConfig` object as a `dict`."""
        return {
            'id': self.id,
            'player_id': self.player_id,
            'pipeline': self.pipeline,
            'enabled': self.enabled,
            'loudness_enabled': self.loudness_enabled,
            'loudness_reference_level': self.loudness_reference_level,
            'volume': self.volume,
        }

    def __repr__(self) -> str:
        """Returns a `DSPConfig` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)


def apply_loudness(pipeline: dict, reference_level_db: float = -25.0) -> dict:
    """Insert the audera_loudness Loudness filter into pipeline, preceded by a preamp
    attenuation Gain filter that offsets the Loudness filter's worst-case low_boost so
    the two together never exceed 0 dB of headroom.
    """
    pipeline = dict(pipeline)
    filters = dict(pipeline.get('filters', {}))
    steps = list(pipeline.get('pipeline', []))
    existing_names = {name for step in steps for name in step.get('names', [])}

    filters[_PREAMP_FILTER_KEY] = {
        'type': 'Gain',
        'parameters': {'gain': _PREAMP_ATTENUATION_DB},
    }
    if _PREAMP_FILTER_KEY not in existing_names:
        for channel in range(2):
            steps.append({'type': 'Filter', 'channels': [channel], 'names': [_PREAMP_FILTER_KEY]})

    filters[_LOUDNESS_FILTER_KEY] = {
        'type': 'Loudness',
        'parameters': {
            'reference_level': reference_level_db,
            'high_boost': _LOUDNESS_HIGH_BOOST,
            'low_boost': _LOUDNESS_LOW_BOOST,
            'fader': 'Main',
        },
    }
    if _LOUDNESS_FILTER_KEY not in existing_names:
        for channel in range(2):
            steps.append({'type': 'Filter', 'channels': [channel], 'names': [_LOUDNESS_FILTER_KEY]})

    pipeline['filters'] = filters
    pipeline['pipeline'] = steps
    return pipeline


def remove_loudness(pipeline: dict) -> dict:
    """Remove the audera_loudness filter, its preamp attenuation Gain filter, and their pipeline steps."""
    pipeline = dict(pipeline)
    pipeline['filters'] = {
        k: v for k, v in pipeline.get('filters', {}).items() if k not in (_LOUDNESS_FILTER_KEY, _PREAMP_FILTER_KEY)
    }
    pipeline['pipeline'] = [
        step
        for step in pipeline.get('pipeline', [])
        if _LOUDNESS_FILTER_KEY not in step.get('names', []) and _PREAMP_FILTER_KEY not in step.get('names', [])
    ]
    return pipeline
