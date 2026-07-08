import json
import os

import audera.dal.players as players
from audera.models.player import Player


def _write_player_file(id: str, data: dict) -> None:
    """Writes a hand-crafted player config file directly to the players DAL path."""
    os.makedirs(players.PATH, exist_ok=True)
    with open(os.path.join(players.PATH, f'{id}.json'), 'w') as f:
        json.dump({'player': data}, f)


def _make_player(id='abc123', host='192.168.1.50', connected=True) -> Player:
    return Player(
        id=id,
        host=host,
        port=1704,
        connected=connected,
        volume=80,
        muted=False,
        group_id='',
    )


def test_player_create(audera_home):
    player = _make_player()
    players.create(player)
    assert players.exists(player.id)


def test_player_get(audera_home):
    player = _make_player()
    players.create(player)

    result = players.get(player.id)
    assert result == player


def test_player_update(audera_home):
    player = _make_player()
    players.create(player)

    updated = Player(
        id=player.id,
        host=player.host,
        port=player.port,
        connected=False,
        volume=50,
        muted=True,
        group_id='group-1',
    )
    players.update(updated)

    result = players.get(player.id)
    assert result.volume == 50
    assert result.muted is True
    assert result.group_id == 'group-1'


def test_player_delete(audera_home):
    player = _make_player()
    players.create(player)
    players.delete(player.id)
    assert not players.exists(player.id)


def test_get_all_players(audera_home):
    p1 = _make_player(id='p1', host='192.168.1.1')
    p2 = _make_player(id='p2', host='192.168.1.2')
    players.create(p1)
    players.create(p2)

    result = players.get_all_players()
    ids = {p.id for p in result}
    assert ids == {'p1', 'p2'}


def test_get_all_players_empty(audera_home):
    result = players.get_all_players()
    assert result == []


def test_get_player_by_host(audera_home):
    player = _make_player(id='find-me', host='10.0.0.5')
    players.create(player)

    result = players.get_player_by_host('10.0.0.5')
    assert result is not None
    assert result.id == 'find-me'


def test_get_player_by_host_missing(audera_home):
    result = players.get_player_by_host('10.0.0.99')
    assert result is None


def test_get_all_connected_players(audera_home):
    p_on = _make_player(id='on', host='192.168.1.10', connected=True)
    p_off = _make_player(id='off', host='192.168.1.11', connected=False)
    players.create(p_on)
    players.create(p_off)

    result = players.get_all_connected_players()
    assert len(result) == 1
    assert result[0].id == 'on'


def test_get_all_players_unions_mixed_old_and_new_files(audera_home):
    """Guards the DuckDB read_json_auto schema-union path across mixed old/new files.

    An old player file predates the `dsp_id` column; a new one carries it. Reading both
    back must not raise, and the old row's `dsp_id` must surface as '' (coerced from the
    NULL DuckDB fills in for the missing column).
    """
    _write_player_file(
        'old',
        {
            'id': 'old',
            'host': '192.168.1.1',
            'port': 1704,
            'connected': True,
            'volume': 80,
            'muted': False,
            'group_id': '',
        },
    )
    _write_player_file(
        'new',
        {
            'id': 'new',
            'host': '192.168.1.2',
            'port': 1704,
            'connected': True,
            'volume': 80,
            'muted': False,
            'group_id': '',
            'dsp_id': 'dsp-1',
        },
    )

    result = {p.id: p for p in players.get_all_players()}
    assert set(result) == {'old', 'new'}
    assert result['old'].dsp_id == ''
    assert result['new'].dsp_id == 'dsp-1'
