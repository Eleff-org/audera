"""Audera app pages"""

from dotenv import load_dotenv
from nicegui import ui

from audera.ui.streamer.pages import dsp, index
from audera.ui.streamer.pages._clients import _load_settings, _snapserver

load_dotenv()


class Page:
    """A `class` that represents the streamer dashboard app."""

    def __init__(self):
        """Initializes an instance of the streamer dashboard app."""
        self.settings = _load_settings()
        self._client = _snapserver(self.settings)
        self._dialog_open: bool = False

    def load(self) -> None:
        """Registers page routes."""
        ui.page('/')(self.index)
        ui.page('/player/{player_id}/dsp')(self.dsp)

    def index(self) -> None:
        """Renders the main dashboard page."""
        index.render(self)

    def dsp(self, player_id: str) -> None:
        """Renders the full-page parametric-EQ editor for a single player."""
        dsp.render(self, player_id)

    # The refreshable tabs stay `@ui.refreshable` *methods* so each `Page` instance keys
    # its own refresh targets (NiceGUI filters targets by `instance`); their bodies live in
    # `index` and are re-run via `self._build_<name>_tab.refresh()`.
    @ui.refreshable
    def _build_players_tab(self) -> None:
        index.build_players_tab(self)

    @ui.refreshable
    def _build_services_tab(self) -> None:
        index.build_services_tab(self)
