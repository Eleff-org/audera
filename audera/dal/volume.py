"""Per-player volume cache

`~/.audera/volume/{player_id}.json` holds `{'volume': {'player_id': '<raw-id>', 'percent': <int>}}`.

The raw player id is stored inside the document because `path.to_filename()` is lossy (MAC-address
colons become dashes). `get_all()` reads `player_id` from each document so callers always see the
original id.

Audera is the only writer of CamillaDSP volume, so a write-through DAL with observers is
sufficient and no periodic resync is needed.
"""

import glob
import json
import logging
import os
import threading
from typing import Callable, Union

from audera import io
from audera.dal import path

logger = logging.getLogger(__name__)

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'volume')

_WRITE_LOCK = threading.Lock()
_observers: list[Callable[[], None]] = []


def on_change(callback: Callable[[], None]) -> None:
    """Registers a callback invoked after any volume write."""
    _observers.append(callback)


def _notify_observers() -> None:
    for cb in _observers:
        try:
            cb()
        except Exception:
            logger.exception('volume observer failed')


def get(player_id: str) -> int | None:
    """Returns the cached volume percent for a player, or ``None`` if absent or malformed."""
    file_path = os.path.join(PATH, path.to_filename(player_id))
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data['volume']['percent']
    except Exception:
        return None


def set(player_id: str, percent: int) -> None:
    """Writes a player's volume percent to the cache and notifies observers."""
    with _WRITE_LOCK:
        if get(player_id) == percent:
            return
        file_path = os.path.join(PATH, path.to_filename(player_id))
        doc = json.dumps({'volume': {'player_id': player_id, 'percent': percent}}, indent=2)
        io.write_text(file_path, doc)
    _notify_observers()


def get_all() -> dict[str, int]:
    """Returns ``{player_id: percent}`` for every cached volume file."""
    result: dict[str, int] = {}
    pattern = os.path.join(PATH, '*.json')
    for file_path in glob.glob(pattern):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            vol = data['volume']
            result[vol['player_id']] = vol['percent']
        except Exception:
            continue
    return result
