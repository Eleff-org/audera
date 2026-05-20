"""Player configuration-layer"""

import json
import os
from typing import List, Optional, Union

import duckdb

from audera.dal import path
from audera.models import player

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'players')


def exists(id: str) -> bool:
    """Returns `True` when the player configuration file exists.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(player_: player.Player) -> player.Player:
    """Creates the player configuration file and returns the `Player` object.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    return save(player_)


def get(id: str) -> player.Player:
    """Returns the player configuration as a `Player` object.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    file_path = os.path.join(PATH, '.'.join([id, 'json']))
    with open(file_path, 'r') as f:
        data = json.load(f)
    return player.Player.from_dict(data['player'])


def get_or_create(player_: player.Player) -> player.Player:
    """Creates or reads the player configuration file and returns the `Player` object.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if exists(player_.id):
        return get(player_.id)
    else:
        return create(player_)


def save(player_: player.Player) -> player.Player:
    """Saves the player configuration to `~/.audera/players/{player_.id}.json`.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    file_path = os.path.join(PATH, '.'.join([player_.id, 'json']))
    with open(file_path, 'w') as f:
        json.dump({'player': player_.to_dict()}, f, indent=2)
    return player_


def update(new: player.Player) -> player.Player:
    """Updates the player configuration file `~/.audera/players/{player_.id}.json`.

    Parameters
    ----------
    new: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    existing = get_or_create(new)
    if not existing == new:
        return save(new)
    else:
        return existing


def delete(id: str):
    """Deletes the configuration file for a player.

    Parameters
    ----------
    id: `str`
        The Snapcast client identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect().execute(
        'CREATE TABLE players AS SELECT player.* FROM read_json_auto(?)', (os.path.join(PATH, '*.json'),)
    )


def query_to_players(cursor: duckdb.DuckDBPyConnection) -> List[player.Player]:
    columns = [desc[0] for desc in cursor.description]
    return [player.Player.from_dict(dict(zip(columns, row))) for row in cursor.fetchall()]


def get_player_by_host(host: str) -> Optional[player.Player]:
    """Returns the player with the given host address.

    Parameters
    ----------
    host: `str`
        The ip-address of the Snapcast client.
    """
    try:
        with connection() as conn:
            return query_to_players(conn.execute("SELECT * FROM players WHERE host = '%s'" % str(host)))[0]
    except (duckdb.IOException, IndexError):
        return None


def get_all_players() -> List[player.Player]:
    """Returns all players as a list of `audera.models.player.Player` objects."""
    try:
        with connection() as conn:
            return query_to_players(conn.execute('SELECT * FROM players'))
    except duckdb.IOException:
        return []


def get_all_connected_players() -> List[player.Player]:
    """Returns all connected players as a list of `audera.models.player.Player` objects."""
    try:
        with connection() as conn:
            return query_to_players(conn.execute('SELECT * FROM players WHERE connected = True'))
    except duckdb.IOException:
        return []
