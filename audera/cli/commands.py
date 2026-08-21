"""Audera commands"""

import os
import sys
from typing import Literal

from audera.cli import conf
from audera.dal import sources as sources_dal
from audera.domains.sources import source_units
from audera.services import netifaces


def _mock_enabled(flag: bool) -> bool:
    """Returns whether mock mode is on, from the `--mock` flag or `AUDERA_MOCK`.

    The env var lets a whole shell run mock without repeating the flag.
    """
    return flag or os.getenv('AUDERA_MOCK', '').strip().lower() in ('1', 'true', 'yes', 'on')


def streamer_start(mock: bool = False, **_) -> None:
    """Starts the audera streamer service, running setup first if not connected to a network.

    Parameters
    ----------
    mock : `bool`
        Whether to run the web-app against loopback:8080 with the network-setup gate
        skipped, for local development off-device. Also honors `AUDERA_MOCK`.

    Help
    ----
    usage: audera streamer start [--mock]

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer start
    audera streamer start --mock
    ```

    """
    # Lazy import so tests can patch audera.ui.streamer.run and audera.ui.setup.run
    # without fighting module-level binding, and to avoid importing heavy UI
    # dependencies when running non-start commands.
    from audera.ui import streamer

    if _mock_enabled(mock):
        # Lazy import, only under the flag, so a normal start never imports the mock module.
        # The seams are NOT applied: platform.NAME stays the real OS, so a Sources-tab toggle
        # still fails safe on @platform.requires('dietpi') instead of shelling out systemctl.
        # The connected() gate is skipped; the wizard is reached via `streamer setup --mock`.
        from audera.ui.setup import _mock

        _mock.loopback_bind()
        streamer.run()
        return

    from audera.ui import setup

    if not netifaces.connected_with_retry():
        setup.run(role='streamer')

    streamer.run()


def streamer_setup(mock: bool = False, **_) -> None:
    """Runs the Wi-Fi setup wizard, streamer copy.

    Parameters
    ----------
    mock : `bool`
        Whether to apply the dev-box seams and bind loopback:8080, for local development
        off-device. Also honors `AUDERA_MOCK`. Non-mock is a legitimate on-device launch.

    Help
    ----
    usage: audera streamer setup [--mock]

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer setup --mock
    ```

    """
    from audera.ui import setup

    if _mock_enabled(mock):
        from audera.ui.setup import _mock

        _mock.apply_seams()
        _mock.loopback_bind()

    setup.run(role='streamer')


def player_start(**_) -> None:
    """Starts the audera player service, running setup first if not connected to a network.

    Help
    ----
    usage: audera player start

    Execute `audera player --help` for help.

    Examples
    --------
    ``` console
    audera player start
    ```

    """
    # Lazy import so tests can patch audera.ui.setup.run without fighting
    # module-level binding, and to avoid importing heavy UI dependencies when
    # running non-start commands.
    from audera.ui import setup

    if not netifaces.connected_with_retry():
        setup.run(role='player')


def player_setup(mock: bool = False, **_) -> None:
    """Runs the Wi-Fi setup wizard, player copy.

    Parameters
    ----------
    mock : `bool`
        Whether to apply the dev-box seams and bind loopback:8080, for local development
        off-device. Also honors `AUDERA_MOCK`. Non-mock is a legitimate on-device launch.

    Help
    ----
    usage: audera player setup [--mock]

    Execute `audera player --help` for help.

    Examples
    --------
    ``` console
    audera player setup --mock
    ```

    """
    from audera.ui import setup

    if _mock_enabled(mock):
        from audera.ui.setup import _mock

        _mock.apply_seams()
        _mock.loopback_bind()

    setup.run(role='player')


def _emit_conf(filename: str, playback_format: Literal['S16LE', 'S32LE'], playback_device: str = 'hw:0') -> None:
    """Writes a bundled config file, rendered from `audera.cli.conf`, to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name to render.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).
    playback_device : `str`
        The CamillaDSP playback ALSA device (only applies to `camilladsp.yml`).
    """
    if filename == 'camilladsp.yml':
        sys.stdout.write(conf.render_camilladsp(playback_format, playback_device))
    elif filename == 'snapserver.conf':
        # The recorded enabled set, not `DEFAULT_ENABLED`. `~/.audera/sources.json` survives a
        # reprovision, so rendering the bootstrap default would ship a conf naming AirPlay to a
        # device running PlexAmp, and Snapserver would reassign every group off the stream it no
        # longer serves. `get_enabled()` degrades an unrecorded set to `DEFAULT_ENABLED`.
        sys.stdout.write(conf.render_snapserver(sources_dal.get_enabled()))
    elif filename == 'go-librespot.yml':
        sys.stdout.write(conf.render_go_librespot())
    elif filename == 'asound.conf':
        sys.stdout.write(conf.render_asound())
    else:
        raise SystemExit(f'Unknown config file: {filename!r}')


def streamer_conf(
    filename: str, playback_format: Literal['S16LE', 'S32LE'] = 'S32LE', playback_device: str = 'hw:0', **_
) -> None:
    """Prints a bundled streamer config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).
    playback_device : `str`
        The CamillaDSP playback ALSA device (only applies to `camilladsp.yml`).

    Help
    ----
    usage: audera streamer conf <filename> [--playback-format {S16LE,S32LE}] [--playback-device DEVICE]

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer conf camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    _emit_conf(filename, playback_format, playback_device)


def streamer_units(disabled: bool = False, **_) -> None:
    """Prints the systemd units of the recorded audio sources to stdout, one per line.

    The complement, `--disabled`, is every other catalogued source's units. Provisioning enables
    one list and disables the other, so between them no catalogued unit is left in whatever state
    the last image left it.

    Nothing is printed when the selected list is empty, which the shell handles as an empty loop.

    Parameters
    ----------
    disabled : `bool`
        Whether to print the disabled sources' units rather than the enabled sources'.

    Help
    ----
    usage: audera streamer units (--enabled | --disabled)

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    systemctl enable $(audera streamer units --enabled)
    ```

    """
    sys.stdout.writelines(f'{unit}\n' for unit in source_units(sources_dal.get_enabled(), enabled=not disabled))


def player_conf(filename: str, playback_format: Literal['S16LE', 'S32LE'] = 'S32LE', playback_device: str = 'hw:0', **_) -> None:
    """Prints a bundled player config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).
    playback_device : `str`
        The CamillaDSP playback ALSA device (only applies to `camilladsp.yml`).

    Help
    ----
    usage: audera player conf <filename> [--playback-format {S16LE,S32LE}] [--playback-device DEVICE]

    Execute `audera player --help` for help.

    Examples
    --------
    ``` console
    audera player conf camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    _emit_conf(filename, playback_format, playback_device)
