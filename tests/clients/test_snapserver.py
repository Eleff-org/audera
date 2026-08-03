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
