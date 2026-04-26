""" Player configuration-layer """

import os
from typing import List, Union

import duckdb
from pytensils import config

from audera.dal import path
from audera.models import player

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'players')
DTYPES: dict = {
    'player': {
        'id': 'str',
        'host': 'str',
        'port': 'int',
        'connected': 'bool',
        'volume': 'int',
        'muted': 'bool',
        'group_id': 'str',
    }
}


def exists(id: str) -> bool:
    """ Returns `True` when the player configuration file exists.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(player_: player.Player) -> config.Handler:
    """ Creates the player configuration file and returns the contents as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(
        path=PATH,
        file_name='.'.join([player_.id, 'json']),
        create=True
    )
    config_ = config_.from_dict({'player': player_.to_dict()})
    return config_


def get(id: str) -> config.Handler:
    """ Returns the contents of the player configuration as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    config_ = config.Handler(
        path=PATH,
        file_name='.'.join([id, 'json'])
    )
    config_.validate(DTYPES)
    return config_


def get_or_create(player_: player.Player) -> config.Handler:
    """ Creates or reads the player configuration file and returns the contents as
    a `pytensils.config.Handler` object.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if exists(player_.id):
        return get(player_.id)
    else:
        return create(player_)


def save(player_: player.Player) -> config.Handler:
    """ Saves the player configuration to `~/.audera/players/{player_.id}.json`.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(
        path=PATH,
        file_name='.'.join([player_.id, 'json']),
        create=True
    )
    config_ = config_.from_dict({'player': player_.to_dict()})
    return config_


def update(new: player.Player) -> player.Player:
    """ Updates the player configuration file `~/.audera/players/{player_.id}.json`.

    Parameters
    ----------
    new: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    config_ = get_or_create(new)
    player_ = player.Player.from_config(config=config_)
    if not player_ == new:
        config_ = config_.from_dict({'player': new.to_dict()})
        return new
    else:
        return player_


def delete(id: str):
    """ Deletes the configuration file for a player.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def get_player(id: str) -> player.Player:
    """ Returns the player as an `audera.models.player.Player` object. """
    return player.Player.from_config(get(id))


def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect().execute(
        'CREATE TABLE players AS SELECT player.* FROM read_json_auto(?)',
        (os.path.join(PATH, '*.json'),)
    )


def query_to_players(cursor: duckdb.DuckDBPyConnection) -> List[player.Player]:
    columns = [desc[0] for desc in cursor.description]
    return [player.Player.from_dict(dict(zip(columns, row))) for row in cursor.fetchall()]


def get_player_by_host(host: str) -> player.Player:
    """ Returns the player with the given host address.

    Parameters
    ----------
    host: `str`
        The ip-address of the Snapcast client.
    """
    try:
        with connection() as conn:
            return query_to_players(
                conn.execute(
                    "SELECT * FROM players WHERE host = '%s'" % str(host)
                )
            )[0]
    except (duckdb.IOException, IndexError):
        return None


def get_all_players() -> List[player.Player]:
    """ Returns all players as a list of `audera.models.player.Player` objects. """
    try:
        with connection() as conn:
            return query_to_players(conn.execute('SELECT * FROM players'))
    except duckdb.IOException:
        return []


def get_all_connected_players() -> List[player.Player]:
    """ Returns all connected players as a list of `audera.models.player.Player` objects. """
    try:
        with connection() as conn:
            return query_to_players(
                conn.execute('SELECT * FROM players WHERE connected = True')
            )
    except duckdb.IOException:
        return []
