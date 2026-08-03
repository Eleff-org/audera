"""Tests for `audera.io`, the writer every configuration file goes through."""

import os
import stat

import pytest

from audera import io


def test_write_text_creates_the_parent_directory(tmp_path):
    # The DALs write into `~/.audera/dsp/presets/`, which does not exist until a preset is saved.
    path = tmp_path / 'nested' / 'deeper' / 'file.json'
    io.write_text(path, '{}')
    assert path.read_text(encoding='utf-8') == '{}'


def test_write_text_replaces_an_existing_file(tmp_path):
    path = tmp_path / 'file.conf'
    path.write_text('old', encoding='utf-8')
    io.write_text(path, 'new')
    assert path.read_text(encoding='utf-8') == 'new'


def test_write_text_leaves_the_destination_intact_when_the_write_fails(tmp_path, monkeypatch):
    """A failed write leaves the previous file, not a truncated one.

    Opening the destination `'w'` would empty it before any new content lands, and a zero-byte
    `/etc/snapserver.conf` is a Snapserver that will not start.
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
    # Otherwise one temp file per failure accumulates beside every configuration file.
    path = tmp_path / 'file.json'

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(io.os, 'replace', _boom)
    with pytest.raises(OSError):
        io.write_text(path, '{}')

    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(os.name == 'nt', reason='Windows chmod carries only the read-only bit')
def test_write_text_mode_lands_on_the_destination(tmp_path):
    """`mode` applies to the destination file.

    `os.replace` carries the temp file's mode onto the destination, so the `chmod` has to happen
    before it. The PlexAmp claim drop-in is written `0o600` because it carries a plex.tv token.
    """
    path = tmp_path / 'override.conf'
    io.write_text(path, '[Service]\n', mode=0o600)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
