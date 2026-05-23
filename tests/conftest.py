import json
import threading
import time
from pathlib import Path

import pytest
import websockets.sync.server

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

    conf_path = Path(__file__).parent.parent / 'os/dietpi/streamer/conf/snapserver.conf'
    with (
        DockerContainer('debian:bookworm')
        .with_volume_mapping(str(conf_path), '/etc/snapserver.conf', 'ro')
        .with_exposed_ports(1780)
        .with_command(
            'bash -c "'
            'apt-get update -qq'
            " && echo 'deb http://deb.debian.org/debian bookworm-backports main'"
            ' >> /etc/apt/sources.list'
            ' && apt-get update -qq'
            ' && DEBIAN_FRONTEND=noninteractive'
            ' apt-get install -t bookworm-backports -y'
            ' -o Dpkg::Options::=--force-confold snapserver'
            ' && snapserver --config /etc/snapserver.conf"'
        )
    ) as container:
        _wait_for_http(container, 1780, timeout=180)
        host = container.get_container_host_ip()
        port = container.get_exposed_port(1780)
        yield host, int(port)


def _make_camilladsp_handler(state: dict):
    def handler(ws):
        for raw in ws:
            msg = json.loads(raw)
            if msg == 'GetConfig':
                ws.send(json.dumps({'GetConfig': state['config']}))
            elif isinstance(msg, dict) and 'SetConfig' in msg:
                state['config'] = msg['SetConfig']
                ws.send(json.dumps({'SetConfig': 'Ok'}))
            elif msg == 'GetVolume':
                ws.send(json.dumps({'GetVolume': state['volume']}))
            elif isinstance(msg, dict) and 'SetVolume' in msg:
                state['volume'] = msg['SetVolume']
                ws.send(json.dumps({'SetVolume': 'Ok'}))
            else:
                ws.send(json.dumps({'result': 'Error', 'message': 'Unknown command'}))

    return handler


@pytest.fixture
def camilladsp_mock():
    state = {'config': {'filters': {}, 'mixers': {}, 'pipeline': []}, 'volume': -10.0}
    server = websockets.sync.server.serve(_make_camilladsp_handler(state), '127.0.0.1', 0)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield '127.0.0.1', port
    server.shutdown()


def _error_handler(ws):
    for _ in ws:
        ws.send(json.dumps({'result': 'Error', 'message': 'Forced error'}))


@pytest.fixture
def camilladsp_error_mock():
    server = websockets.sync.server.serve(_error_handler, '127.0.0.1', 0)
    port = server.socket.getsockname()[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield '127.0.0.1', port
    server.shutdown()
