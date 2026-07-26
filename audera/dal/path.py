"""Data-access directory management"""

import os
import re

HOME = os.path.abspath(os.path.join(os.path.expanduser('~'), '.audera'))

# Characters that are illegal in a Windows filename (`< > : " / \ | ? *` and the ASCII
# control codes). A Snapcast player id is a MAC address, so its colons would otherwise
# make `dsp/{player_id}.json` an invalid path on Windows and raise OSError 22 on open.
# POSIX only forbids `/`, but the same set is sanitized on every platform so a given id
# always resolves to the same filename regardless of where the streamer runs.
_RESERVED_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def to_filename(stem: str, extension: str = 'json') -> str:
    """Returns a cross-platform-safe `{stem}.{extension}` filename for a config key.

    Reserved characters in `stem` — notably the colons in a MAC-address player id — are
    replaced with `-` so the name is valid on Windows as well as POSIX.

    Parameters
    ----------
    stem: `str`
        The file stem (e.g. a player id or preset id).
    extension: `str`
        The file extension, without a leading dot.
    """
    return '.'.join([_RESERVED_CHARS.sub('-', stem), extension])
