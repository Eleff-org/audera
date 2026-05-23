"""Tests for audera.cli.commands dispatch logic"""

from unittest.mock import MagicMock, patch

from audera.cli import commands


def test_streamer_conf_writes_to_stdout(capsys):
    mock_ref = MagicMock()
    mock_ref.read_text.return_value = 'streamer-config-content'

    with patch('importlib.resources.files') as mock_files:
        mock_files.return_value.joinpath.return_value.joinpath.return_value.joinpath.return_value = mock_ref
        commands.streamer_conf(filename='snapserver.conf')

    captured = capsys.readouterr()
    assert captured.out == 'streamer-config-content'


def test_player_conf_writes_to_stdout(capsys):
    mock_ref = MagicMock()
    mock_ref.read_text.return_value = 'player-config-content'

    with patch('importlib.resources.files') as mock_files:
        mock_files.return_value.joinpath.return_value.joinpath.return_value.joinpath.return_value = mock_ref
        commands.player_conf(filename='snapclient.conf')

    captured = capsys.readouterr()
    assert captured.out == 'player-config-content'


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
