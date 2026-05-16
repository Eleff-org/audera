"""Audio stream"""

from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class Stream(BaseModel):
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
    status: Literal['playing', 'paused', 'idle'] = 'idle'
    current_track: Optional[str] = None

    @field_validator('current_track', mode='before')
    @classmethod
    def _coerce_current_track(cls, v: object) -> Optional[str]:
        return str(v) if v else None

    @classmethod
    def from_dict(cls, dict_object: dict) -> 'Stream':
        """Returns a `Stream` object from a `dict`."""
        return cls.model_validate(dict_object)

    def to_dict(self) -> dict:
        """Returns a `Stream` object as a `dict`."""
        return {
            'id': self.id,
            'name': self.name,
            'uri': self.uri,
            'status': self.status,
            'current_track': self.current_track if self.current_track is not None else '',
        }

    def __repr__(self) -> str:
        """Returns a `Stream` object as a json-formatted `str`."""
        return json.dumps(self.to_dict(), indent=2)
