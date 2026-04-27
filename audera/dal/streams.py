"""Stream configuration-layer"""

import os
from typing import List, Union

import duckdb
from pytensils import config

from audera.dal import path
from audera.models import stream

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'streams')
DTYPES: dict = {
    'stream': {
        'id': 'str',
        'name': 'str',
        'uri': 'str',
        'status': 'str',
        'current_track': 'str',
    }
}


def exists(id: str) -> bool:
    """Returns `True` when the stream configuration file exists.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(stream_: stream.Stream) -> config.Handler:
    """Creates the stream configuration file and returns the contents as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(path=PATH, file_name='.'.join([stream_.id, 'json']), create=True)
    config_ = config_.from_dict({'stream': stream_.to_dict()})
    return config_


def get(id: str) -> config.Handler:
    """Returns the contents of the stream configuration as a
    `pytensils.config.Handler` object.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    config_ = config.Handler(path=PATH, file_name='.'.join([id, 'json']))
    config_.validate(DTYPES)
    return config_


def get_or_create(stream_: stream.Stream) -> config.Handler:
    """Creates or reads the stream configuration file and returns the contents as
    a `pytensils.config.Handler` object.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    if exists(stream_.id):
        return get(stream_.id)
    else:
        return create(stream_)


def save(stream_: stream.Stream) -> config.Handler:
    """Saves the stream configuration to `~/.audera/streams/{stream_.id}.json`.

    Parameters
    ----------
    stream_: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    config_ = config.Handler(path=PATH, file_name='.'.join([stream_.id, 'json']), create=True)
    config_ = config_.from_dict({'stream': stream_.to_dict()})
    return config_


def update(new: stream.Stream) -> stream.Stream:
    """Updates the stream configuration file `~/.audera/streams/{stream_.id}.json`.

    Parameters
    ----------
    new: `audera.models.stream.Stream`
        An instance of an `audera.models.stream.Stream` object.
    """
    config_ = get_or_create(new)
    stream_ = stream.Stream.from_config(config=config_)
    if not stream_ == new:
        config_ = config_.from_dict({'stream': new.to_dict()})
        return new
    else:
        return stream_


def delete(id: str):
    """Deletes the configuration file for a stream.

    Parameters
    ----------
    id: `str`
        The stream identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))


def get_stream(id: str) -> stream.Stream:
    """Returns the stream as an `audera.models.stream.Stream` object."""
    return stream.Stream.from_config(get(id))


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
