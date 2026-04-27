"""Streamer service settings"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pytensils import config


@dataclass
class Settings:
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

    def from_dict(dict_object: dict) -> Settings:
        """Returns a `Settings` object from a `dict`.

        Parameters
        ----------
        dict_object : `dict`
            The dictionary object to convert to a `Settings` object.
        """
        if not isinstance(dict_object, dict):
            raise TypeError('Object must be a `dict`.')

        missing_keys = [key for key in ['plexamp_host', 'snapserver_host'] if key not in dict_object]
        if missing_keys:
            raise KeyError(
                'Missing keys. The `dict` object is missing the following required keys [%s].'
                % (','.join(["'%s'" % key for key in missing_keys]))
            )

        return Settings(**dict_object)

    def from_config(config: config.Handler) -> Settings:
        """Returns a `Settings` object from a `pytensils.config.Handler` object.

        Parameters
        ----------
        config: `pytensils.config.Handler`
            An instance of a `pytensils.config.Handler` object.
        """
        return Settings.from_dict(config.to_dict()['settings'])

    def to_dict(self) -> dict:
        """Returns a `Settings` object as a `dict`."""
        return {
            'plexamp_host': self.plexamp_host,
            'snapserver_host': self.snapserver_host,
        }

    def __repr__(self) -> str:
        """Returns a `Settings` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)

    def __eq__(self, compare) -> bool:
        """Returns `True` when compare is an instance of self.

        Parameters
        ----------
        compare: `Settings`
            An instance of a `Settings` object.
        """
        if isinstance(compare, Settings):
            return self.plexamp_host == compare.plexamp_host and self.snapserver_host == compare.snapserver_host
        return False
