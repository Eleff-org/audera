"""Safe file writing

Every configuration file Audera writes — `~/.audera/*.json`, `/etc/snapserver.conf`, the PlexAmp
claim drop-in, the access point's dnsmasq conf — goes through `write_text()`.

Opening a destination `'w'` truncates it before a single byte of the new content is written, so
the destination is empty for the length of the write. Two things go wrong in that window. A
concurrent reader gets a zero-byte file: the Sources tab's choreographies write `sources.json`
through `asyncio.to_thread` while the Players tab reads the enabled set on every render,
including the 10 s poll's, and a `JSONDecodeError` there fails the whole tab. And a raise from
whatever produces the content leaves the truncation permanent: a zero-byte `/etc/snapserver.conf`
is a Snapserver that will not start.

`write_text()` closes both. It takes rendered content, so a caller cannot truncate a destination
and only then discover that its content does not exist; and it writes a sibling temporary file
and `os.replace`s it into place, which is atomic on both POSIX and Windows, so a reader sees
either the old file or the new one and a failure leaves the old one.
"""

import os
from typing import Union


def write_text(path: Union[str, os.PathLike], content: str, *, encoding: str = 'utf-8', mode: Union[int, None] = None) -> None:
    """Writes `content` to `path`, atomically, creating the parent directory as needed.

    The temporary file is a sibling of the destination, since `os.replace` is only atomic within
    a filesystem, and carries the process id, since two processes writing the same destination
    would otherwise share one temporary name and each unlink the other's. It is `chmod`ed before
    the replace rather than after, because `os.replace` carries the source's mode onto the
    destination, and because a token written world-readable and narrowed a moment later was still
    world-readable for that moment.

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
    temp_path = f'{path}.{os.getpid()}.tmp'
    try:
        with open(temp_path, 'w', encoding=encoding) as f:
            f.write(content)
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        # `os.replace` consumed the temporary file on the success path, so this only runs when
        # the write, the `chmod`, or the replace itself raised. Leaving the litter behind would
        # accumulate one file per failure beside every configuration file.
        if os.path.exists(temp_path):
            os.remove(temp_path)
