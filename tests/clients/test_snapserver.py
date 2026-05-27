import pytest

from audera.clients import SnapserverClient
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


def test_set_client_latency(client):
    clients = client.get_clients()
    result = client.set_client_latency(clients[0].id, 50)
    assert isinstance(result, dict)
