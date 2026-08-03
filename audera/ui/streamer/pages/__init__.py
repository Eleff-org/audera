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
        # The Players tab's build counter. An `async` `@ui.refreshable` is not re-entrant, so two
        # refreshes in the same tick both clear and then both append, rendering every element twice.
        self._players_generation: int = 0
        # Set while the PlexAmp claim flow is mid-OAuth. A Sources tab refresh deletes the flow's
        # elements and cancels its timers, so a source toggle raised during a claim is refused.
        self._claim_in_flight: bool = False
        # Reconciles the enabled source set against the streams Snapserver is serving, so an
        # in-place upgrade does not rewrite the conf from a set that contradicts the device.
        # No-ops once a set has been recorded.
        index.adopt_running_sources(self)

    def load(self) -> None:
        """Registers page routes."""
        ui.page('/')(self.index)
        ui.page('/player/{player_id}/dsp')(self.dsp)

    async def index(self) -> None:
        """Renders the main dashboard page."""
        await index.render(self)

    def dsp(self, player_id: str) -> None:
        """Renders the full-page parametric-EQ editor for a single player."""
        dsp.render(self, player_id)

    # The refreshable tabs stay `@ui.refreshable` *methods* so each `Page` instance keys
    # its own refresh targets (NiceGUI filters targets by `instance`); their bodies live in
    # `index` and are re-run via `self._build_<name>_tab.refresh()`.
    @ui.refreshable
    async def _build_players_tab(self) -> None:
        await index.build_players_tab(self)

    @ui.refreshable
    def _build_sources_tab(self) -> None:
        index.build_sources_tab(self)
