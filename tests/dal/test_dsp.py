import os

import pytest

import audera.dal.dsp as dsp_dal
from audera.errors import StorageError
from audera.models.dsp import Band, DSPConfig


def _write_corrupt(player_id: str) -> str:
    """Writes an unparseable DSP file for `player_id` and returns its path."""
    from audera.dal import path

    os.makedirs(dsp_dal.PATH, exist_ok=True)
    file_path = os.path.join(dsp_dal.PATH, path.to_filename(player_id))
    with open(file_path, 'w') as f:
        f.write('{ not json')
    return file_path


def _make_dsp(player_id='abc123') -> DSPConfig:
    return DSPConfig(
        player_id=player_id,
        preamp_db=-6.0,
        bands=[Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0)],
        enabled=True,
    )


def test_dsp_create(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    assert dsp_dal.exists(config.player_id)


def test_dsp_get(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get(config.player_id)
    assert result == config


def test_dsp_update(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    updated = config.model_copy(update={'enabled': False})
    dsp_dal.update(updated)

    result = dsp_dal.get(config.player_id)
    assert result.enabled is False


def test_dsp_delete(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)
    dsp_dal.delete(config.player_id)
    assert not dsp_dal.exists(config.player_id)


def test_dsp_bands_round_trip(audera_home):
    config = DSPConfig(
        player_id='dsp-bands',
        preamp_db=-3.0,
        bands=[
            Band(id='b1', type='Lowshelf', freq=90.0, gain=10.0, q=0.7),
            Band(id='b2', type='Highshelf', freq=8000.0, gain=6.0, q=0.7),
            Band(id='b3', type='Peaking', freq=1000.0, gain=-3.0, q=2.0, enabled=False),
        ],
    )
    dsp_dal.create(config)

    result = dsp_dal.get(config.player_id)
    assert result == config
    assert [b.type for b in result.bands] == ['Lowshelf', 'Highshelf', 'Peaking']


def test_dsp_round_trip_with_mac_address_id(audera_home):
    # A Snapcast player id is a MAC address, whose colons are illegal in a Windows
    # filename (OSError 22). The DAL must sanitize them out of `dsp/{player_id}.json`.
    config = _make_dsp(player_id='d8:3a:dd:80:3c:91')
    dsp_dal.create(config)

    assert dsp_dal.exists('d8:3a:dd:80:3c:91')
    assert dsp_dal.get('d8:3a:dd:80:3c:91') == config

    # The file on disk carries no colon — the id maps to a filesystem-safe stem.
    json_files = [f for f in os.listdir(dsp_dal.PATH) if f.endswith('.json')]
    assert json_files == ['d8-3a-dd-80-3c-91.json']

    dsp_dal.delete('d8:3a:dd:80:3c:91')
    assert not dsp_dal.exists('d8:3a:dd:80:3c:91')


def test_dsp_get_or_create_creates(audera_home):
    config = _make_dsp()
    assert not dsp_dal.exists(config.player_id)

    dsp_dal.get_or_create(config)
    assert dsp_dal.exists(config.player_id)


def test_dsp_get_or_create_creates_keyed_by_player_id(audera_home):
    # The config file is `dsp/{player_id}.json` — the filename is the link to the player.
    config = dsp_dal.get_or_create(DSPConfig(player_id='abc123'))

    assert config.player_id == 'abc123'
    assert dsp_dal.exists('abc123')
    assert config.bands == []
    assert config.preamp_db == 0.0


def test_dsp_get_or_create_reads(audera_home):
    config = _make_dsp()
    dsp_dal.create(config)

    result = dsp_dal.get_or_create(config)
    assert result == config


def test_dsp_get_or_create_idempotent_after_edit(audera_home):
    dsp_dal.get_or_create(DSPConfig(player_id='abc123'))  # first open creates an empty config

    edited = _make_dsp(player_id='abc123')
    dsp_dal.update(edited)

    # A second open re-reads the edited config — it never re-mints an empty one.
    assert dsp_dal.get_or_create(DSPConfig(player_id='abc123')) == edited


def test_dsp_get_raises_storage_error_on_corrupt_file(audera_home):
    _write_corrupt('abc123')
    with pytest.raises(StorageError):
        dsp_dal.get('abc123')


def test_dsp_get_or_create_returns_seed_without_clobbering_corrupt_file(audera_home):
    file_path = _write_corrupt('abc123')
    seed = _make_dsp(player_id='abc123')

    result = dsp_dal.get_or_create(seed)

    assert result == seed
    # The corrupt file is left byte-for-byte untouched, never overwritten with the seed.
    with open(file_path, 'r') as f:
        assert f.read() == '{ not json'
