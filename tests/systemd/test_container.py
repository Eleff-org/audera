"""The driver: runs each `inside/` module as its own pytest inside the container.

Requires Docker and the privileged systemd container the package's `conftest.py` boots.

One `exec` per module rather than one for the whole directory. The modules boot no container of their
own, so the extra cost is a pytest startup each, around a second, and a failure names the module in
the host-side report rather than being buried in one combined log.

The inner pytest is invoked as `/app/.venv/bin/pytest` rather than through `uv run`, so a test run
needs no network and cannot re-resolve the environment the image built.
"""

import pytest

# Every module under `inside/`, listed rather than globbed. The conftest makes them uncollectable
# outside the container, so the host cannot import them and a typo in a glob would silently run
# nothing.
#
# The order is load-bearing at one point: the container is session-scoped, so `test_platform.py` runs
# first because it asserts `/etc/systemd/system/` ships no Audera units, and provisioning leaves them
# there. Nothing else here depends on order; the modules that provision re-run provisioning, and the
# ones that do not use the container's own stub units.
INSIDE_MODULES = ('test_platform.py', 'test_system.py', 'test_index.py', 'test_plex.py', 'test_provisioning.py')


def _run_inside(container, module: str) -> tuple[int, str]:
    """Runs one inner module and returns its exit status and combined output."""
    # `-m systemd` overrides `addopts`, which deselects the marker by default; `-p no:cacheprovider`
    # because the image's `/app` is the context copy and a written cache is noise nothing reads.
    code, output = container.exec(
        [
            '/bin/sh',
            '-c',
            f'cd /app && exec /app/.venv/bin/pytest -m systemd -v -p no:cacheprovider tests/systemd/inside/{module}',
        ]
    )
    return code, output.decode(errors='replace') if isinstance(output, bytes) else str(output)


@pytest.mark.parametrize('module', INSIDE_MODULES)
def test_inside_the_container(systemd_container, module: str):
    """Fails with the inner pytest's own report, verbatim.

    `pytrace=False`, because a host-side traceback would point at this line only. The inner run's
    output names the inner test, the inner assertion, and the unit state it read.
    """
    code, output = _run_inside(systemd_container, module)
    if code != 0:
        pytest.fail(f'tests/systemd/inside/{module} failed inside the container (exit {code}):\n\n{output}', pytrace=False)
