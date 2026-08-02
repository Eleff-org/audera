"""The single safe writer every configuration file goes through."""

import os
import stat

import pytest

from audera import io


def test_write_text_creates_the_parent_directory(tmp_path):
    # The DALs write into `~/.audera/dsp/presets/`, which does not exist on a device whose
    # operator has not saved one yet, so the writer creates what it is pointed at.
    path = tmp_path / 'nested' / 'deeper' / 'file.json'
    io.write_text(path, '{}')
    assert path.read_text(encoding='utf-8') == '{}'


def test_write_text_replaces_an_existing_file(tmp_path):
    path = tmp_path / 'file.conf'
    path.write_text('old', encoding='utf-8')
    io.write_text(path, 'new')
    assert path.read_text(encoding='utf-8') == 'new'


def test_write_text_leaves_the_destination_intact_when_the_write_fails(tmp_path, monkeypatch):
    """A failed write leaves the previous file, rather than a truncated one.

    This is the whole reason the module exists: opening the destination `'w'` empties it before the
    first byte of the new content lands, so a raise anywhere after that leaves a zero-byte file
    permanently. A zero-byte `/etc/snapserver.conf` is a Snapserver that will not start.
    """
    path = tmp_path / 'snapserver.conf'
    path.write_text('[stream]\nsource = airplay:///\n', encoding='utf-8')

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(io.os, 'replace', _boom)
    with pytest.raises(OSError):
        io.write_text(path, 'truncated')

    assert path.read_text(encoding='utf-8') == '[stream]\nsource = airplay:///\n'


def test_write_text_leaves_no_temporary_file_behind(tmp_path, monkeypatch):
    # One file per failure would otherwise accumulate beside every configuration file, and the
    # next reader globbing the directory would find them.
    path = tmp_path / 'file.json'

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(io.os, 'replace', _boom)
    with pytest.raises(OSError):
        io.write_text(path, '{}')

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == 'nt', reason='Windows chmod carries only the read-only bit')
def test_write_text_mode_lands_on_the_destination(tmp_path):
    """The permission bits reach the file the reader opens, not just the temporary one.

    `os.replace` carries the source's mode onto the destination, so the `chmod` has to happen
    before it. The PlexAmp claim drop-in is written `0o600` because it carries a plex.tv token,
    and a token that is world-readable until a later `chmod` narrows it was still world-readable.
    """
    path = tmp_path / 'override.conf'
    io.write_text(path, '[Service]\n', mode=0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
