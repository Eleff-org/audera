"""Settings configuration-layer"""

import json
import os
from typing import Union

from audera import io
from audera.dal import path
from audera.models import settings

PATH: Union[str, os.PathLike] = path.HOME
FILE_NAME: str = 'settings.json'


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
    """Returns the settings configuration as a `Settings` object."""
    file_path = os.path.join(PATH, FILE_NAME)
    with open(file_path, 'r') as f:
        data = json.load(f)
    return settings.Settings.from_dict(data['settings'])


def get_or_create(settings_: settings.Settings) -> settings.Settings:
    """Creates or reads the settings configuration file and returns the `Settings` object.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    if exists():
        return get()
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
