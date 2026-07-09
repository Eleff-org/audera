from audera.models.player import Player


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
