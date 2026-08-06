"""Safe file writing

Every configuration file Audera writes — `~/.audera/*.json`, `/etc/snapserver.conf`, the PlexAmp
claim drop-in, the access point's dnsmasq conf — goes through `write_text()`.

Opening a destination `'w'` truncates it before any of the new content is written, leaving a
concurrent reader a zero-byte file and making a raise from whatever produces the content
permanent. `write_text()` takes rendered content, so a caller cannot truncate a destination and
only then discover its content does not exist, and it writes a sibling temporary file that it
`os.replace`s into place, which is atomic on both POSIX and Windows, so a reader sees either the
old file or the new one and a failure leaves the old one.
"""

import os
import threading
from typing import Union


def write_text(path: Union[str, os.PathLike], content: str, *, encoding: str = 'utf-8', mode: Union[int, None] = None) -> None:
    """Writes `content` to `path`, atomically, creating the parent directory as needed.

    The temporary file is a sibling of the destination, since `os.replace` is only atomic within a
    filesystem, and carries the process id and thread id, so two processes or two threads writing
    the same destination do not share one temporary name. It is `chmod`ed before the replace, since `os.replace` carries the
    source's mode onto the destination and narrowing afterwards leaves a window in which the
    content is world-readable.

    Parameters
    ----------
    path: `Union[str, os.PathLike]`
        The destination path.
    content: `str`
        The fully rendered file content.
    encoding: `str`
        The text encoding.
    mode: `Union[int, None]`
        The permission bits to set on the destination, or `None` to leave the platform default.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        with open(temp_path, 'w', encoding=encoding) as f:
            f.write(content)
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        # `os.replace` consumed the temporary file on the success path, so this only runs after a
        # failure, where it keeps one file per failure from accumulating beside the destination.
        if os.path.exists(temp_path):
            os.remove(temp_path)
