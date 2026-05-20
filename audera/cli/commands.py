"""Audera commands"""

import importlib.resources
import sys
from typing import Literal

from audera.services import netifaces


def run(type_: Literal['streamer-server', 'player-server', 'player-setup']):
    """Runs an `audera` service.

    Parameters
    ----------
    type_ : `Literal['streamer-server', 'player-server', 'player-setup']`
        The type of `audera` service.

    Help
    ----
    usage: audera run [-h] {streamer-server,player-server,player-setup}

    positional arguments:
    {streamer-server,player-server,player-setup}  The type of `audera` service.

    options:
    -h, --help       show this help message and exit

    Execute `audera run --help` for help.

    Examples
    --------
    ``` console
    audera run streamer-server
    ```

    """
    type_normalized = type_.strip().lower()

    if type_normalized not in ['streamer-server', 'player-server', 'player-setup']:
        raise NotImplementedError

    if type_normalized == 'streamer-server':
        if not netifaces.connected():
            from audera.server import setup

            setup.run(role='streamer')
        from audera.server.streamer import app

        app.run()

    elif type_normalized == 'player-server':
        if not netifaces.connected():
            from audera.server import setup

            setup.run(role='player')

    elif type_normalized == 'player-setup':
        from audera.server import setup

        setup.run(role='player')


def conf(role: Literal['streamer', 'player'], filename: str) -> None:
    """Prints a bundled config file to stdout.

    Parameters
    ----------
    role : `Literal['streamer', 'player']`
        The audera device role.
    filename : `str`
        The config file name within the role directory.

    Help
    ----
    usage: audera conf [-h] {streamer,player} filename

    positional arguments:
    {streamer,player}  The audera device role.
    filename           The config file name.

    options:
    -h, --help       show this help message and exit

    Execute `audera conf --help` for help.

    Examples
    --------
    ``` console
    audera conf streamer camilladsp.yml > /etc/camilladsp/config.yml
    ```

    """
    ref = importlib.resources.files('audera').joinpath('conf').joinpath(role).joinpath(filename)
    sys.stdout.write(ref.read_text(encoding='utf-8'))
