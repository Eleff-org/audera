import pytest

from audera.clients import CamillaDSPClient


@pytest.fixture
def client(camilladsp_mock):
    host, port = camilladsp_mock
    return CamillaDSPClient(host, port)


@pytest.fixture
def error_client(camilladsp_error_mock):
    host, port = camilladsp_error_mock
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


def test_error_response_raises(error_client):
    with pytest.raises(RuntimeError):
        error_client.get_config()
