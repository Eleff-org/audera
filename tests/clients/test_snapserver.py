import threading

import pytest

import audera.dal.sources as sources_dal
from audera.clients import SnapserverClient
from audera.domains.sources import default_source
from audera.models.player import Group, Player


@pytest.fixture(scope='module')
def client(snapserver_container):
    host, port = snapserver_container
    return SnapserverClient(host, port)


def test_get_status(client):
    status = client.get_status()
    assert isinstance(status, dict)
    assert 'server' in status


def test_get_groups(client):
    result = client.get_groups()
    assert isinstance(result, list)
    for group in result:
        assert isinstance(group, Group)


def test_get_clients(client):
    result = client.get_clients()
    assert isinstance(result, list)
    for p in result:
        assert isinstance(p, Player)


def test_get_stream_status(client):
    # The container boots the bootstrap set, so the expected stream is derived from
    # `DEFAULT_ENABLED` rather than named here.
    expected = default_source(sources_dal.DEFAULT_ENABLED)
    result = client.get_stream_status()
    assert isinstance(result, dict)
    assert expected in result
    assert isinstance(result[expected], str)
    assert result[expected]


def test_set_client_latency(client):
    clients = client.get_clients()
    result = client.set_client_latency(clients[0].id, 50)
    assert isinstance(result, dict)


def test_get_clients_tolerates_partial_status(monkeypatch):
    """A partial client frame degrades to defaults; a frame without an id is skipped, not a KeyError.

    Pure parse test (no container): `get_status` is stubbed with a payload missing nested keys.
    """
    snap = SnapserverClient('127.0.0.1', 1780)
    status = {
        'server': {
            'groups': [
                {
                    'id': 'g1',
                    'clients': [
                        {'id': 'ok'},  # no host/config/connected/volume -> all defaulted
                        {'host': {'ip': '1.2.3.4'}},  # no id -> skipped
                    ],
                }
            ],
            'streams': [],
        }
    }
    monkeypatch.setattr(snap, 'get_status', lambda: status)

    result = snap.get_clients()

    assert [p.id for p in result] == ['ok']
    parsed = result[0]
    assert parsed.connected is False
    assert parsed.volume == 0
    assert parsed.muted is False
    assert parsed.group_id == 'g1'
    assert parsed.port == 0


def test_get_stream_status_tolerates_partial_status(monkeypatch):
    """A stream without an id is skipped and a stream without a status degrades to ''."""
    snap = SnapserverClient('127.0.0.1', 1780)
    status = {
        'server': {
            'streams': [
                {'id': 's1', 'status': 'playing'},
                {'status': 'idle'},  # no id -> skipped
                {'id': 's2'},  # no status -> ''
            ]
        }
    }
    monkeypatch.setattr(snap, 'get_status', lambda: status)

    assert snap.get_stream_status() == {'s1': 'playing', 's2': ''}


def test_call_id_matching_under_notification_pressure(snapserver_container):
    """_call must return the response matching the request id, not a notification.

    Three background threads drive Client.SetVolume to create notification pressure on the
    WebSocket. 100 concurrent get_status() calls must all return a dict containing 'server',
    proving _call never returns {} (a notification frame that lacks a matching id).
    """
    host, port = snapserver_container
    clients = SnapserverClient(host, port).get_clients()
    if not clients:
        pytest.skip('no snapclient connected')
    target = clients[0].id

    stop = threading.Event()
    errors: list[Exception] = []

    def _pressure():
        snap = SnapserverClient(host, port)
        vol = 50
        while not stop.is_set():
            try:
                snap.set_client_volume(target, vol, muted=False)
                vol = 100 - vol
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=_pressure, daemon=True) for _ in range(3)]
    for t in threads:
        t.start()

    try:
        snap = SnapserverClient(host, port)
        for i in range(100):
            status = snap.get_status()
            assert isinstance(status, dict), f'iteration {i}: got {type(status)}'
            assert 'server' in status, f'iteration {i}: missing server key, got {status}'
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5)
