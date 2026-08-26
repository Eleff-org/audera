"""Streamer service settings"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """A `class` that represents the streamer service settings.

    Attributes
    ----------
    plexamp_host: `str`
        The hostname or IP address of the PlexAmp headless instance.
    snapserver_host: `str`
        The hostname or IP address of the Snapserver instance.
    features: `dict[str, str]`
        A mapping of feature-flag keys to the selected option value.
    """

    plexamp_host: str
    snapserver_host: str
    features: dict[str, str] = Field(default_factory=dict)
