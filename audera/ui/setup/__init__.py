"""Remote audio device setup — shared between player and streamer roles"""

from typing import Literal

from nicegui import app, ui

import audera
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
        ui.run(host='0.0.0.0', port=80, title=audera.NAME.strip().lower(), show=False, reload=False, reconnect_timeout=60)
    except KeyboardInterrupt:
        app.shutdown()
