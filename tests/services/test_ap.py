"""Tests for the setup-mode access point.

The AP-creation path must never leave NetworkManager stopped: an EBUSY `iw` failure would otherwise
strand the device offline. NetworkManager / AP effects on real hardware are verified by flashing a
device (see `os/dietpi/AGENTS.md`); these tests pin ordering and the `finally` restore around a
fully faked seam.

`ap.py` shells out to nothing directly: `nmcli`, `iw`, and `ip` all route through the `netifaces`
seam and `systemctl` through the `system` seam. The seam functions are patched here, so the
recorder sees every call `create()` / `delete()` / `up()` / `down()` make and asserts the ordering.
"""

import pytest

from audera.errors import ServiceError
from audera.services import ap, platform

# Maps each `netifaces` seam call `ap.py` makes to the short label the recorder records.
_NETIFACES_CALLS = {
    'delete_interface': 'iw_del',
    'add_ap_interface': 'iw_add',
    'set_link_up': 'ip_up',
    'connection_add': 'nmcli_add',
    'connection_delete': 'nmcli_delete',
    'connection_up': 'nmcli_up',
    'connection_down': 'nmcli_down',
}


def _patch_netifaces(monkeypatch, events, fail_kind=None):
    """Patches every `netifaces` seam function `ap.py` uses to record its label and optionally fail one."""

    def make(kind):
        def fn(*args, **kwargs):
            events.append(kind)
            if kind == fail_kind:
                raise ServiceError('boom')

        return fn

    for name, kind in _NETIFACES_CALLS.items():
        monkeypatch.setattr(ap.netifaces, name, make(kind))


def _systemctl_recorder(events, fail_on=None):
    """A fake `system.systemctl` recording `(verb, unit)` and optionally rejecting one exact call."""

    def systemctl(*args, **kwargs):
        events.append(('systemctl', *args))
        if fail_on is not None and tuple(args) == tuple(fail_on):
            raise ServiceError('boom')

    return systemctl


@pytest.fixture
def access_point(monkeypatch):
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    return ap.AccessPoint(name='audera', url='http://audera.local', interface='wlan0')


def test_create_always_restarts_network_manager_when_iw_fails(monkeypatch, access_point):
    """An EBUSY `iw ... interface add` failure still runs the `finally` restart.

    NetworkManager was cleanly stopped, so the restart under `finally` is what brings it back after
    an AP-creation failure. The seam translates the failure into a typed `ServiceError`.
    """
    events = []
    monkeypatch.setattr(ap.system, 'systemctl', _systemctl_recorder(events))
    _patch_netifaces(monkeypatch, events, fail_kind='iw_add')
    monkeypatch.setattr(ap.io, 'write_text', lambda *a, **k: events.append('write_text'))
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: None)

    with pytest.raises(ServiceError):
        access_point.create()

    systemctl_events = [event for event in events if event[0] == 'systemctl']
    assert systemctl_events == [
        ('systemctl', 'stop', 'NetworkManager'),
        ('systemctl', 'stop', 'wpa_supplicant'),
        ('systemctl', 'restart', 'NetworkManager'),
    ]
    # `iw` failed first, so the write never happened, but NetworkManager still restarted.
    assert 'write_text' not in events


def test_create_swallows_a_stop_failure_and_still_restarts(monkeypatch, access_point):
    """A `stop` that raises a typed `CommandError` is non-fatal; the restart is still reached."""
    events = []
    monkeypatch.setattr(ap.system, 'systemctl', _systemctl_recorder(events, fail_on=('stop', 'wpa_supplicant')))
    _patch_netifaces(monkeypatch, events)
    monkeypatch.setattr(ap.io, 'write_text', lambda *a, **k: events.append('write_text'))
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(access_point, 'connection_exists', lambda: True)

    access_point.create()  # does not raise

    assert ('systemctl', 'restart', 'NetworkManager') in events


def test_create_happy_path_ordering(monkeypatch, access_point):
    """Stops both holders, resets and adds the AP interface, writes dnsmasq, restarts
    NetworkManager, and adds the connection."""
    events = []
    monkeypatch.setattr(ap.system, 'systemctl', _systemctl_recorder(events))
    _patch_netifaces(monkeypatch, events)
    monkeypatch.setattr(ap.io, 'write_text', lambda *a, **k: events.append('write_text'))
    monkeypatch.setattr(ap.time, 'sleep', lambda seconds: None)

    # No existing connection, so the add runs; the post-add wait sees it appear.
    states = iter([False, True, True])
    monkeypatch.setattr(access_point, 'connection_exists', lambda: next(states))

    access_point.create()

    assert events == [
        ('systemctl', 'stop', 'NetworkManager'),
        ('systemctl', 'stop', 'wpa_supplicant'),
        'iw_del',
        'iw_add',
        'ip_up',
        'write_text',
        ('systemctl', 'restart', 'NetworkManager'),
        'nmcli_add',
    ]


def test_delete_tears_down_the_interface_when_connection_exists(monkeypatch, access_point):
    events = []
    _patch_netifaces(monkeypatch, events)
    monkeypatch.setattr(access_point, 'connection_exists', lambda: True)

    access_point.delete()

    assert events == ['nmcli_delete', 'iw_del']


def test_delete_tears_down_the_interface_when_no_connection(monkeypatch, access_point):
    """A missing connection still resets the interface, leaving no stale `ap0`."""
    events = []
    _patch_netifaces(monkeypatch, events)
    monkeypatch.setattr(access_point, 'connection_exists', lambda: False)

    access_point.delete()

    assert events == ['iw_del']


def test_up_brings_the_connection_up_through_the_seam(monkeypatch, access_point):
    events = []
    _patch_netifaces(monkeypatch, events)

    access_point.up()

    assert events == ['nmcli_up']


def test_down_brings_the_connection_down_through_the_seam(monkeypatch, access_point):
    events = []
    _patch_netifaces(monkeypatch, events)
    monkeypatch.setattr(access_point, 'connection_exists', lambda: True)

    access_point.down()

    assert events == ['nmcli_down']


def test_up_wraps_a_seam_failure_in_access_point_error(monkeypatch, access_point):
    """A seam `CommandError` surfaces to callers as an `AccessPointError`."""
    events = []
    _patch_netifaces(monkeypatch, events, fail_kind='nmcli_up')

    with pytest.raises(ap.AccessPointError):
        access_point.up()


@pytest.mark.parametrize('method', ['create', 'delete'])
def test_off_platform_raises(monkeypatch, method):
    """`@platform.requires('dietpi')` prevents mutating a dev machine."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    point = ap.AccessPoint(name='audera', url='http://audera.local', interface='wlan0')
    monkeypatch.setattr(platform, 'NAME', 'windows')
    with pytest.raises(RuntimeError):
        getattr(point, method)()
