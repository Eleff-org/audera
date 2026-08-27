"""Reference-balance configuration-layer

One reference balance under `~/.audera/balance.json`: `save` overwrites it, `get` re-reads it.
"""

import json
import logging
import os
from typing import Callable, Union

from audera import io
from audera.dal import path
from audera.errors import StorageError
from audera.models import balance

logger = logging.getLogger(__name__)

PATH: Union[str, os.PathLike] = path.HOME
FILE_NAME: str = 'balance.json'

_observers: list[Callable[[], None]] = []


def on_change(callback: Callable[[], None]) -> None:
    """Registers a callback invoked after a reference-balance save."""
    _observers.append(callback)


def _notify_observers() -> None:
    for cb in _observers:
        try:
            cb()
        except Exception:
            logger.exception('balance observer failed')


def exists() -> bool:
    """Returns `True` when the reference-balance file exists."""
    return os.path.isfile(os.path.abspath(os.path.join(PATH, FILE_NAME)))


def get() -> balance.ReferenceBalance:
    """Returns the saved reference balance as a `ReferenceBalance` object.

    Raises
    ------
    `audera.errors.StorageError`
        When the reference-balance file cannot be read or holds invalid JSON.
    """
    file_path = os.path.join(PATH, FILE_NAME)
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise StorageError('Unable to read reference balance [%s]: %s' % (file_path, exc)) from exc
    return balance.ReferenceBalance.model_validate(data['balance'])


def save(ref: balance.ReferenceBalance) -> balance.ReferenceBalance:
    """Saves the reference balance to `~/.audera/balance.json`.

    Parameters
    ----------
    ref: `audera.models.balance.ReferenceBalance`
        An instance of a `ReferenceBalance` object.
    """
    io.write_text(os.path.join(PATH, FILE_NAME), json.dumps({'balance': ref.model_dump()}, indent=2))
    _notify_observers()
    return ref
