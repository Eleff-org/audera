"""Audera app pages"""

from dotenv import load_dotenv
from nicegui import Client, app, context, ui

from audera.ui.streamer.pages import dsp, index
from audera.ui.streamer.pages._clients import _load_settings

load_dotenv()

_registry: dict[str, 'Page'] = {}


def connected_pages() -> list[tuple[Client, 'Page']]:
    """Returns (client, page) pairs for every connected browser."""
    result = []
    for client_id, page in list(_registry.items()):
        client = Client.instances.get(client_id)
        if client is None or not client.has_socket_connection:
            _registry.pop(client_id, None)
            continue
        result.append((client, page))
    return result


class Page:
    """A `class` that represents the streamer dashboard app.

    One instance per connected client. `@ui.refreshable` keys its render targets on the bound
    instance and on nothing else, so a `Page` shared across clients makes every `refresh()` a
    broadcast that clears every open browser's tab.
    """

    def __init__(self):
        """Initializes an instance of the streamer dashboard app."""
        self.settings = _load_settings()
        self._dialog_open: bool = False
        self._deferred_tabs: set[str] = set()
        # Set while the PlexAmp claim flow is mid-OAuth. A Sources tab refresh deletes the flow's
        # elements and cancels its timers, so a source toggle raised during a claim is refused.
        self._claim_in_flight: bool = False

    def load(self) -> None:
        """Registers page routes, each of which builds its own `Page`."""
        # Reconciles the enabled source set against the streams Snapserver is serving, so an
        # in-place upgrade does not rewrite the conf from a set that contradicts the device.
        # No-ops once a set has been recorded. Here rather than in `__init__` because it is a
        # blocking Snapserver read that belongs to the process, not to a page load.
        index.adopt_running_sources(self)

        ui.page('/')(_index)
        ui.page('/player/{player_id}/dsp')(_dsp)

    async def index(self) -> None:
        """Renders the main dashboard page."""
        await index.render(self)

    async def dsp(self, player_id: str) -> None:
        """Renders the full-page parametric-EQ editor for a single player."""
        await dsp.render(self, player_id)

    # The refreshable tabs stay `@ui.refreshable` *methods* so each `Page` instance keys
    # its own refresh targets (NiceGUI filters targets by `instance`); their bodies live in
    # `index` and are re-run via `self._build_<name>_tab.refresh()`.
    @ui.refreshable
    def _build_players_tab(self) -> None:
        index.build_players_tab(self)

    @ui.refreshable
    def _build_sources_tab(self) -> None:
        index.build_sources_tab(self)

    @ui.refreshable
    def _build_settings_tab(self) -> None:
        index.build_settings_tab(self)


def current() -> Page:
    """Returns the calling client's `Page`.

    Only valid inside a client context. Production code is handed its `page`; this is for a caller
    that has only the client, such as a test asserting on per-client state after a render.
    """
    return app.storage.client['page']


async def _index() -> None:
    """The `/` route. One `Page` per client, published for `current()`."""
    page = Page()
    app.storage.client['page'] = page
    client = context.client
    _registry[client.id] = page
    client.on_disconnect(lambda: _registry.pop(client.id, None))
    await page.index()


async def _dsp(player_id: str) -> None:
    """The `/player/{player_id}/dsp` route. One `Page` per client, published for `current()`."""
    page = Page()
    app.storage.client['page'] = page
    client = context.client
    _registry[client.id] = page
    client.on_disconnect(lambda: _registry.pop(client.id, None))
    await page.dsp(player_id)
