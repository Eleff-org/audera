"""Tests for the platform gate."""

import pytest

from audera.services import platform, system


@pytest.mark.parametrize('call', [lambda: system.systemctl('restart', 'snapserver'), lambda: system.is_active('plexamp')])
def test_the_systemd_seam_raises_off_platform(monkeypatch, call):
    """`@platform.requires('dietpi')` raises off-platform, so Audera cannot mutate a dev machine.

    Asserted here rather than in the container lane, which is always on-platform. `is_active` is
    covered alongside `systemctl` because it swallows a `TimeoutExpired` and an `OSError` to report
    `False`, and swallowing the gate's `RuntimeError` too would report every unit as inactive.

    `NAME` is read inside the decorator's wrapper at call time, so the late patch takes effect.
    """
    monkeypatch.setattr(platform, 'NAME', 'windows')
    with pytest.raises(RuntimeError):
        call()
