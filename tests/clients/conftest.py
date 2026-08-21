"""Docker-availability guard for the client lane.

`tests/conftest.py`'s container fixtures build a `DockerImage`/`DockerContainer` unguarded, so on
a machine without Docker they *error* rather than *skip*. This probes Docker once per session and
skips any test that pulls in a container fixture when the daemon is unreachable — tests that need
no container (e.g. the pure `_call`/parse regressions) still run.
"""

import functools

import pytest

# Fixtures whose setup requires a reachable Docker daemon. A test that requests any of these
# (directly or transitively) is skipped rather than errored when Docker is unavailable.
_DOCKER_FIXTURES = {
    'client',
    'snapserver_image',
    'snapserver_container',
    'snapserver_container_all_sources',
    'camilladsp_container',
}


@functools.lru_cache(maxsize=1)
def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _require_docker(request):
    """Skips a container-backed test when Docker is unreachable."""
    if _docker_available():
        return
    if _DOCKER_FIXTURES & set(request.fixturenames):
        pytest.skip('Docker is not available')
