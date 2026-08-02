"""Preset DSP configuration-layer"""

import glob
import json
import os
from typing import Union

from audera import io
from audera.dal import path
from audera.models import dsp

PATH: Union[str, os.PathLike] = os.path.join(path.HOME, 'dsp', 'presets')


def get_all_presets() -> list[dsp.Preset]:
    """Returns every saved preset, name-sorted (case-insensitive) for a stable menu.

    Returns `[]` when the namespace directory is missing. Malformed preset files are
    skipped-and-continued so a single bad file can't hide the rest.
    """
    if not os.path.isdir(PATH):
        return []
    presets: list[dsp.Preset] = []
    for file_path in glob.glob(os.path.join(PATH, '*.json')):
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            presets.append(dsp.Preset.model_validate(data['preset']))
        except Exception:
            continue
    return sorted(presets, key=lambda preset: preset.name.lower())


def save_preset(preset: dsp.Preset) -> dsp.Preset:
    """Saves the preset to `~/.audera/dsp/presets/{id}.json` and returns it.

    Parameters
    ----------
    preset: `audera.models.dsp.Preset`
        An instance of an `audera.models.dsp.Preset` object.
    """
    file_path = os.path.join(PATH, path.to_filename(preset.id))
    io.write_text(file_path, json.dumps({'preset': preset.model_dump()}, indent=2))
    return preset


def delete_preset(id: str) -> None:
    """Deletes the preset file if it exists.

    A preset has no inbound FK, so deleting one can never orphan a player config.

    Parameters
    ----------
    id: `str`
        The preset identifier.
    """
    file_path = os.path.join(PATH, path.to_filename(id))
    if os.path.isfile(file_path):
        os.remove(file_path)
