from audera.models.player import Group, Player


def test_player_is_live_only_dto_without_dsp_id():
    # `Player` is a pure live DTO built from a `get_clients()`-shaped payload; it carries
    # no persisted `dsp_id` FK, and pydantic ignores any unknown keys in the payload.
    player = Player.from_dict(
        {
            'id': 'abc123',
            'host': '192.168.1.50',
            'port': 1704,
            'connected': True,
            'volume': 80,
            'muted': False,
            'group_id': '',
            'dsp_id': 'stale',
        }
    )
    assert not hasattr(player, 'dsp_id')


def test_group_to_dict_from_dict_roundtrip():
    # `Group` is a live Snapcast-owned DTO with a hand-written `to_dict`; its round-trip
    # was previously only asserted by the retired groups DAL tests, so it lives here now.
    group = Group(
        id='grp1',
        name='Living Room',
        client_ids=['client-a', 'client-b'],
        stream_id='stream-1',
        muted=True,
        volume=60,
    )
    assert Group.from_dict(group.to_dict()) == group
