import os
import threading

import audera.dal.volume as volume_dal
from audera.dal import path


def test_volume_get_absent_returns_none(audera_home):
    assert volume_dal.get('abc123') is None


def test_volume_round_trip(audera_home):
    volume_dal.set('abc123', 75)
    assert volume_dal.get('abc123') == 75


def test_volume_overwrite(audera_home):
    volume_dal.set('abc123', 50)
    volume_dal.set('abc123', 90)
    assert volume_dal.get('abc123') == 90


def test_volume_get_all_empty(audera_home):
    assert volume_dal.get_all() == {}


def test_volume_get_all_returns_all_players(audera_home):
    volume_dal.set('player-1', 40)
    volume_dal.set('player-2', 60)
    assert volume_dal.get_all() == {'player-1': 40, 'player-2': 60}


def test_volume_mac_address_player_id(audera_home):
    mac_id = 'aa:bb:cc:dd:ee:ff'
    volume_dal.set(mac_id, 55)
    assert volume_dal.get(mac_id) == 55
    assert volume_dal.get_all() == {mac_id: 55}


def test_volume_get_all_reads_player_id_from_document(audera_home):
    """The filename is lossy (colons become dashes), so get_all reads the raw id from inside."""
    mac_id = 'aa:bb:cc:dd:ee:ff'
    volume_dal.set(mac_id, 42)
    all_vols = volume_dal.get_all()
    assert mac_id in all_vols
    assert all_vols[mac_id] == 42


def test_volume_malformed_file_returns_none(audera_home):

    os.makedirs(volume_dal.PATH, exist_ok=True)
    file_path = os.path.join(volume_dal.PATH, path.to_filename('bad'))
    with open(file_path, 'w') as f:
        f.write('not json')
    assert volume_dal.get('bad') is None


def test_volume_malformed_file_skipped_in_get_all(audera_home):

    volume_dal.set('good', 80)
    file_path = os.path.join(volume_dal.PATH, path.to_filename('bad'))
    with open(file_path, 'w') as f:
        f.write('not json')
    assert volume_dal.get_all() == {'good': 80}


def test_volume_observer_fires_on_set(audera_home):
    fired = []
    volume_dal.on_change(lambda: fired.append(True))
    try:
        volume_dal.set('abc123', 70)
        assert fired == [True]
    finally:
        volume_dal._observers.pop()


def test_volume_observer_failure_does_not_prevent_write(audera_home):
    def _boom():
        raise RuntimeError('observer failed')

    volume_dal.on_change(_boom)
    try:
        volume_dal.set('abc123', 65)
        assert volume_dal.get('abc123') == 65
    finally:
        volume_dal._observers.pop()


def test_volume_concurrent_writes(audera_home):
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _write(player_id, percent):
        try:
            barrier.wait(timeout=5)
            volume_dal.set(player_id, percent)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_write, args=('p1', 30))
    t2 = threading.Thread(target=_write, args=('p2', 70))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, errors
    assert volume_dal.get('p1') == 30
    assert volume_dal.get('p2') == 70
