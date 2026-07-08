"""DSP configuration-layer"""

import json
import os
import uuid
from typing import Union

from audera.dal import path, players
from audera.models import dsp, player

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'dsp')


def exists(id: str) -> bool:
    """Returns `True` when the DSP configuration file exists.

    Parameters
    ----------
    id: `str`
        The DSP configuration identifier.
    """
    return os.path.isfile(os.path.abspath(os.path.join(PATH, '.'.join([id, 'json']))))


def create(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Creates the DSP configuration file and returns the `DSPConfig` object.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    return save(dsp_config)


def get(id: str) -> dsp.DSPConfig:
    """Returns the DSP configuration as an `audera.models.dsp.DSPConfig` object.

    Parameters
    ----------
    id: `str`
        The DSP configuration identifier.
    """
    file_path = os.path.join(PATH, '.'.join([id, 'json']))
    with open(file_path, 'r') as f:
        data = json.load(f)
    return dsp.DSPConfig.from_dict(data['dsp'])


def get_or_create(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Creates or reads the DSP configuration file and returns the `DSPConfig` object.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    if exists(dsp_config.id):
        return get(dsp_config.id)
    else:
        return create(dsp_config)


def resolve_for_player(player_: player.Player) -> dsp.DSPConfig:
    """Returns the player's editable `DSPConfig`, minting and linking one if unassigned.

    If `player_.dsp_id` is set, the referenced config is returned. Otherwise a fresh,
    empty `DSPConfig` is minted, saved, and linked to the player (via `players.update`
    persisting the `dsp_id`). This is a one-time create-and-link — it reads no legacy
    file.

    Parameters
    ----------
    player_: `audera.models.player.Player`
        An instance of an `audera.models.player.Player` object.
    """
    if player_.dsp_id:
        return get(player_.dsp_id)
    dsp_config = save(dsp.DSPConfig(id=uuid.uuid4().hex))
    players.update(player_.model_copy(update={'dsp_id': dsp_config.id}))
    return dsp_config


def save(dsp_config: dsp.DSPConfig) -> dsp.DSPConfig:
    """Saves the DSP configuration to `~/.audera/dsp/{id}.json`.

    Parameters
    ----------
    dsp_config: `audera.models.dsp.DSPConfig`
        An instance of an `audera.models.dsp.DSPConfig` object.
    """
    if not os.path.isdir(PATH):
        os.makedirs(PATH)
    file_path = os.path.join(PATH, '.'.join([dsp_config.id, 'json']))
    with open(file_path, 'w') as f:
        json.dump({'dsp': dsp_config.to_dict()}, f, indent=2)
    return dsp_config


def update(new: dsp.DSPConfig) -> dsp.DSPConfig:
    """Updates the DSP configuration file `~/.audera/dsp/{id}.json`.

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


def delete(id: str):
    """Deletes the DSP configuration file.

    Parameters
    ----------
    id: `str`
        The DSP configuration identifier.
    """
    if exists(id):
        os.remove(os.path.join(PATH, '.'.join([id, 'json'])))
