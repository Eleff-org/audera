"""Audio stream"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, Optional

from pytensils import config


@dataclass
class Stream:
    """A `class` that represents a Plex-Amp audio stream.

    Attributes
    ----------
    id: `str`
        The stream identifier.
    name: `str`
        The display name of the stream.
    uri: `str`
        The Snapcast stream URI.
    status: `Literal['playing', 'paused', 'idle']`
        The current playback status.
    current_track: `Optional[str]`
        The title of the currently playing track, or `None` when idle.
    """

    id: str
    name: str
    uri: str
    status: Literal['playing', 'paused', 'idle'] = field(default='idle')
    current_track: Optional[str] = field(default=None)

    def from_dict(dict_object: dict) -> Stream:
        """Returns a `Stream` object from a `dict`."""
        if not isinstance(dict_object, dict):
            raise TypeError('Object must be a `dict`.')
        missing_keys = [key for key in ['id', 'name', 'uri', 'status', 'current_track'] if key not in dict_object]
        if missing_keys:
            raise KeyError(
                'Missing keys. The `dict` object is missing the following required keys [%s].'
                % (','.join(["'%s'" % key for key in missing_keys]))
            )
        dict_object['current_track'] = dict_object['current_track'] or None
        return Stream(**dict_object)

    def from_config(config: config.Handler) -> Stream:
        """Returns a `Stream` object from a `pytensils.config.Handler` object."""
        return Stream.from_dict(config.to_dict()['stream'])

    def to_dict(self):
        """Returns a `Stream` object as a `dict`."""
        return {
            'id': self.id,
            'name': self.name,
            'uri': self.uri,
            'status': self.status,
            'current_track': self.current_track if self.current_track is not None else '',
        }

    def __repr__(self):
        """Returns a `Stream` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)

    def __eq__(self, compare):
        """Returns `True` when compare is an instance of self."""
        if isinstance(compare, Stream):
            return (
                self.id == compare.id
                and self.name == compare.name
                and self.uri == compare.uri
                and self.status == compare.status
                and self.current_track == compare.current_track
            )
        return False
