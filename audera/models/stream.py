"""Audio stream"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class Stream(BaseModel):
    """A `class` that represents what PlexAmp is currently playing.

    Unrelated to a Snapcast stream. Built fresh from `PlexAmpClient.get_now_playing` on each
    poll, and not persisted.

    Attributes
    ----------
    id: `str`
        Plex's `ratingKey` for the track.
    name: `str`
        The display name, Plex's `parentTitle` (the album), falling back to the track.
    uri: `str`
        Unused; PlexAmp's timeline reports no URI, so this is always `''`.
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
