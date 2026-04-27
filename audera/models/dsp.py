"""DSP configuration"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class DSPConfig:
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
    pipeline: dict = field(default_factory=dict)
    enabled: bool = field(default=True)

    def from_dict(dict_object: dict) -> DSPConfig:
        """Returns a `DSPConfig` object from a `dict`."""
        if not isinstance(dict_object, dict):
            raise TypeError('Object must be a `dict`.')
        missing_keys = [key for key in ['id', 'player_id', 'pipeline', 'enabled'] if key not in dict_object]
        if missing_keys:
            raise KeyError(
                'Missing keys. The `dict` object is missing the following required keys [%s].'
                % (','.join(["'%s'" % key for key in missing_keys]))
            )
        return DSPConfig(**dict_object)

    def to_dict(self):
        """Returns a `DSPConfig` object as a `dict`."""
        return {
            'id': self.id,
            'player_id': self.player_id,
            'pipeline': self.pipeline,
            'enabled': self.enabled,
        }

    def __repr__(self):
        """Returns a `DSPConfig` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)

    def __eq__(self, compare):
        """Returns `True` when compare is an instance of self."""
        if isinstance(compare, DSPConfig):
            return (
                self.id == compare.id
                and self.player_id == compare.player_id
                and self.pipeline == compare.pipeline
                and self.enabled == compare.enabled
            )
        return False
