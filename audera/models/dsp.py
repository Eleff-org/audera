"""DSP configuration"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field


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
        }

    def __repr__(self) -> str:
        """Returns a `DSPConfig` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)
