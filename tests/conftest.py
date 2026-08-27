import os
import time
from pathlib import Path

import pytest

from tests.helpers import raise_with_logs

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
    raise_with_logs(container, f'HTTP {url} not ready after {timeout}s.', timeout)


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
        ('audera.dal.balance', 'balance'),
        ('audera.dal.dsp', 'dsp'),
        ('audera.dal.presets', 'dsp/presets'),
        ('audera.dal.settings', 'settings'),
        ('audera.dal.sources', 'sources'),
        ('audera.dal.volume', 'volume'),
    ]:
        dest = str(tmp_path / subdir)
        (tmp_path / subdir).mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(module + '.PATH', dest)
    return tmp_path


@pytest.fixture
def audera_home_process(tmp_path, monkeypatch):
    """Isolates `~/.audera` for a child process, returning `(home, env)`.

    A child resolves `~/.audera` from its environment, not from `audera_home`'s monkeypatched module
    attribute, which reaches this process only. `audera/dal/path.py` computes `HOME` from
    `expanduser('~')` at import, and `ntpath.expanduser` reads `USERPROFILE` then `HOMEDRIVE` +
    `HOMEPATH`, never `HOME`; so isolating the home takes `HOME`/`USERPROFILE` set and
    `HOMEDRIVE`/`HOMEPATH` popped. `sources_dal.PATH` is pointed at the same directory the child
    resolves so a test can seed that home in-process and have the child read it.
    """
    from audera.dal import sources as sources_dal

    home = tmp_path / 'home'
    (home / '.audera').mkdir(parents=True)
    monkeypatch.setattr(sources_dal, 'PATH', str(home / '.audera'))

    env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home)}
    env.pop('HOMEDRIVE', None)
    env.pop('HOMEPATH', None)
    return home, env


@pytest.fixture(scope='session')
def snapserver_image():
    """Builds the snapserver image once per session and yields its tag.

    Shared by every snapserver container fixture, since two fixtures building and removing the
    same tag conflict on teardown.
    """
    from testcontainers.core.image import DockerImage

    context = Path(__file__).parent / 'docker' / 'snapserver'
    with DockerImage(path=str(context), tag='snapserver-test:latest') as image:
        yield str(image)


def _snapserver_container(image: str, tmp_path_factory, snapserver_conf: str, name: str):
    """Boots a snapserver container against `snapserver_conf` and yields its (host, port).

    The conf is mounted read-only at `/etc/snapserver.conf`. A conf snapserver rejects never
    reaches the HTTP wait.
    """
    from testcontainers.core.container import DockerContainer

    conf_file = tmp_path_factory.mktemp(name) / 'snapserver.conf'
    conf_file.write_text(snapserver_conf, encoding='utf-8')
    with (
        DockerContainer(image).with_volume_mapping(str(conf_file), '/etc/snapserver.conf', 'ro').with_exposed_ports(1780)
    ) as container:
        _wait_for_http(container, 1780, timeout=180)
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(1780))
        _wait_for_client(host, port)
        yield host, port


@pytest.fixture(scope='session')
def snapserver_container(snapserver_image, tmp_path_factory):
    from audera.cli import conf
    from audera.dal import sources as sources_dal

    yield from _snapserver_container(
        snapserver_image, tmp_path_factory, conf.render_snapserver(list(sources_dal.DEFAULT_ENABLED)), 'conf'
    )


@pytest.fixture(scope='session')
def snapserver_container_all_sources(snapserver_image, tmp_path_factory):
    """A snapserver booted from a conf with every catalogued source enabled.

    Session-scoped, so it costs one extra boot per run rather than one per test. The container's
    stub source binaries make the `process://` and `airplay://` streams start, so tests under it
    cover conf acceptance and stream registration.
    """
    from audera.cli import conf
    from audera.domains.sources import CATALOG

    yield from _snapserver_container(
        snapserver_image,
        tmp_path_factory,
        conf.render_snapserver([source.id for source in CATALOG]),
        'conf-all-sources',
    )


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
    raise_with_logs(container, f'WebSocket {url} not ready after {timeout}s.', timeout)


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
