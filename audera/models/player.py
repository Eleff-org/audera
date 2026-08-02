"""Audio-player"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class Player(BaseModel):
    """A `class` that represents a Snapcast client.

    Attributes
    ----------
    id: `str`
        The Snapcast client identifier.
    host: `str`
        The ip-address of the Snapcast client.
    port: `int`
        The port of the Snapcast client.
    connected: `bool`
        Whether the client is connected to the Snapcast server.
    volume: `int`
        An integer value from 0 to 100 that sets the loudness of playback.
    muted: `bool`
        Whether the client is muted.
    group_id: `str`
        The identifier of the Snapcast group this client belongs to.
    name: `str`
        The display name from Snapcast responses; not persisted.
    """

    id: str
    host: str
    port: int
    connected: bool = False
    volume: int = 100
    muted: bool = False
    group_id: str = ''
    name: str = Field(default='', exclude=True)
    latency_ms: int = Field(default=0, ge=-500, le=500, exclude=True)

    def __eq__(self, compare) -> bool:
        """Returns `True` when compare is an instance of self, excluding `name`."""
        if isinstance(compare, Player):
            return (
                self.id == compare.id
                and self.host == compare.host
                and self.port == compare.port
                and self.connected == compare.connected
                and self.volume == compare.volume
                and self.muted == compare.muted
                and self.group_id == compare.group_id
                and self.latency_ms == compare.latency_ms
            )
        return False

    def __hash__(self) -> int:
        return hash(self.id)


class Group(BaseModel):
    """A `class` that represents a Snapcast group.

    Attributes
    ----------
    id: `str`
        The Snapcast group identifier.
    name: `str`
        The name of the group.
    client_ids: `List[str]`
        A list of Snapcast client identifiers belonging to this group.
    stream_id: `str`
        The identifier of the stream assigned to this group.
    muted: `bool`
        Whether the group is muted.
    volume: `int`
        An integer value from 0 to 100 that sets the loudness of playback.
    """

    id: str
    name: str
    client_ids: List[str] = Field(default_factory=list)
    stream_id: str = ''
    muted: bool = False
    volume: int = 100
