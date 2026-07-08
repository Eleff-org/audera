import pytest

from audera.clients import CamillaDSPClient


@pytest.fixture(scope='session')
def client(camilladsp_container):
    host, port = camilladsp_container
    return CamillaDSPClient(host, port)


def test_get_config(client):
    config = client.get_config()
    assert isinstance(config, dict)


def test_set_config(client):
    original = client.get_config()
    new_config = {**original, 'filters': {}, 'pipeline': []}
    client.set_config(new_config)
    result = client.get_config()
    assert result['filters'] == {}
    assert result['pipeline'] == []


def test_get_volume(client):
    volume = client.get_volume()
    assert isinstance(volume, float)


def test_set_volume(client):
    client.set_volume(-20.0)
    result = client.get_volume()
    assert result == -20.0


def test_error_response_raises(client):
    with pytest.raises(RuntimeError):
        client._call('UnknownCommand')


def test_percent_to_db():
    c = CamillaDSPClient('localhost', 0)
    assert c.percent_to_db(100) == 0.0
    assert c.percent_to_db(50) == pytest.approx(-6.021, abs=1e-3)
    assert c.percent_to_db(0) == -50.0


def test_default_percent_volume_matches_shell_gain_literal():
    """Guards the Python constant against the hard-coded `--gain -12.04` shell literal.

    `os/dietpi/lib/common.sh:write_camilladsp_service` seeds a fresh statefile with
    `--gain -12.04` (= percent_to_db(25)); the two must never silently drift.
    """
    c = CamillaDSPClient('localhost', 0)
    assert round(c.percent_to_db(CamillaDSPClient.DEFAULT_PERCENT_VOLUME), 2) == -12.04


def test_db_to_percent():
    c = CamillaDSPClient('localhost', 0)
    assert c.db_to_percent(0.0) == pytest.approx(100.0)
    assert c.db_to_percent(-6.0) == pytest.approx(50.12, abs=1e-2)
    assert c.db_to_percent(-50.0) == 0.0
    assert c.db_to_percent(-80.0) == 0.0


def test_set_percent_volume(client):
    client.set_percent_volume(75)
    result = client.get_volume()
    assert result == pytest.approx(-2.499, abs=1e-3)


def test_get_percent_volume(client):
    client.set_volume(-6.0)
    assert client.get_percent_volume() == 50
