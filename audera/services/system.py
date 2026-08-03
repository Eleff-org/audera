"""Systemd unit management"""

import subprocess

from audera.services import logging, platform

# Bounds every call. A `systemctl` verb that has not returned in 15 seconds is hung.
TIMEOUT: float = 15

# `CalledProcessError.__str__` carries the argv and the exit status but never `stderr`, so a
# failure's reason is logged here, into the `audera-streamer` journal.
LOGGER = logging.logger(name=__name__)


@platform.requires('dietpi')
def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Runs `systemctl` with `args` and returns the completed process.

    Output is always captured, since `is_active()` reads `stdout`.

    Parameters
    ----------
    *args: `str`
        The `systemctl` arguments, e.g. `'restart', 'snapserver'`.
    check: `bool`
        Whether a non-zero exit status raises `subprocess.CalledProcessError`.
    """
    try:
        return subprocess.run(
            ['systemctl', *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=check,
        )
    except subprocess.CalledProcessError as exc:
        LOGGER.error(f'systemctl {" ".join(args)} failed: {(exc.stderr or "").strip()}')
        raise


@platform.requires('dietpi')
def is_active(unit: str) -> bool:
    """Returns `True` when the systemd unit is active.

    Parameters
    ----------
    unit: `str`
        The systemd unit name, e.g. `'plexamp'`.
    """
    try:
        # `check=False`: `systemctl is-active` exits 3 for an inactive unit, which is an expected
        # outcome here and must not raise.
        result = systemctl('is-active', unit, check=False)
        return result.stdout.strip() == 'active'
    except (subprocess.SubprocessError, OSError):
        return False
