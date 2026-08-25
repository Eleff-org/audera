"""Fixtures for driving the `audera` CLI as a process."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


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
def audera_cli(audera_home_process):
    """Runs the installed `audera` console script against an isolated home.

    Provisioning calls the CLI as a process, so it is tested that way, through argparse. An
    in-process call can pass arguments argparse forbids.

    The isolated home and its `HOME`/`USERPROFILE` environment come from `conftest.py`'s
    `audera_home_process`, which also points `dal.sources` at the same directory the child resolves so
    a test can seed the home in-process.
    """
    _, env = audera_home_process

    def run(*args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        # `text=True` for its universal-newline translation, since `sys.stdout.write` emits `\r\n`
        # on Windows. `env_overrides` reaches the child as `AUDERA_`-prefixed settings, which is the
        # only way to prove from a process that a rendered value is sourced rather than hardcoded.
        return subprocess.run([*ENTRY, *args], capture_output=True, text=True, env={**env, **(env_overrides or {})}, timeout=60)

    return run
