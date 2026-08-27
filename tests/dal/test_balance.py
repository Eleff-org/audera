import os

import pytest

import audera.dal.balance as balance_dal
from audera.errors import StorageError
from audera.models.balance import ReferenceBalance


def _write_corrupt() -> str:
    """Writes an unparseable reference-balance file and returns its path."""
    os.makedirs(balance_dal.PATH, exist_ok=True)
    file_path = os.path.join(balance_dal.PATH, balance_dal.FILE_NAME)
    with open(file_path, 'w') as f:
        f.write('{ not json')
    return file_path


def test_balance_absent_by_default(audera_home):
    assert not balance_dal.exists()


def test_balance_save_then_exists(audera_home):
    balance_dal.save(ReferenceBalance(volumes={'aa:bb:cc:dd:ee:ff': 70}))
    assert balance_dal.exists()


def test_balance_round_trip(audera_home):
    ref = ReferenceBalance(volumes={'player-1': 40, 'player-2': 60})
    balance_dal.save(ref)
    assert balance_dal.get() == ref


def test_balance_save_overwrites(audera_home):
    balance_dal.save(ReferenceBalance(volumes={'player-1': 40}))
    balance_dal.save(ReferenceBalance(volumes={'player-2': 90}))
    assert balance_dal.get().volumes == {'player-2': 90}


def test_balance_mac_address_player_id(audera_home):
    mac_id = 'aa:bb:cc:dd:ee:ff'
    balance_dal.save(ReferenceBalance(volumes={mac_id: 55}))
    assert balance_dal.get().volumes == {mac_id: 55}


def test_balance_empty_round_trip(audera_home):
    balance_dal.save(ReferenceBalance())
    assert balance_dal.get().volumes == {}


def test_balance_get_raises_storage_error_on_corrupt_file(audera_home):
    _write_corrupt()
    with pytest.raises(StorageError):
        balance_dal.get()


def test_save_notifies_observers(audera_home):
    fired: list[bool] = []
    balance_dal.on_change(lambda: fired.append(True))
    balance_dal.save(ReferenceBalance(volumes={'player-1': 50}))
    assert fired == [True]
