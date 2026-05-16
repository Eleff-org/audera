"""Streamer service settings"""

from __future__ import annotations

import json

from pydantic import BaseModel


class Settings(BaseModel):
    """A `class` that represents the streamer service settings.

    Attributes
    ----------
    plexamp_host: `str`
        The hostname or IP address of the PlexAmp headless instance.
    snapserver_host: `str`
        The hostname or IP address of the Snapserver instance.
    """

    plexamp_host: str
    snapserver_host: str

    @classmethod
    def from_dict(cls, dict_object: dict) -> 'Settings':
        """Returns a `Settings` object from a `dict`."""
        return cls.model_validate(dict_object)

    def to_dict(self) -> dict:
        """Returns a `Settings` object as a `dict`."""
        return {
            'plexamp_host': self.plexamp_host,
            'snapserver_host': self.snapserver_host,
        }

    def __repr__(self) -> str:
        """Returns a `Settings` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)
