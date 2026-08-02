"""Tests that a multi-source rendered configuration boots snapserver.

The stub source binaries in the image make `process://` and `airplay://` start. These tests cover
conf acceptance and stream registration. go-librespot's Spotify session and shairport-sync's
option table need the real binaries on real hardware and are out of scope here.
"""

import pytest

from audera.clients import SnapserverClient
from audera.domains.sources import CATALOG, default_source


@pytest.fixture(scope='module')
def client(snapserver_container_all_sources):
    host, port = snapserver_container_all_sources
    return SnapserverClient(host, port)


def test_snapserver_boots_with_every_source_enabled(client):
    # A conf snapserver rejects never serves JSON-RPC, so a successful call means the rendered
    # conf booted.
    assert 'server' in client.get_status()


def test_every_catalogued_source_registers_as_a_stream(client):
    status = client.get_stream_status()
    for source in CATALOG:
        assert source.id in status


def test_clients_land_on_the_default_source(client):
    # Checks that `default_source` is an accepted key on the pinned 0.31.0 and that its value
    # resolves to a real stream rather than mis-routing.
    expected = default_source([source.id for source in CATALOG])
    groups = client.get_groups()
    assert groups
    assert all(group.stream_id == expected for group in groups)


def test_set_group_stream_reassigns_a_group(client):
    # The container is session-scoped, so the move is undone before returning. Leaving it applied
    # would make `test_clients_land_on_the_default_source` depend on running first.
    group = client.get_groups()[0]
    original = group.stream_id

    # Any stream the group is not already on; a move onto the current stream would assert nothing.
    destination = next(source.id for source in CATALOG if source.id != original)

    try:
        client.set_group_stream(group.id, destination)
        assert destination in client.get_stream_status()
        assert next(g for g in client.get_groups() if g.id == group.id).stream_id == destination
    finally:
        client.set_group_stream(group.id, original)
