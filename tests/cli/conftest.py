"""Fixtures for driving the `audera` CLI as a process."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from audera.dal import sources as sources_dal


def _entrypoint() -> list[str]:
    """Returns the argv that runs the CLI, preferring the installed console script.

    The script is probed with `--help` rather than checked for existence, since a moved environment
    leaves a shim that exists and fails.

    The fallback imports `main` rather than running `python -m audera.cli.audera`, which imports
    the module a second time under `__main__` and emits a `RuntimeWarning` on stderr that the
    exit-code tests read.
    """
    fallback = [sys.executable, '-c', 'from audera.cli.audera import main; main()']
    script = Path(sys.executable).with_name('audera.exe' if os.name == 'nt' else 'audera')
    if not script.is_file():
        return fallback
    try:
        if subprocess.run([str(script), '--help'], capture_output=True, timeout=60).returncode == 0:
            return [str(script)]
    except (OSError, subprocess.SubprocessError):
        pass
    return fallback


ENTRY = _entrypoint()


@pytest.fixture
def audera_cli(tmp_path, monkeypatch):
    """Runs the installed `audera` console script against an isolated home.

    Provisioning calls the CLI as a process, so it is tested that way, through argparse. An
    in-process call can pass arguments argparse forbids.

    Isolating the home takes both `HOME` and `USERPROFILE`. `audera/dal/path.py` computes `HOME`
    from `expanduser('~')` at import, so the child never sees `tests/conftest.py`'s monkeypatched
    `PATH`, and `ntpath.expanduser` reads `USERPROFILE` and then `HOMEDRIVE` + `HOMEPATH`, never
    `HOME`. With `HOME` alone the child read the developer's own `~/.audera`.

    Tests seed that home through `dal.sources`, pointed at the same directory the child resolves,
    rather than through `conftest.py`'s `audera_home`, whose monkeypatched module attribute no
    other process can see.
    """
    home = tmp_path / 'home'
    (home / '.audera').mkdir(parents=True)
    monkeypatch.setattr(sources_dal, 'PATH', str(home / '.audera'))

    env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home)}
    env.pop('HOMEDRIVE', None)
    env.pop('HOMEPATH', None)

    def run(*args: str) -> subprocess.CompletedProcess:
        # `text=True` for its universal-newline translation, since `sys.stdout.write` emits `\r\n`
        # on Windows.
        return subprocess.run([*ENTRY, *args], capture_output=True, text=True, env=env, timeout=60)

    return run
