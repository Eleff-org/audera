"""The premises every other module in this directory rests on.

Runs inside the privileged systemd container. Covers that systemd is PID 1, that the platform gate
resolves to `dietpi` without being patched, that a gated function therefore runs, and that the image
ships no Audera unit file.

The rest of the suite reaches `@platform.requires('dietpi')`'s passing branch by
`monkeypatch.setattr(platform, 'NAME', 'dietpi')`, which pins that the decorator reads the constant
and nothing about the constant being derivable on a real device. Here the derivation is under test.
"""

import subprocess
from pathlib import Path

from audera.services import platform, system


def test_systemd_is_pid_1():
    """systemd is the container's init, so the seam's calls have an effect.

    Without it, `enable --now` and `disable --now` degrade to argv with no effect and the assertions in
    this directory would still pass, since a stopped unit and an unmanaged one look alike to anything
    that only reads argv.
    """
    assert Path('/proc/1/comm').read_text(encoding='utf-8').strip() == 'systemd'


def test_the_platform_resolves_to_dietpi_without_being_patched():
    """`platform.NAME` is derived from a real `/boot/dietpi/.version`.

    `NAME` is computed at import from `G_DIETPI_VERSION_CORE`, so this also pins that the image's file
    is in the shape `dotenv` can read. Present but unparseable leaves `NAME` at `'linux'` and turns
    every gated call in this directory into a `RuntimeError`.
    """
    assert platform.NAME == 'dietpi'
    assert platform.VERSION.split('.')[0].isdigit()


def test_a_gated_function_runs_instead_of_raising():
    """The passing branch of the gate, driven by the real constant.

    `is-system-running` needs no unit. It exits non-zero for a `degraded` manager, so `check=False`
    keeps the answer readable and the assertion is on the output rather than the status.
    """
    result = system.systemctl('is-system-running', check=False)
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.stdout.strip() in ('running', 'degraded')


def test_the_image_ships_no_audera_unit_files():
    """`/etc/systemd/system/` ships no unit, so provisioning installs everything the lane asserts on.

    `write_streamer_units()` installs every unit the other modules assert on, so a unit baked into the
    image would be one the tests read but provisioning never wrote. The units the device gets from apt
    are in `/usr/lib/systemd/system/`.
    """
    units = sorted(p.name for p in Path('/etc/systemd/system').glob('*.service'))
    assert units == []
