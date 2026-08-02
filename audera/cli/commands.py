"""Audera commands"""

import sys
from typing import Literal

from audera.cli import conf
from audera.dal import sources as sources_dal
from audera.domains.sources import source_units
from audera.services import netifaces


def streamer_start(**_) -> None:
    """Starts the audera streamer service, running setup first if not connected to a network.

    Help
    ----
    usage: audera streamer start

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer start
    ```

    """
    # Lazy import so tests can patch audera.ui.streamer.run and audera.ui.setup.run
    # without fighting module-level binding, and to avoid importing heavy UI
    # dependencies when running non-start commands.
    from audera.ui import setup, streamer

    if not netifaces.connected():
        setup.run(role='streamer')

    streamer.run()


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

    if not netifaces.connected():
        setup.run(role='player')


def _emit_conf(filename: str, playback_format: Literal['S16LE', 'S32LE']) -> None:
    """Writes a bundled config file, rendered from `audera.cli.conf`, to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name to render.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).
    """
    if filename == 'camilladsp.yml':
        sys.stdout.write(conf.render_camilladsp(playback_format))
    elif filename == 'snapserver.conf':
        # The recorded enabled set, not `DEFAULT_ENABLED`. `~/.audera/sources.json` survives a
        # reprovision, so rendering the bootstrap default here would ship a conf naming AirPlay to
        # a device whose operator runs PlexAmp: the Sources tab would keep reporting PlexAmp
        # enabled while Snapserver reassigned every group off the stream it no longer serves.
        # `get_enabled()` degrades an unrecorded set to `DEFAULT_ENABLED`, so a fresh flash still
        # renders what it always did.
        sys.stdout.write(conf.render_snapserver(sources_dal.get_enabled()))
    elif filename == 'go-librespot.yml':
        sys.stdout.write(conf.render_go_librespot())
    elif filename == 'asound.conf':
        sys.stdout.write(conf.render_asound())
    else:
        raise SystemExit(f'Unknown config file: {filename!r}')


def streamer_conf(filename: str, playback_format: Literal['S16LE', 'S32LE'] = 'S32LE', **_) -> None:
    """Prints a bundled streamer config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).

    Help
    ----
    usage: audera streamer conf <filename> [--playback-format {S16LE,S32LE}]

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer conf camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    _emit_conf(filename, playback_format)


def streamer_units(disabled: bool = False, **_) -> None:
    """Prints the systemd units of the recorded audio sources to stdout, one per line.

    The complement, `--disabled`, is every other catalogued source's units. Provisioning enables
    one list and disables the other, so between them they leave no catalogued unit in whatever
    state the last image left it.

    Nothing is printed when the selected list is empty, which is what a device running only
    sources whose backend Snapserver forks looks like. The shell loops over the output, so an
    empty list is an empty loop and needs no special case.

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


def player_conf(filename: str, playback_format: Literal['S16LE', 'S32LE'] = 'S32LE', **_) -> None:
    """Prints a bundled player config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name.
    playback_format : `Literal['S16LE', 'S32LE']`
        The CamillaDSP playback device format (only applies to `camilladsp.yml`).

    Help
    ----
    usage: audera player conf <filename> [--playback-format {S16LE,S32LE}]

    Execute `audera player --help` for help.

    Examples
    --------
    ``` console
    audera player conf camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    _emit_conf(filename, playback_format)
