"""Audio sources configuration-layer

`~/.audera/sources.json` holds `{'sources': {'enabled': [...], 'setup': {id: {...}}}}`.

`enabled` is which audio sources the operator wants running. Snapcast does not persist this. A
source absent from the list is disabled, so adding a catalog entry needs no migration.

`setup` is the durable record of a source's one-time setup, today only `{'complete': true}` for a
claimed PlexAmp. The live probes report what the device does now, so a stopped unit reads as
unclaimed and provisioning would otherwise re-ask for a claim that already happened. The record
is discarded when the source is disabled.

An absent `enabled` key means nothing has been recorded yet, and `get_enabled()` falls back to
`DEFAULT_ENABLED`. `is_recorded()` and `adopt()` exist for the one caller that must tell those
two apart, `ui.streamer.pages.index.adopt_running_sources`. They test the key rather than the
file, since a setup record can create the file before any enabled set is recorded.
"""

import json
import logging
import os
import threading
from typing import Callable, Union

from audera import io
from audera.dal import path

logger = logging.getLogger(__name__)

PATH: Union[str, os.PathLike] = path.HOME
FILE_NAME: str = 'sources.json'

# The bootstrap set, restated here rather than imported from `domains.sources.CATALOG` so the
# DAL keeps its standard-library-plus-`dal.path` imports. `tests/dal/test_sources.py` asserts
# every id here is catalogued and renders cleanly.
#
# AirPlay is the only source that plays with no account, claim flow, or app-side pairing.
# Provisioning renders the conf and the systemd unit state from `get_enabled()`, so this is what
# a device with no recorded set gets; it never overwrites a recording.
DEFAULT_ENABLED: tuple[str, ...] = ('AirPlay',)

_WRITE_LOCK = threading.Lock()
_observers: list[Callable[[], None]] = []


def on_change(callback: Callable[[], None]) -> None:
    """Registers a callback invoked after any write to the sources document.

    Fires for enabled-set changes and setup-record writes so every connected browser can refresh
    the Sources tab (Plex claim completion is a setup write, not an enabled-set write).
    """
    _observers.append(callback)


def _notify_observers() -> None:
    for cb in _observers:
        try:
            cb()
        except Exception:
            logger.exception('sources observer failed')


def is_recorded() -> bool:
    """Returns whether an enabled set has been written to disk.

    `get_enabled()` cannot answer this, since it degrades an unrecorded set to `DEFAULT_ENABLED`,
    which is indistinguishable from a recorded set naming only AirPlay.
    """
    return 'enabled' in _document().get('sources', {})


def get_enabled() -> list[str]:
    """Returns the enabled source ids, or `DEFAULT_ENABLED` when none have been recorded."""
    enabled = _document().get('sources', {}).get('enabled')
    return list(DEFAULT_ENABLED) if enabled is None else enabled


def adopt(ids: list[str]) -> bool:
    """Records `ids` as the enabled set only when nothing has been recorded yet, and returns
    whether the write happened.

    Refuses an already-recorded set, which is the operator's own intent, and an empty `ids`, which
    indicates a failed observation and would break the "at least one source stays enabled"
    invariant.

    Parameters
    ----------
    ids: `list[str]`
        The source ids observed running, in catalog order.
    """
    with _WRITE_LOCK:
        if not ids or is_recorded():
            return False
        _save(ids)
    _notify_observers()
    return True


def set_enabled(id: str, enabled: bool) -> list[str]:
    """Enables or disables a source and returns the new set of enabled source ids.

    The new set is returned so callers render from the value just written rather than reading the
    configuration file back.

    Parameters
    ----------
    id: `str`
        The source id to toggle.
    enabled: `bool`
        Whether the source is enabled.
    """
    with _WRITE_LOCK:
        ids = get_enabled()
        if enabled and id not in ids:
            ids.append(id)
        elif not enabled and id in ids:
            ids.remove(id)
        else:
            return ids
        result = _save(ids)
    _notify_observers()
    return result


def get_setup(id: str) -> dict:
    """Returns the recorded setup state of a source, or `{}` when nothing has been recorded.

    Parameters
    ----------
    id: `str`
        The source id.
    """
    return _document().get('sources', {}).get('setup', {}).get(id, {})


def set_setup_complete(id: str, complete: bool) -> None:
    """Records whether a source's one-time setup has been completed.

    Parameters
    ----------
    id: `str`
        The source id.
    complete: `bool`
        Whether setup is complete.
    """
    with _WRITE_LOCK:
        data = _document()
        setup = data.setdefault('sources', {}).setdefault('setup', {})
        setup[id] = {**setup.get(id, {}), 'complete': complete}
        _save_document(data)
    _notify_observers()


def clear_setup(id: str) -> None:
    """Discards a source's recorded setup state.

    Called when a source is disabled, since whatever was set up may not survive to the next
    enable.

    Parameters
    ----------
    id: `str`
        The source id.
    """
    with _WRITE_LOCK:
        data = _document()
        setup = data.get('sources', {}).get('setup', {})
        if id not in setup:
            return
        del setup[id]
        _save_document(data)
    _notify_observers()


def _document() -> dict:
    """Returns the whole configuration document, or an empty one when the file is absent or corrupt.

    A corrupt file degrades to an empty document rather than raising, like the absent-file path.
    """
    file_path = os.path.abspath(os.path.join(PATH, FILE_NAME))
    if not os.path.isfile(file_path):
        return {'sources': {}}
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (OSError, ValueError):
        logger.exception('sources file is unreadable; degrading to an empty document')
        return {'sources': {}}


def _save(ids: list[str]) -> list[str]:
    """Saves the enabled source ids to `~/.audera/sources.json` and returns them.

    Parameters
    ----------
    ids: `list[str]`
        The enabled source ids.
    """
    data = _document()
    data.setdefault('sources', {})['enabled'] = ids
    _save_document(data)
    return ids


def _save_document(data: dict) -> None:
    """Writes the whole configuration document to `~/.audera/sources.json`.

    Every writer reads the document first and re-writes all of it, so an enabled-set write and a
    setup write cannot clobber each other's section.

    Parameters
    ----------
    data: `dict`
        The whole configuration document.
    """
    io.write_text(os.path.join(PATH, FILE_NAME), json.dumps(data, indent=2))
