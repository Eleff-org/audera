"""Stream configuration-layer"""

import json
import os
from typing import List, Union

import duckdb

from audera.dal import path
from audera.models import stream

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'streams')


def exists(id: str) -> bool:
    """Returns `True` when the stream configuration file exists.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(stream_: stream.Stream) -> stream.Stream:
    """Creates the stream configuration file and returns the `Stream` object.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    return save(stream_)


def get(id: str) -> stream.Stream:
    """Returns the stream configuration as a `Stream` object.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    file_path = os.path.join(PATH, '.'.join([id, 'json']))
    with open(file_path, 'r') as f:
        data = json.load(f)
    return stream.Stream.from_dict(data['stream'])


def get_or_create(stream_: stream.Stream) -> stream.Stream:
    """Creates or reads the stream configuration file and returns the `Stream` object.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    if exists(stream_.id):
        return get(stream_.id)
    else:
        return create(stream_)


def save(stream_: stream.Stream) -> stream.Stream:
    """Saves the stream configuration to `~/.audera/streams/{stream_.id}.json`.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    file_path = os.path.join(PATH, '.'.join([stream_.id, 'json']))
    with open(file_path, 'w') as f:
        json.dump({'stream': stream_.to_dict()}, f, indent=2)
    return stream_


def update(new: stream.Stream) -> stream.Stream:
    """Updates the stream configuration file `~/.audera/streams/{stream_.id}.json`.

    Parameters
    ----------
    new: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    existing = get_or_create(new)
    if not existing == new:
        return save(new)
    else:
        return existing


def delete(id: str):
    """Deletes the configuration file for a stream.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect().execute(
        'CREATE TABLE streams AS SELECT "stream".* FROM read_json_auto(?)', (os.path.join(PATH, '*.json'),)
    )


def query_to_streams(cursor: duckdb.DuckDBPyConnection) -> List[stream.Stream]:
    columns = [desc[0] for desc in cursor.description]
    return [stream.Stream.from_dict(dict(zip(columns, row))) for row in cursor.fetchall()]


def get_all_streams() -> List[stream.Stream]:
    """Returns all streams as a list of `audera.models.stream.Stream` objects."""
    try:
        with connection() as conn:
            return query_to_streams(conn.execute('SELECT * FROM streams'))
    except duckdb.IOException:
        return []
