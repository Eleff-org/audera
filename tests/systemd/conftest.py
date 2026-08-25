"""Host-side fixtures for the real-systemd lane.

`test_container.py` is the driver: it boots a privileged container with systemd as PID 1 and
`docker exec`s an inner pytest per module under `inside/`. Everything in `inside/` runs in the
container, against the device's own provisioning.

Requires Docker and a privileged container. `AUDERA_IN_SYSTEMD_CONTAINER` is set as image `ENV`, so
`docker exec` inherits it and the inner pytest is the only one that collects `inside/`.
"""

import os
import time
from pathlib import Path

import pytest

from tests.helpers import raise_with_logs

ROOT = Path(__file__).resolve().parents[2]

# `inside/` is uncollectable outside the container rather than deselected by marker. The inner modules
# import `audera.services.system` and call it for effect, so collecting them on a developer's machine
# would issue `systemctl` against the developer's own init system.
#
# The directory is ignored rather than its contents: `'inside/*'` ignores the modules but pytest still
# descends into the directory to load its `conftest.py`, which reads the `/app/os/dietpi/lib/` shell
# libraries at import, a path that exists only in the container.
collect_ignore_glob = [] if os.getenv('AUDERA_IN_SYSTEMD_CONTAINER') else ['inside']

# How long to let systemd finish booting before giving up on the container.
_BOOT_TIMEOUT: float = 180

# The states that mean the manager is up. `degraded` is included because `systemd-modules-load`
# cannot load kernel modules in a container and settles `failed`, so a wait for `running` alone would
# always time out on a container that is ready.
_READY_STATES = ('running', 'degraded')


def pytest_collection_modifyitems(config, items):
    """Marks everything under this directory `systemd`, so no module restates it.

    Applies to the driver and the inner modules alike, which is why the driver's inner command passes
    `-m systemd`: `addopts` deselects the marker by default.

    The path test is required. A `conftest.py` hook is registered against the whole session, so
    `items` is every test pytest collected, and marking unconditionally would leave a bare
    `uv run pytest` selecting nothing.
    """
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker('systemd')


def _decode(output) -> str:
    """Renders `container.exec`'s output, which is `bytes` for a combined stream."""
    if isinstance(output, tuple):
        return ''.join(part.decode(errors='replace') for part in output if part)
    return output.decode(errors='replace')


def _wait_for_systemd(container, timeout: float = _BOOT_TIMEOUT) -> None:
    """Blocks until `systemctl is-system-running` reports a ready state.

    Polls rather than matching a log line, since systemd's console output is not a readiness protocol.
    The exit status is ignored because it is non-zero for `degraded`, the expected steady state here.
    """
    deadline = time.monotonic() + timeout
    state = '<no answer>'
    while time.monotonic() < deadline:
        try:
            _, output = container.exec(['systemctl', 'is-system-running'])
            state = _decode(output).strip()
        except Exception as exc:
            state = f'<exec failed: {exc}>'
        if state in _READY_STATES:
            return
        time.sleep(1)

    raise_with_logs(container, f'systemd not ready after {timeout}s; last state {state!r}.', timeout)


@pytest.fixture(scope='session')
def systemd_image():
    """Builds the systemd image once per session and yields its tag.

    The context is the repo root, for the reasons `.dockerignore` states. A cold build is around
    three minutes, dominated by the apt install and by compiling `netifaces`; the Dockerfile's layer
    order makes a source-only rebuild seconds. buildx caching is unavailable, since `DockerImage`
    uses docker-py's legacy build endpoint.
    """
    from testcontainers.core.image import DockerImage

    with DockerImage(
        path=str(ROOT),
        dockerfile_path='tests/docker/systemd/Dockerfile',
        tag='audera-systemd-test:latest',
    ) as image:
        yield str(image)


@pytest.fixture(scope='session')
def systemd_container(systemd_image):
    """Boots systemd as PID 1 and yields the container.

    The code under test runs inside the container, so the fixture yields the handle rather than the
    `(host, port)` the suite's other container fixtures yield.

    The keyword arguments are one `with_kwargs` call because it replaces rather than merges:

    - `privileged` and a read-write `/sys/fs/cgroup` let systemd manage cgroups. On an ephemeral
      GitHub-hosted VM that is safe; on a self-hosted runner it grants container root, and the
      workflow says so.
    - `cgroupns='host'` keeps systemd in the host's cgroup namespace, so it works across both the
      cgroup v1 the development machine runs and the v2 hosted runners do. Assertions still never
      read `/sys/fs/cgroup`; `inside/conftest.py`'s module docstring records why.
    - `/run` and `/run/lock` as tmpfs, which systemd requires writable and expects empty at boot.
    - `extra_hosts` resolves `plex.tv` locally, so `plexamp.service` runs verbatim rather than needing
      a container-only drop-in over the step under test; otherwise its `ExecStartPre` polls
      `getent hosts plex.tv` for up to 60 s. It is a run argument rather than a Dockerfile line
      because Docker bind-mounts `/etc/hosts` at container start, discarding anything the image wrote.
    """
    from testcontainers.core.container import DockerContainer

    container = DockerContainer(systemd_image).with_kwargs(
        privileged=True,
        cgroupns='host',
        tmpfs={'/run': '', '/run/lock': ''},
        extra_hosts={'plex.tv': '127.0.0.1'},
    )
    container.with_volume_mapping('/sys/fs/cgroup', '/sys/fs/cgroup', 'rw')

    with container:
        _wait_for_systemd(container)
        yield container
