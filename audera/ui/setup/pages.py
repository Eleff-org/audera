"""Remote audio device setup pages"""

import asyncio
import json
import os
import time
from typing import Dict, List, Literal, Optional, Union

from nicegui import app, ui

import audera
from audera.ui import components


class Page:
    """A `class` that represents a device setup app shared between player and streamer roles.

    Parameters
    ----------
    role: `Literal['streamer', 'player']`
        The device role, used to customise page labels and finish-page instructions.
    """

    @audera.platform.requires('dietpi')
    def __init__(
        self,
        role: Literal['streamer', 'player'] = 'player',
    ):
        """Initializes an instance of the device setup app.

        Parameters
        ----------
        role: `Literal['streamer', 'player']`
            The device role, used to customise page labels and finish-page instructions.
        """

        self.role = role

        # Initialize connected network ssid
        self.connected_profile: Union[str, None] = None

        # Initialize available networks
        self.network_refreshing: bool = False
        self.wifi_networks: Dict[str, List[str]] = {}

        # Initialize shutdown state
        self.shutting_down: bool = False

        # Initialize access-point
        self.ap = audera.ap.AccessPoint(name=audera.NAME, url='http://%s-setup.audera.com' % role, interface='wlan0')

        try:
            self.ap.start()
        except RuntimeError:
            raise audera.ap.AccessPointError('Access-point setup is only available on dietpi-os.')

    @property
    def _secured_ssids(self) -> List[str]:
        """The ssids that advertise a security type, so require a password."""
        return [ssid for ssid, security in self.wifi_networks.items() if security]

    async def refresh_callback(self):
        """Refreshes the list of available Wi-Fi networks."""

        # Start
        self.network_refreshing = True

        # Get available networks
        self.wifi_networks = await audera.netifaces.get_wifi_networks(interface='wlan0')

        # Stop
        self.network_refreshing = False
        self._build_selector.refresh()

    def _option_slot(self) -> str:
        """Renders a dropdown row: the ssid, plus a lock icon for a secured network.

        The secured ssids are baked into the Quasar `option` slot as a literal
        array, so the lock is a Material `q-icon` rather than a glyph carried in
        the label. No emoji reaches the UI and the selector's value stays the
        bare ssid, so nothing is stripped before connecting.
        """
        # Single-quote the v-if so the double-quoted json array does not close the
        # attribute; encode any embedded apostrophe as an entity so an ssid like
        # "Bob's" cannot close it either.
        secured = json.dumps(self._secured_ssids).replace("'", '&#39;')
        return (
            '<q-item v-bind="props.itemProps">'
            '<q-item-section><q-item-label>{{ props.opt.label }}</q-item-label></q-item-section>'
            "<q-item-section side v-if='" + secured + ".includes(props.opt.label)'>"
            '<q-icon name="lock" size="18px" />'
            '</q-item-section>'
            '</q-item>'
        )

    @ui.refreshable_method
    def _build_selector(self):
        """Renders the network selector, rebuilt in place when the scan returns.

        The selector is recreated rather than re-optioned because the lock slot
        bakes the current secured set into its template; a fresh build reflects
        the fresh scan without reaching into NiceGUI's option internals.
        """
        self.network_selector = (
            ui.select(options=list(self.wifi_networks.keys()), label='Network')
            .props('clearable outlined dense')
            .classes('w-full')
        )
        self.network_selector.add_slot('option', self._option_slot())

    def _build_network_card(self):
        """Renders the network selector and password input."""

        self._build_selector()
        self.password_input = (
            ui.input(placeholder='Password', password=True, password_toggle_button=True)
            .bind_visibility_from(
                self,
                'network_selector',
                backward=lambda selector: bool(selector and selector.value) and selector.value in self._secured_ssids,
            )
            .props('clearable outlined dense')
            .classes('w-full')
        )

        with ui.row().classes('flex w-full'):
            ui.button(
                'Connect',
                on_click=lambda: self.connect_callback(
                    self.network_selector.value,
                    str(self.password_input.value).strip() if self.password_input.value else None,
                ),
            ).bind_enabled_from(self, 'network_selector', backward=lambda selector: bool(selector and selector.value)).props(
                'rounded'
            ).classes('normal-case')
            ui.spinner(size='md').bind_visibility_from(self, 'network_refreshing')

    async def connect_callback(self, ssid: str, password: Optional[str]):
        """Connects to an available Wi-Fi network and checks for a valid internet connection.

        Parameters
        ----------
        ssid: `str`
            The name of the Wi-Fi network.
        password: `str`
            The password of the Wi-Fi network.
        """

        # Start
        self.network_refreshing = True

        if not self.wifi_networks:
            self.wifi_networks = await audera.netifaces.get_wifi_networks(interface='wlan0')

        if not ssid:
            ui.notify('Select a network.', position='top-right', type='negative')

        elif ssid not in self.wifi_networks:
            ui.notify('Network `%s` is no longer available.' % ssid, position='top-right', type='negative')

        else:
            try:
                # Connect
                await audera.netifaces.connect(
                    ssid=ssid, supported_security_types=self.wifi_networks[ssid], password=password, interface='wlan0'
                )
                self.connected_profile = ssid

                ui.notify('Network `%s` connected successfully.' % ssid, position='top-right', type='positive')

            except RuntimeError:
                ui.notify('Network setup is unavailable.', position='top-right', type='negative')

            except audera.netifaces.NetworkConnectionError as e:
                ui.notify(str(e), position='top-right', type='negative')

            except audera.netifaces.NetworkTimeoutError:
                ui.notify('`%s` is inaccessible.' % ssid, position='top-right', type='negative')

            except audera.netifaces.NetworkNotFoundError:
                ui.notify('`%s` is unavailable.' % ssid, position='top-right', type='negative')

        # Stop
        self.network_refreshing = False

    def _chrome(self, step: Literal['welcome', 'connect', 'finish']) -> None:
        """Renders the branded header and the three-step progress dots.

        Rendering `header.render()` is what pulls the brand stylesheet, font-faces,
        and light palette onto the page via `theme.apply_page()`; without it the
        setup wizard falls back to default Quasar chrome even though `run()` sets
        the color slots.

        Parameters
        ----------
        step: `Literal['welcome', 'connect', 'finish']`
            The active step, rendered as a filled progress dot.
        """
        _labels: Dict[str, str] = {'welcome': 'Welcome', 'connect': 'Connect', 'finish': 'Finish'}
        components.header.render(audera.NAME.capitalize(), subtitle=_labels[step])

        with ui.row().classes('flex w-full'):
            ui.space()
            for name in ('welcome', 'connect', 'finish'):
                ui.icon('circle', size='.7rem', color='primary' if name == step else 'gray-100').classes('self-center')

    def load(self):
        """Returns the page content."""
        ui.page('/', title='%s — Welcome' % audera.NAME.capitalize())(self.welcome)
        ui.page('/connect', title='%s — Connect' % audera.NAME.capitalize())(self.connect)
        ui.page('/finish', title='%s — Finish' % audera.NAME.capitalize())(self.finish)

    def welcome(self):
        """Returns the welcome page content."""

        self._chrome('welcome')

        # Welcome
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('Welcome to **Audera**').classes('text-3xl audera-heading')
            ui.markdown(audera.DESCRIPTION.replace('`', '**'))
            ui.markdown('Click **Start** to set up your %s.' % self.role)

            with ui.row().classes('flex w-full'):
                ui.button('Start', on_click=lambda: ui.navigate.to('/connect')).props('rounded').classes('ml-auto normal-case')

    def connect(self):
        """Returns the connect page content."""

        self._chrome('connect')

        # Connect
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('Connect to Wi-Fi').classes('text-3xl audera-heading')
            ui.markdown('Select the Wi-Fi network you would like to use with your **Audera** %s.' % self.role)
            ui.button('Refresh', on_click=self.refresh_callback).props('rounded').classes('ml-auto normal-case')

            with ui.card().classes('mx-auto flex w-full'):
                self._build_network_card()

            with ui.row().classes('flex w-full'):
                ui.button('Back', on_click=lambda: ui.navigate.to('/')).props('flat rounded').classes('normal-case')
                ui.button('Continue', on_click=lambda: ui.navigate.to('/finish')).bind_enabled_from(
                    self, 'connected_profile', backward=lambda enabled: True if enabled else False
                ).props('rounded').classes('ml-auto normal-case')

        ui.timer(0, self.refresh_callback, once=True)

    def finish(self):
        """Returns the finish page content."""

        _finish_instructions: Dict[str, str] = {
            'player': (
                'Once your player restarts, open [audera.local](http://audera.local) '
                'to manage playback from your **Audera** streamer.'
            ),
            'streamer': (
                'Once your streamer restarts, open [audera.local](http://audera.local) '
                'to manage your players and start a playback session.'
            ),
        }

        self._chrome('finish')

        # Finish
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('Your %s was set up successfully' % self.role).classes('text-3xl audera-heading')
            ui.markdown('Click **Finish** below to start listening.')
            ui.markdown(_finish_instructions[self.role])
            ui.markdown('To learn more about the **Audera** ecosystem, check out the [Github](%s).' % audera.HOME)

            with ui.row().classes('flex w-full'):
                ui.button('Back', on_click=lambda: ui.navigate.to('/connect')).props('flat rounded').classes('normal-case')
                ui.button('Finish', on_click=self.shutdown).bind_enabled_from(
                    self, 'shutting_down', backward=lambda v: not v
                ).props('rounded').classes('ml-auto normal-case')

    async def shutdown(self):
        """Closes the access-point, shuts down the setup app, and restarts the device."""
        self.shutting_down = True
        ui.notify('Restarting your device, please wait…', position='top-right', type='positive')
        await asyncio.sleep(1.5)
        await asyncio.to_thread(self.ap.stop)
        app.shutdown()
        await asyncio.to_thread(time.sleep, 5)
        await asyncio.to_thread(os.system, 'sudo reboot')
