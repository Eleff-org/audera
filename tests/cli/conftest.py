"""Fixtures for driving the `audera` CLI as a process."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from audera.dal import sources as sources_dal


def _entrypoint() -> list[str]:
    """Returns the argv that runs the CLI, preferring the installed console script.

    Probed rather than assumed: a `sys.executable` outside the project's virtual environment has no
    `audera` beside it, and a moved environment leaves a shim that exists and fails. Existence is
    therefore not the test; running `--help` is.

    The fallback imports `main` rather than running `python -m audera.cli.audera`, which imports
    the module a second time under `__main__` and emits a `RuntimeWarning` on stderr that the two
    exit-code tests below read.
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

    The CLI is what provisioning calls, so it is tested the way provisioning calls it: as a
    process, through argparse, reading stdout. An in-process call can pass arguments argparse
    forbids, and `audera streamer units` was asserted for years in a shape the shell cannot
    produce.

    Isolating the home takes both variables. `audera/dal/path.py` computes `HOME` from
    `expanduser('~')` at import, so the child never sees `tests/conftest.py`'s monkeypatched
    `PATH`; and `ntpath.expanduser` never reads `HOME`, it reads `USERPROFILE` and then
    `HOMEDRIVE` + `HOMEPATH`. With `HOME` alone the child read the developer's own `~/.audera`
    and reported their recorded sources, which is a test passing against the wrong device.

    Tests seed that home through `dal.sources` — pointed at the same directory the child
    resolves — rather than through `conftest.py`'s `audera_home`, whose monkeypatched module
    attribute no other process can see.
    """
    home = tmp_path / 'home'
    (home / '.audera').mkdir(parents=True)
    monkeypatch.setattr(sources_dal, 'PATH', str(home / '.audera'))

    env = {**os.environ, 'HOME': str(home), 'USERPROFILE': str(home)}
    env.pop('HOMEDRIVE', None)
    env.pop('HOMEPATH', None)

    def run(*args: str) -> subprocess.CompletedProcess:
        # `text=True` for its universal-newline translation. `sys.stdout.write` emits `\r\n` on
        # Windows, which no comparison against a rendered string survives.
        return subprocess.run([*ENTRY, *args], capture_output=True, text=True, env=env, timeout=60)

    return run
