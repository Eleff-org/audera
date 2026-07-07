"""Tests for audera.cli.commands dispatch logic"""

from unittest.mock import MagicMock, patch

import pytest

from audera.cli import commands, conf


def test_streamer_conf_writes_rendered_snapserver(capsys):
    commands.streamer_conf(filename='snapserver.conf')
    assert capsys.readouterr().out == conf.render_snapserver()


def test_player_conf_writes_rendered_camilladsp(capsys):
    commands.player_conf(filename='camilladsp.yml')
    assert capsys.readouterr().out == conf.render_camilladsp()


def test_conf_unknown_filename_raises(capsys):
    with pytest.raises(SystemExit):
        commands.streamer_conf(filename='does-not-exist.conf')


@pytest.mark.parametrize('emit', [commands.streamer_conf, commands.player_conf])
def test_conf_camilladsp_default_format_is_s32le(emit, capsys):
    emit(filename='camilladsp.yml')
    out = capsys.readouterr().out
    # Default leaves both capture and playback at S32LE.
    assert out.count('format: S32LE') == 2
    assert 'format: S16LE' not in out


@pytest.mark.parametrize('emit', [commands.streamer_conf, commands.player_conf])
def test_conf_camilladsp_s16le_only_changes_playback(emit, capsys):
    emit(filename='camilladsp.yml', playback_format='S16LE')
    out = capsys.readouterr().out
    # Playback becomes S16LE; capture stays S32LE to match Snapclient's loopback.
    assert '    format: S16LE\n' in out
    assert out.count('format: S16LE') == 1
    assert out.count('format: S32LE') == 1
    # Comments are preserved end-to-end (scope + render fidelity).
    assert 'HDMI STABILITY' in out


def test_streamer_start_calls_app_run():
    mock_netifaces = MagicMock()
    mock_netifaces.connected.return_value = True

    with (
        patch('audera.ui.streamer.run') as mock_run,
        patch('audera.cli.commands.netifaces', mock_netifaces),
    ):
        commands.streamer_start()

    mock_run.assert_called_once()


def test_streamer_start_runs_setup_when_disconnected():
    mock_netifaces = MagicMock()
    mock_netifaces.connected.return_value = False

    with (
        patch('audera.ui.setup.run') as mock_setup_run,
        patch('audera.ui.streamer.run') as mock_streamer_run,
        patch('audera.cli.commands.netifaces', mock_netifaces),
    ):
        commands.streamer_start()

    mock_setup_run.assert_called_once_with(role='streamer')
    mock_streamer_run.assert_called_once()


def test_player_start_runs_setup_when_disconnected():
    mock_netifaces = MagicMock()
    mock_netifaces.connected.return_value = False

    with (
        patch('audera.ui.setup.run') as mock_setup_run,
        patch('audera.cli.commands.netifaces', mock_netifaces),
    ):
        commands.player_start()

    mock_setup_run.assert_called_once_with(role='player')


def test_player_start_does_nothing_when_connected():
    mock_netifaces = MagicMock()
    mock_netifaces.connected.return_value = True

    with patch('audera.cli.commands.netifaces', mock_netifaces):
        commands.player_start()  # should not raise or import setup
