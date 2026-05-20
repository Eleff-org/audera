"""Group configuration-layer"""

import json
import os
from typing import List, Union

import duckdb

from audera.dal import path
from audera.models import player

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'groups')


def exists(id: str) -> bool:
    """Returns `True` when the group configuration file exists.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(group: player.Group) -> player.Group:
    """Creates the group configuration file and returns the `Group` object.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    return save(group)


def get(id: str) -> player.Group:
    """Returns the group configuration as a `Group` object.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    file_path = os.path.join(PATH, '.'.join([id, 'json']))
    with open(file_path, 'r') as f:
        data = json.load(f)
    return player.Group.from_dict(data['group'])


def get_or_create(group: player.Group) -> player.Group:
    """Creates or reads the group configuration file and returns the `Group` object.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    if exists(group.id):
        return get(group.id)
    else:
        return create(group)


def save(group: player.Group) -> player.Group:
    """Saves the group configuration to `~/.audera/groups/{group.id}.json`.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    file_path = os.path.join(PATH, '.'.join([group.id, 'json']))
    with open(file_path, 'w') as f:
        json.dump({'group': group.to_dict()}, f, indent=2)
    return group


def update(new: player.Group) -> player.Group:
    """Updates the group configuration file `~/.audera/groups/{group.id}.json`.

    Parameters
    ----------
    new: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    existing = get_or_create(new)
    if not existing == new:
        return save(new)
    else:
        return existing


def delete(id: str):
    """Deletes the configuration file for a group.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def attach_client(group_id: str, client_id: str) -> player.Group:
    """Attaches a Snapcast client to a group.

    Parameters
    ----------
    group_id: `str`
        The Snapcast group identifier.
    client_id: `str`
        The Snapcast client identifier.
    """
    group = get(group_id)
    if client_id in group.client_ids:
        return group
    group.client_ids.append(client_id)
    return update(group)


def detach_client(group_id: str, client_id: str) -> player.Group:
    """Detaches a Snapcast client from a group.

    Parameters
    ----------
    group_id: `str`
        The Snapcast group identifier.
    client_id: `str`
        The Snapcast client identifier.
    """
    group = get(group_id)
    if client_id not in group.client_ids:
        return group
    group.client_ids.remove(client_id)
    return update(group)


def assign_stream(group_id: str, stream_id: str) -> player.Group:
    """Assigns a stream to a group.

    Parameters
    ----------
    group_id: `str`
        The Snapcast group identifier.
    stream_id: `str`
        The Snapcast stream identifier.
    """
    group = get(group_id)
    if group.stream_id == stream_id:
        return group
    group.stream_id = stream_id
    return update(group)


def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect().execute(
        'CREATE TABLE groups AS SELECT "group".* FROM read_json_auto(?)', (os.path.join(PATH, '*.json'),)
    )


def query_to_groups(cursor: duckdb.DuckDBPyConnection) -> List[player.Group]:
    columns = [desc[0] for desc in cursor.description]
    return [player.Group.from_dict(dict(zip(columns, row))) for row in cursor.fetchall()]


def get_all_groups() -> List[player.Group]:
    """Returns all groups as a list of `audera.models.player.Group` objects."""
    try:
        with connection() as conn:
            return query_to_groups(conn.execute('SELECT * FROM groups'))
    except duckdb.IOException:
        return []
