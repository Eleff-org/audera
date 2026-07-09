"""Named user-preset configuration-layer.

Presets live in their own namespace nested under `dsp/` (`~/.audera/dsp/presets/`),
glob-listed and wrapped `{'preset': {...}}`, so a corrupt player config can't break
the preset menu and vice-versa. Uses plain `json` + `glob` (consistent with `dsp`'s
plain-json storage; the bands dict is out of `read_json_auto` by design).
"""

import glob
import json
import os
from typing import Union

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
    os.makedirs(PATH, exist_ok=True)
    file_path = os.path.join(PATH, '.'.join([preset.id, 'json']))
    with open(file_path, 'w') as f:
        json.dump({'preset': preset.model_dump()}, f, indent=2)
    return preset


def delete_preset(id: str) -> None:
    """Deletes the preset file if it exists.

    A preset has no inbound FK, so deleting one can never orphan a player config.

    Parameters
    ----------
    id: `str`
        The preset identifier.
    """
    file_path = os.path.join(PATH, '.'.join([id, 'json']))
    if os.path.isfile(file_path):
        os.remove(file_path)
