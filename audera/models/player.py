""" Audio-player """

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List

from pytensils import config


@dataclass
class Player():
    """ A `class` that represents a Snapcast client.

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
    """
    id: str
    host: str
    port: int
    connected: bool = field(default=False)
    volume: int = field(default=100)
    muted: bool = field(default=False)
    group_id: str = field(default='')

    def from_dict(dict_object: dict) -> Player:
        """ Returns a `Player` object from a `dict`. """
        if not isinstance(dict_object, dict):
            raise TypeError('Object must be a `dict`.')
        missing_keys = [
            key for key in ['id', 'host', 'port', 'connected', 'volume', 'muted', 'group_id']
            if key not in dict_object
        ]
        if missing_keys:
            raise KeyError(
                'Missing keys. The `dict` object is missing the following required keys [%s].' % (
                    ','.join(["'%s'" % key for key in missing_keys])
                )
            )
        return Player(**dict_object)

    def from_config(config: config.Handler) -> Player:
        """ Returns a `Player` object from a `pytensils.config.Handler` object. """
        return Player.from_dict(config.to_dict()['player'])

    def to_dict(self):
        """ Returns a `Player` object as a `dict`. """
        return {
            'id': self.id,
            'host': self.host,
            'port': self.port,
            'connected': self.connected,
            'volume': self.volume,
            'muted': self.muted,
            'group_id': self.group_id,
        }

    def __repr__(self):
        """ Returns a `Player` object as a json-formatted `str`. """
        return json.dumps(self.to_dict(), indent=2)

    def __eq__(self, compare):
        """ Returns `True` when compare is an instance of self. """
        if isinstance(compare, Player):
            return (
                self.id == compare.id
                and self.host == compare.host
                and self.port == compare.port
                and self.connected == compare.connected
                and self.volume == compare.volume
                and self.muted == compare.muted
                and self.group_id == compare.group_id
            )
        return False


@dataclass
class Group():
    """ A `class` that represents a Snapcast group.

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
    client_ids: List[str] = field(default_factory=list)
    stream_id: str = field(default='')
    muted: bool = field(default=False)
    volume: int = field(default=100)

    def from_dict(dict_object: dict) -> Group:
        """ Returns a `Group` object from a `dict`. """
        if not isinstance(dict_object, dict):
            raise TypeError('Object must be a `dict`.')
        missing_keys = [
            key for key in ['id', 'name', 'client_ids', 'stream_id', 'muted', 'volume']
            if key not in dict_object
        ]
        if missing_keys:
            raise KeyError(
                'Missing keys. The `dict` object is missing the following required keys [%s].' % (
                    ','.join(["'%s'" % key for key in missing_keys])
                )
            )
        return Group(**dict_object)

    def from_config(config: config.Handler) -> Group:
        """ Returns a `Group` object from a `pytensils.config.Handler` object. """
        return Group.from_dict(config.to_dict()['group'])

    def to_dict(self):
        """ Returns a `Group` object as a `dict`. """
        return {
            'id': self.id,
            'name': self.name,
            'client_ids': self.client_ids,
            'stream_id': self.stream_id,
            'muted': self.muted,
            'volume': self.volume,
        }

    def __repr__(self):
        """ Returns a `Group` object as a json-formatted `str`. """
        return json.dumps(self.to_dict(), indent=2)

    def __eq__(self, compare):
        """ Returns `True` when compare is an instance of self. """
        if isinstance(compare, Group):
            return (
                self.id == compare.id
                and self.name == compare.name
                and self.client_ids == compare.client_ids
                and self.stream_id == compare.stream_id
                and self.muted == compare.muted
                and self.volume == compare.volume
            )
        return False
