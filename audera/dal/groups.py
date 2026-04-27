"""Group configuration-layer"""

import os
from typing import List, Union

import duckdb
from pytensils import config

from audera.dal import path
from audera.models import player

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'groups')
DTYPES: dict = {
    'group': {
        'id': 'str',
        'name': 'str',
        'client_ids': 'list',
        'stream_id': 'str',
        'muted': 'bool',
        'volume': 'int',
    }
}


def exists(id: str) -> bool:
    """Returns `True` when the group configuration file exists.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(group: player.Group) -> config.Handler:
    """Creates the group configuration file and returns the contents as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(path=PATH, file_name='.'.join([group.id, 'json']), create=True)
    config_ = config_.from_dict({'group': group.to_dict()})
    return config_


def get(id: str) -> config.Handler:
    """Returns the contents of the group configuration as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    config_ = config.Handler(path=PATH, file_name='.'.join([id, 'json']))
    config_.validate(DTYPES)
    return config_


def get_or_create(group: player.Group) -> config.Handler:
    """Creates or reads the group configuration file and returns the contents as
    a `pytensils.config.Handler` object.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    if exists(group.id):
        return get(group.id)
    else:
        return create(group)


def save(group: player.Group) -> config.Handler:
    """Saves the group configuration to `~/.audera/groups/{group.id}.json`.

    Parameters
    ----------
    group: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(path=PATH, file_name='.'.join([group.id, 'json']), create=True)
    config_ = config_.from_dict({'group': group.to_dict()})
    return config_


def update(new: player.Group) -> player.Group:
    """Updates the group configuration file `~/.audera/groups/{group.id}.json`.

    Parameters
    ----------
    new: `audera.models.player.Group`
        An instance of an `audera.models.player.Group` object.
    """
    config_ = get_or_create(new)
    group = player.Group.from_config(config=config_)
    if not group == new:
        config_ = config_.from_dict({'group': new.to_dict()})
        return new
    else:
        return group


def delete(id: str):
    """Deletes the configuration file for a group.

    Parameters
    ----------
    id: `str`
        The Snapcast group identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def get_group(id: str) -> player.Group:
    """Returns the group as an `audera.models.player.Group` object."""
    return player.Group.from_config(get(id))


def attach_client(group_id: str, client_id: str) -> player.Group:
    """Attaches a Snapcast client to a group.

    Parameters
    ----------
    group_id: `str`
        The Snapcast group identifier.
    client_id: `str`
        The Snapcast client identifier.
    """
    group = get_group(group_id)
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
    group = get_group(group_id)
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
    group = get_group(group_id)
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
