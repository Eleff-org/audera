"""Audera streamer web UI"""

from nicegui import app, ui

import audera
from audera.ui import components
from audera.ui.streamer.pages import Page


def run() -> None:
    """Runs the streamer dashboard."""
    page = Page()
    page.load()

    components.theme.apply_defaults()

    try:
        ui.run(host='0.0.0.0', port=audera.SERVER_PORT, title=audera.NAME, show=False, reload=False)
    except KeyboardInterrupt:
        app.shutdown()
