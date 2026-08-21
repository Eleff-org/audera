"""DSP configuration-layer"""

import json
import logging
import os
from typing import Union

from audera import io
from audera.dal import path
from audera.errors import StorageError
from audera.models import dsp

logger = logging.getLogger(__name__)

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'dsp')


def exists(player_id: str) -> bool:
    """Returns `True` when the DSP configuration file exists.

    Parameters
    ----------
    player_id: `str`
        The player identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, path.to_filename(player_id))))


def create(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Creates the DSP configuration file and returns the `DSPConfig` object.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    return save(dsp_config)


def get(player_id: str) -> dsp.DSPConfig:
    """Returns the DSP configuration as an `audera.models.dsp.DSPConfig` object.

    Parameters
    ----------
    player_id: `str`
        The player identifier.

    Raises
    ------
    `audera.errors.StorageError`
        When the DSP file cannot be read or holds invalid JSON.
    """
    file_path = os.path.join(PATH, path.to_filename(player_id))
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise StorageError('Unable to read DSP configuration [%s]: %s' % (file_path, exc)) from exc
    return dsp.DSPConfig.from_dict(data['dsp'])


def get_or_create(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Creates or reads the DSP configuration file and returns the `DSPConfig` object.

    A present-but-corrupt file is not overwritten: the seed is returned and the corruption logged.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    if exists(dsp_config.player_id):
        try:
            return get(dsp_config.player_id)
        except StorageError:
            logger.exception('DSP file is unreadable; returning seed without rewriting')
            return dsp_config
    else:
        return create(dsp_config)


def save(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Saves the DSP configuration to `~/.audera/dsp/{player_id}.json`.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    file_path = os.path.join(PATH, path.to_filename(dsp_config.player_id))
    io.write_text(file_path, json.dumps({'dsp': dsp_config.to_dict()}, indent=2))
    return dsp_config


def update(new: dsp.DSPConfig) -> dsp.DSPConfig:
    """Updates the DSP configuration file `~/.audera/dsp/{player_id}.json`.

    Parameters
    ----------
    new: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    existing = get_or_create(new)
    if not existing == new:
        return save(new)
    else:
        return existing


def delete(player_id: str):
    """Deletes the DSP configuration file for a player.

    Parameters
    ----------
    player_id: `str`
        The player identifier.
    """
    if exists(player_id):
        os.remove(os.path.join(PATH, path.to_filename(player_id)))
