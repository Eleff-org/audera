"""Mock seams for running the local UI apps off-device.

The setup app cannot run off-device as written: `Page.__init__` and the whole
`AccessPoint` are `@platform.requires('dietpi')`, and `get_wifi_networks()`
shells out to `nmcli`. This module stands in for the device so the wizard is
reachable and screenshotable on a dev box.

`apply_seams()` patches four seams before `setup.run()`:

- `platform.NAME = 'dietpi'`, so the `requires('dietpi')` gates pass.
- `AccessPoint.start` / `stop` become no-ops, so no `iw`/`nmcli`/`systemctl`.
- `get_wifi_networks()` returns a canned list, so the selector, the lock icon,
  and the password field all render.
- `connect()` / `shutdown()` notify instead of touching the host, so Continue
  and Finish light up without a reboot.

`loopback_bind()` binds the web UI to loopback:8080 unless the operator has
already overridden the bind through `AUDERA_SERVER_HOST` / `AUDERA_SERVER_PORT`.

The `audera` CLI applies these under its `--mock` flag (or `AUDERA_MOCK`), so
device code carries no dev-only branches. This module ships in the wheel but its
bodies only run under the mock flag.
"""

import os
from typing import Dict, List, Optional

from nicegui import ui

from audera.services import ap, netifaces, platform
from audera.settings import settings
from audera.ui.setup.pages import Page

# A canned network list that exercises every branch of the selector: a secured
# network (renders the lock and the password field), an open one (no field), and
# a duplicate-looking name so the list is not trivially short.
_FAKE_NETWORKS: Dict[str, List[str]] = {
    'Living Room 5G': ['wpa-psk'],
    'Cafe Guest': [],
    'audera-lab': ['wpa-psk'],
}


async def _fake_get_wifi_networks(**_) -> Dict[str, List[str]]:
    """Returns a canned network list in place of the `nmcli` scan."""
    return dict(_FAKE_NETWORKS)


async def _fake_connect(self: Page, ssid: str, password: Optional[str]) -> None:
    """Marks the network connected and notifies, without touching the host."""
    if not ssid:
        ui.notify('Select a network.', position='top-right', type='negative')
        return
    self.connected_profile = ssid
    ui.notify('Network `%s` connected successfully.' % ssid, position='top-right', type='positive')


async def _fake_shutdown(self: Page) -> None:
    """Notifies instead of stopping the access point and rebooting."""
    self.shutting_down = True
    ui.notify('(dev) Device would restart here.', position='top-right', type='positive')


def apply_seams() -> None:
    """Swaps the four dietpi-only seams for dev-box stand-ins.

    `pages.py` reaches these through the same module objects (`audera.platform`,
    `audera.netifaces`, `audera.ap`, and the `Page` class), so rebinding them here
    is enough — no dev-only branch is needed in the device code.
    """
    platform.NAME = 'dietpi'
    ap.AccessPoint.start = lambda self: None
    ap.AccessPoint.stop = lambda self: None
    netifaces.get_wifi_networks = _fake_get_wifi_networks
    Page.connect_callback = _fake_connect  # type: ignore
    Page.shutdown = _fake_shutdown  # type: ignore


def loopback_bind() -> None:
    """Binds the web UI to loopback:8080 unless the operator overrode the bind.

    An explicit `AUDERA_SERVER_HOST` / `AUDERA_SERVER_PORT` still wins, so a
    developer can point the app elsewhere. Mutates the `audera.settings.settings`
    singleton, which both `streamer.run()` and `setup.run()` read at `ui.run()`.
    """
    if 'AUDERA_SERVER_HOST' not in os.environ:
        settings.server_host = '127.0.0.1'
    if 'AUDERA_SERVER_PORT' not in os.environ:
        settings.server_port = 8080
