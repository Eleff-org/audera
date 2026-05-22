"""Audera commands"""

import importlib.resources
import sys

from audera.services import netifaces
from audera.ui import setup, streamer


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
    if not netifaces.connected():
        setup.run(role='player')


def streamer_conf(filename: str, **_) -> None:
    """Prints a bundled streamer config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name within the streamer directory.

    Help
    ----
    usage: audera streamer conf <filename>

    Execute `audera streamer --help` for help.

    Examples
    --------
    ``` console
    audera streamer conf camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    ref = importlib.resources.files('audera').joinpath('conf').joinpath('streamer').joinpath(filename)
    sys.stdout.write(ref.read_text(encoding='utf-8'))


def player_conf(filename: str, **_) -> None:
    """Prints a bundled player config file to stdout.

    Parameters
    ----------
    filename : `str`
        The config file name within the player directory.

    Help
    ----
    usage: audera player conf <filename>

    Execute `audera player --help` for help.

    Examples
    --------
    ``` console
    audera player conf snapclient.conf > /etc/snapclient/snapclient.conf
    ```

    """
    ref = importlib.resources.files('audera').joinpath('conf').joinpath('player').joinpath(filename)
    sys.stdout.write(ref.read_text(encoding='utf-8'))
