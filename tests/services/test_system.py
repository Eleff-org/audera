"""Tests for the systemd seam's `reboot()`.

`reboot()` routes through `systemctl()` so it inherits the `TIMEOUT`, the `stderr` logging, and the
exception translation. The real reboot is verified by flashing a device (see `os/dietpi/AGENTS.md`);
here the seam is faked, so the dev box never restarts.
"""

import subprocess

import pytest

from audera.services import platform, system


def test_reboot_off_platform_raises(monkeypatch):
    """`@platform.requires('dietpi')` prevents rebooting a dev machine."""
    monkeypatch.setattr(platform, 'NAME', 'windows')
    with pytest.raises(RuntimeError):
        system.reboot()


def test_reboot_routes_through_systemctl(monkeypatch):
    """On-device, `reboot()` runs `systemctl reboot` unprivileged (no `sudo`)."""
    monkeypatch.setattr(platform, 'NAME', 'dietpi')
    calls = []
    monkeypatch.setattr(system.subprocess, 'run', lambda argv, **k: calls.append(argv) or subprocess.CompletedProcess(argv, 0))

    system.reboot()

    assert calls == [['systemctl', 'reboot']]
