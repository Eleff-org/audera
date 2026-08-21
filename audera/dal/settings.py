"""Settings configuration-layer"""

import json
import logging
import os
from typing import Callable, Union

from audera import io
from audera.dal import path
from audera.errors import StorageError
from audera.models import settings

logger = logging.getLogger(__name__)

PATH: Union[str, os.PathLike] = path.HOME
FILE_NAME: str = 'settings.json'

_observers: list[Callable[[], None]] = []


def on_change(callback: Callable[[], None]) -> None:
    """Registers a callback invoked after a settings save."""
    _observers.append(callback)


def _notify_observers() -> None:
    for cb in _observers:
        try:
            cb()
        except Exception:
            logger.exception('settings observer failed')


def exists() -> bool:
    """Returns `True` when the settings configuration file exists."""
    return os.path.isfile(os.path.abspath(os.path.join(PATH, FILE_NAME)))


def create(settings_: settings.Settings) -> settings.Settings:
    """Creates the settings configuration file and returns the `Settings` object.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    return save(settings_)


def get() -> settings.Settings:
    """Returns the settings configuration as a `Settings` object.

    Raises
    ------
    `audera.errors.StorageError`
        When the settings file cannot be read or holds invalid JSON.
    """
    file_path = os.path.join(PATH, FILE_NAME)
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise StorageError('Unable to read settings [%s]: %s' % (file_path, exc)) from exc
    return settings.Settings.from_dict(data['settings'])


def get_or_create(settings_: settings.Settings) -> settings.Settings:
    """Creates or reads the settings configuration file and returns the `Settings` object.

    A present-but-corrupt file is not overwritten: the seed is returned and the corruption logged.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    if exists():
        try:
            return get()
        except StorageError:
            logger.exception('settings file is unreadable; returning seed without rewriting')
            return settings_
    else:
        return create(settings_)


def save(settings_: settings.Settings) -> settings.Settings:
    """Saves the settings configuration to `~/.audera/settings.json`.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    io.write_text(os.path.join(PATH, FILE_NAME), json.dumps({'settings': settings_.to_dict()}, indent=2))
    _notify_observers()
    return settings_


def update(new: settings.Settings) -> settings.Settings:
    """Updates the settings configuration file `~/.audera/settings.json`.

    Parameters
    ----------
    new: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    existing = get_or_create(new)
    if not existing == new:
        return save(new)
    else:
        return existing


def delete():
    """Deletes the settings configuration file."""
    if exists():
        os.remove(os.path.join(PATH, FILE_NAME))
