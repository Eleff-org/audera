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
    new_config = {'filters': {'hp': {'type': 'Biquad'}}, 'mixers': {}, 'pipeline': []}
    client.set_config(new_config)

    result = client.get_config()
    assert result == new_config


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
    assert c.percent_to_db(100) == -3.0  # clamped to MAX_SAFE_DB
    assert c.percent_to_db(50) == pytest.approx(-6.021, abs=1e-3)  # not clamped (quieter)
    assert c.percent_to_db(0) == -90.0


def test_db_to_percent():
    c = CamillaDSPClient('localhost', 0)
    assert c.db_to_percent(0.0) == 100
    assert c.db_to_percent(-6.0) == 50
    assert c.db_to_percent(-90.0) == 0


def test_set_percent_volume(client):
    client.set_percent_volume(75)
    result = client.get_volume()
    assert result == -3.0  # clamped by MAX_SAFE_DB


def test_get_percent_volume(client):
    client.set_volume(-6.0)
    assert client.get_percent_volume() == 50
