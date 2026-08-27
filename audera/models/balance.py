"""Reference-balance snapshot"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReferenceBalance(BaseModel):
    """A saved snapshot of per-player volume percents, keyed on Snapcast player id.

    Attributes
    ----------
    volumes: `dict[str, int]`
        A mapping of Snapcast player id to its saved volume percent (0-100).
    """

    volumes: dict[str, int] = Field(default_factory=dict)
