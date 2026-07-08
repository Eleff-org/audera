from audera.models.player import Player


def _make_player(dsp_id: str = '') -> Player:
    return Player(id='abc123', host='192.168.1.50', port=1704, dsp_id=dsp_id)


def test_dsp_id_defaults_to_empty_string():
    player = _make_player()
    assert player.dsp_id == ''


def test_dsp_id_round_trips_through_to_dict():
    player = _make_player(dsp_id='dsp-1')
    assert player.to_dict()['dsp_id'] == 'dsp-1'
    assert Player.from_dict(player.to_dict()) == player


def test_dsp_id_participates_in_eq():
    a = _make_player(dsp_id='dsp-1')
    b = _make_player(dsp_id='dsp-2')
    assert a != b
    assert a == _make_player(dsp_id='dsp-1')


def test_dsp_id_none_coerces_to_empty_string():
    player = Player.from_dict({'id': 'abc123', 'host': '192.168.1.50', 'port': 1704, 'dsp_id': None})
    assert player.dsp_id == ''
