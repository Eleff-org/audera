"""Settings configuration-layer"""

import os
from typing import Union

from pytensils import config

from audera.dal import path
from audera.models import settings

PATH: Union[str, os.PathLike] = path.HOME
FILE_NAME: str = 'settings.json'
DTYPES: dict = {
    'settings': {
        'plexamp_host': 'str',
        'snapserver_host': 'str',
    }
}


def exists() -> bool:
    """Returns `True` when the settings configuration file exists."""
    if os.path.isfile(os.path.abspath(os.path.join(PATH, FILE_NAME))):
        return True
    else:
        return False


def create(settings_: settings.Settings) -> config.Handler:
    """Creates the settings configuration file and returns the contents
    as a `pytensils.config.Handler` object.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    if not os.path.isdir(PATH):
        os.mkdir(PATH)

    config_ = config.Handler(path=PATH, file_name=FILE_NAME, create=True)
    config_ = config_.from_dict({'settings': settings_.to_dict()})
    return config_


def get() -> config.Handler:
    """Returns the contents of the settings configuration as a
    `pytensils.config.Handler` object.
    """
    config_ = config.Handler(path=PATH, file_name=FILE_NAME)
    config_.validate(DTYPES)
    return config_


def get_or_create(settings_: settings.Settings) -> config.Handler:
    """Creates or reads the settings configuration file and returns the contents as
    a `pytensils.config.Handler` object.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    if exists():
        return get()
    else:
        return create(settings_)


def save(settings_: settings.Settings) -> config.Handler:
    """Saves the settings configuration to `~/.audera/settings.json`.

    Parameters
    ----------
    settings_: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    if not os.path.isdir(PATH):
        os.mkdir(PATH)

    config_ = config.Handler(path=PATH, file_name=FILE_NAME, create=True)
    config_ = config_.from_dict({'settings': settings_.to_dict()})
    return config_


def update(new: settings.Settings) -> settings.Settings:
    """Updates the settings configuration file `~/.audera/settings.json`.

    Parameters
    ----------
    new: `audera.models.settings.Settings`
        An instance of a `Settings` object.
    """
    config_ = get_or_create(new)
    settings_: settings.Settings = settings.Settings.from_config(config=config_)

    if not settings_ == new:
        config_ = config_.from_dict({'settings': new.to_dict()})
        return settings.Settings.from_config(config=config_)
    else:
        return settings_


def delete():
    """Deletes the settings configuration file."""
    if exists():
        os.remove(os.path.join(PATH, FILE_NAME))


def get_settings() -> settings.Settings:
    """Returns the streamer settings as a `Settings` object."""
    return settings.Settings.from_config(get())
