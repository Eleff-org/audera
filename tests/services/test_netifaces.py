"""Tests for the network-interface connectivity gate's bounded retry and the checked tool wrappers."""

import subprocess

import pytest

from audera.errors import ServiceError, Unreachable
from audera.services import netifaces, platform


def test_connected_with_retry_returns_true_after_a_transient_miss(monkeypatch):
    """A transient failure on the first checks recovers on a later attempt."""
    results = iter([False, False, True])
    calls = []
    sleeps = []
    monkeypatch.setattr(netifaces, 'connected', lambda interface='wlan0': calls.append(interface) or next(results))
    monkeypatch.setattr(netifaces.time, 'sleep', lambda seconds: sleeps.append(seconds))

    assert netifaces.connected_with_retry() is True
    assert len(calls) == 3
    assert sleeps == [2.0, 2.0]


def test_connected_with_retry_gives_up_when_offline(monkeypatch):
    """An offline device exhausts its attempts and returns `False`, sleeping between each."""
    calls = []
    sleeps = []
    monkeypatch.setattr(netifaces, 'connected', lambda interface='wlan0': calls.append(interface) or False)
    monkeypatch.setattr(netifaces.time, 'sleep', lambda seconds: sleeps.append(seconds))

    assert netifaces.connected_with_retry() is False
    assert len(calls) == 3
    assert sleeps == [2.0, 2.0]


def test_connected_with_retry_returns_immediately_when_connected(monkeypatch):
    """A connected device returns on the first attempt."""
    calls = []
    sleeps = []
    monkeypatch.setattr(netifaces, 'connected', lambda interface='wlan0': calls.append(interface) or True)
    monkeypatch.setattr(netifaces.time, 'sleep', lambda seconds: sleeps.append(seconds))

    assert netifaces.connected_with_retry() is True
    assert len(calls) == 1
    assert sleeps == []


# Maps each checked tool wrapper to the argv it runs.
_WRAPPERS = {
    'connection_up': (('audera',), ['nmcli', 'connection', 'up', 'audera']),
    'connection_down': (('audera',), ['nmcli', 'connection', 'down', 'audera']),
    'connection_delete': (('audera',), ['nmcli', 'connection', 'delete', 'audera']),
    'connection_add': (('type', 'wifi'), ['nmcli', 'connection', 'add', 'type', 'wifi']),
    'add_ap_interface': (('wlan0', 'ap0'), ['iw', 'dev', 'wlan0', 'interface', 'add', 'ap0', 'type', '__ap']),
    'set_link_up': (('ap0',), ['ip', 'link', 'set', 'ap0', 'up']),
}


@pytest.mark.parametrize('name, args, argv', [(n, a, v) for n, (a, v) in _WRAPPERS.items()])
def test_checked_wrapper_runs_the_expected_argv(monkeypatch, name, args, argv):
    """Each wrapper runs the command it names, checked so a failure can be translated."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    calls = []
    monkeypatch.setattr(netifaces.subprocess, 'run', lambda a, **k: calls.append((a, k)) or subprocess.CompletedProcess(a, 0))

    getattr(netifaces, name)(*args)

    assert calls[0][0] == argv
    assert calls[0][1]['check'] is True


@pytest.mark.parametrize('name, args', [(n, a) for n, (a, _) in _WRAPPERS.items()])
def test_checked_wrapper_translates_a_non_zero_exit_to_service_error(monkeypatch, name, args):
    """A non-zero exit becomes a typed `ServiceError`."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')

    def run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv, stderr='nope')

    monkeypatch.setattr(netifaces.subprocess, 'run', run)

    with pytest.raises(ServiceError):
        getattr(netifaces, name)(*args)


@pytest.mark.parametrize('name, args', [(n, a) for n, (a, _) in _WRAPPERS.items()])
def test_checked_wrapper_translates_a_missing_binary_to_unreachable(monkeypatch, name, args):
    """A missing binary becomes `Unreachable`."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')

    def run(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(netifaces.subprocess, 'run', run)

    with pytest.raises(Unreachable):
        getattr(netifaces, name)(*args)


def test_delete_interface_is_best_effort(monkeypatch):
    """`delete_interface` does not raise when the interface is missing."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    calls = []
    monkeypatch.setattr(netifaces.subprocess, 'run', lambda a, **k: calls.append((a, k)) or subprocess.CompletedProcess(a, 1))

    netifaces.delete_interface('ap0')  # does not raise on a non-zero exit

    assert calls[0][0] == ['iw', 'dev', 'ap0', 'del']
    assert 'check' not in calls[0][1]
