"""Remote audio device setup — shared between player and streamer roles"""

from typing import Literal

from nicegui import app, ui

import audera
from audera.settings import settings
from audera.ui import components
from audera.ui.setup.pages import Page


def run(role: Literal['streamer', 'player'] = 'player') -> None:
    """Runs the device setup wizard for configuration and Wi-Fi onboarding.

    Parameters
    ----------
    role: `Literal['streamer', 'player']`
        The device role, used to customise page labels and finish-page instructions.
    """
    page = Page(role=role)
    page.load()

    components.theme.apply_defaults()

    try:
        ui.run(
            host=settings.server_host,
            port=settings.server_port,
            title=audera.NAME.strip().capitalize(),
            show=False,
            reload=False,
            reconnect_timeout=60,
        )
    except KeyboardInterrupt:
        app.shutdown()
