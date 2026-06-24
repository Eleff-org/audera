import time
from pathlib import Path

import pytest

pytest_plugins = ['nicegui.testing.user_plugin']


def _wait_for_http(container, internal_port: int, path: str = '/', timeout: float = 180) -> None:
    import httpx

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(internal_port))
    url = f'http://{host}:{port}{path}'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=2)
            return
        except Exception:
            time.sleep(1)
    stdout, stderr = container.get_logs()
    raise TimeoutError(
        f'HTTP {url} not ready after {timeout}s.\nstdout: {stdout.decode()[-2000:]}\nstderr: {stderr.decode()[-2000:]}'
    )


def _wait_for_client(host: str, port: int, timeout: float = 90) -> None:
    from audera.clients import SnapserverClient

    snap = SnapserverClient(host, port)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if snap.get_clients():
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f'No snapclient connected to {host}:{port} after {timeout}s')


@pytest.fixture
def audera_home(tmp_path, monkeypatch):
    for module, subdir in [
        ('audera.dal.players', 'players'),
        ('audera.dal.groups', 'groups'),
        ('audera.dal.streams', 'streams'),
        ('audera.dal.dsp', 'dsp'),
        ('audera.dal.settings', 'settings'),
    ]:
        dest = str(tmp_path / subdir)
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module + '.PATH', dest)
    return tmp_path


@pytest.fixture(scope='session')
def snapserver_container():
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.image import DockerImage

    conf_path = Path(__file__).parent.parent / 'audera/conf/streamer/snapserver.conf'
    context = Path(__file__).parent / 'docker' / 'snapserver'
    with DockerImage(path=str(context), tag='snapserver-test:latest') as image:
        with (
            DockerContainer(str(image))
            .with_volume_mapping(str(conf_path), '/etc/snapserver.conf', 'ro')
            .with_exposed_ports(1780)
        ) as container:
            _wait_for_http(container, 1780, timeout=180)
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(1780))
            _wait_for_client(host, port)
            yield host, port


def _wait_for_websocket(container, internal_port: int, timeout: float = 60) -> None:
    import websockets.sync.client

    host = container.get_container_host_ip()
    port = int(container.get_exposed_port(internal_port))
    url = f'ws://{host}:{port}'
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with websockets.sync.client.connect(url, open_timeout=2):
                return
        except Exception:
            time.sleep(1)
    stdout, stderr = container.get_logs()
    raise TimeoutError(
        f'WebSocket {url} not ready after {timeout}s.\nstdout: {stdout.decode()[-2000:]}\nstderr: {stderr.decode()[-2000:]}'
    )


@pytest.fixture(scope='session')
def camilladsp_container():
    from testcontainers.core.container import DockerContainer
    from testcontainers.core.image import DockerImage

    context = Path(__file__).parent / 'docker' / 'camilladsp'
    with DockerImage(path=str(context), tag='camilladsp-test:latest') as image:
        with DockerContainer(str(image)).with_exposed_ports(1234) as container:
            _wait_for_websocket(container, 1234, timeout=60)
            host = container.get_container_host_ip()
            port = int(container.get_exposed_port(1234))
            yield host, port
