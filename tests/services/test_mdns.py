"""Integration tests for audera.services.mdns"""

import time

import pytest

from audera.models.identity import Identity, generate_uuid_from_mac_address
from audera.services.mdns import PlayerBroadcaster, PlayerDiscovery

_MAC = 'aa:bb:cc:dd:ee:ff'
_PORT = 18080
_IDENTITY = Identity(
    name='test-player',
    uuid=generate_uuid_from_mac_address(_MAC),
    mac_address=_MAC,
    address='127.0.0.1',
)


@pytest.fixture
def discovery():
    d = PlayerDiscovery()
    yield d
    d.close()


def test_broadcaster_registers_and_discovery_finds_player(discovery):
    broadcaster = PlayerBroadcaster(identity=_IDENTITY, port=_PORT)
    broadcaster.start()
    try:
        time.sleep(2.0)
        players = discovery.get_players()
        match = next((p for p in players if p[0] == 'test-player'), None)
        assert match is not None
        _, ip, port = match
        assert ip == '127.0.0.1'
        assert port == _PORT
    finally:
        broadcaster.stop()


def test_broadcaster_stop_removes_player_from_discovery(discovery):
    broadcaster = PlayerBroadcaster(identity=_IDENTITY, port=_PORT)
    broadcaster.start()
    time.sleep(2.0)
    broadcaster.stop()
    time.sleep(2.0)
    players = discovery.get_players()
    names = [name for name, _ip, _port in players]
    assert 'test-player' not in names
