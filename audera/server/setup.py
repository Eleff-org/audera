"""Remote audio device setup — shared between player and streamer roles"""

import os
import time
from typing import Dict, List, Literal, Optional, Union

from nicegui import app, ui

import audera


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

        # Initialize access-point
        self.ap = audera.ap.AccessPoint(name=audera.NAME, url='http://%s-setup.audera.com' % role, interface='wlan0')

        try:
            self.ap.start()
        except RuntimeError:
            raise audera.ap.AccessPointError('Access-point setup is only available on dietpi-os.')

    @property
    def available_networks(self):
        return [f'{key} 🔒' if value else key for key, value in self.wifi_networks.items()]

    async def refresh_callback(self):
        """Refreshes the list of available Wi-Fi networks."""

        # Start
        self.network_refreshing = True

        # Get available networks
        self.wifi_networks = await audera.netifaces.get_wifi_networks(interface='wlan0')

        # Stop
        self.network_refreshing = False

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

    def load(self):
        """Returns the page content."""
        ui.page('/', title='%s \u2014 Welcome' % audera.NAME.lower())(self.welcome)
        ui.page('/connect', title='%s \u2014 Connect' % audera.NAME.lower())(self.connect)
        ui.page('/finish', title='%s \u2014 Finish' % audera.NAME.lower())(self.finish)

    def welcome(self):
        """Returns the welcome page content."""

        with ui.row().classes('flex w-full'):
            ui.label('%s \u2014 Welcome' % audera.NAME.lower()).classes('self-center text-sm ml-3')
            ui.icon('circle', size='.7rem', color='primary').classes('self-center ml-auto')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center mr-3')

        # Welcome
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('Welcome to **audera** 👋').classes('text-3xl')
            ui.markdown(audera.DESCRIPTION.replace('`', '**'))
            ui.markdown('Click **Start** to set up your %s.' % self.role)

            with ui.row().classes('flex w-full'):
                ui.button('Start', on_click=lambda: ui.navigate.to('/connect')).props('rounded').classes('ml-auto normal-case')

    def connect(self):
        """Returns the connect page content."""

        with ui.row().classes('flex w-full'):
            ui.label('%s \u2014 Connect' % audera.NAME.lower()).classes('self-center text-sm ml-3')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center ml-auto')
            ui.icon('circle', size='.7rem', color='primary').classes('self-center')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center mr-3')

        # Connect
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('Connect to Wi-Fi').classes('text-3xl')
            ui.markdown('Select the Wi-Fi network you would like to use with your **audera** %s.' % self.role)
            ui.button('Refresh', on_click=self.refresh_callback).props('rounded').classes('ml-auto normal-case')

            with ui.card().classes('mx-auto flex w-full'):
                self.network_selector = (
                    ui.select(
                        options=self.available_networks,
                        label='Network',
                    )
                    .props('clearable rounded-md outlined dense')
                    .classes('w-full')
                )
                self.password_input = (
                    ui.input(placeholder='Password', password=True, password_toggle_button=True)
                    .bind_visibility_from(
                        self,
                        'network_selector',
                        backward=lambda network_selector: network_selector.value and '🔒' in network_selector.value,
                    )
                    .props('clearable rounded-md outlined dense')
                    .classes('w-full')
                )

                with ui.row().classes('flex w-full'):
                    ui.button(
                        'Connect',
                        on_click=lambda: self.connect_callback(
                            str(self.network_selector.value).replace('🔒', '').strip(),
                            str(self.password_input.value).strip() if self.password_input.value else None,
                        ),
                    ).bind_enabled_from(
                        self, 'network_selector', backward=lambda network_selector: network_selector.value
                    ).props('rounded').classes('normal-case')
                    ui.spinner(size='md').bind_visibility_from(self, 'network_refreshing')

            with ui.row().classes('flex w-full'):
                ui.button('Back', on_click=lambda: ui.navigate.to('/')).props('flat rounded').classes('normal-case')
                ui.button('Continue', on_click=lambda: ui.navigate.to('/finish')).bind_enabled_from(
                    self, 'connected_profile', backward=lambda enabled: True if enabled else False
                ).props('rounded').classes('ml-auto normal-case')

    def finish(self):
        """Returns the finish page content."""

        _finish_instructions: Dict[str, str] = {
            'player': (
                'Once your player restarts, connect to your **audera** streamer to start a playback session, or, '
                'cast directly to your player through any AirPlay enabled device.'
            ),
            'streamer': ('Once your streamer restarts, connect your **audera** players to start a playback session.'),
        }

        with ui.row().classes('flex w-full'):
            ui.label('%s \u2014 Finish' % audera.NAME.lower()).classes('self-center text-sm ml-3')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center ml-auto')
            ui.icon('circle', size='.7rem', color='gray-100').classes('self-center')
            ui.icon('circle', size='.7rem', color='primary').classes('self-center mr-3')

        # Finish
        with ui.card().classes('mx-auto flex w-full'):
            ui.markdown('🎉 Your %s was set up successfully' % self.role).classes('text-3xl')
            ui.markdown('Click **Finish** below to start listening.')
            ui.markdown(_finish_instructions[self.role])
            ui.markdown('To learn more about the **audera** ecosystem, check out the [Github](%s).' % audera.HOME)

            with ui.row().classes('flex w-full'):
                ui.button('Back', on_click=lambda: ui.navigate.to('/connect')).props('flat rounded').classes('normal-case')
                ui.button('Finish', on_click=self.shutdown).props('rounded').classes('ml-auto normal-case')

    def shutdown(self):
        """Closes the access-point, shuts down the setup app, and restarts the device."""
        self.ap.stop()
        app.shutdown()

        # Restart
        time.sleep(5)
        os.system('sudo reboot')


def run(role: Literal['streamer', 'player'] = 'player'):
    """Runs the device setup wizard for configuration and Wi-Fi onboarding.

    Parameters
    ----------
    role: `Literal['streamer', 'player']`
        The device role, used to customise page labels and finish-page instructions.
    """

    # Initialize the ui
    page = Page(role=role)

    # Load the page content
    page.load()

    # Run the app
    try:
        ui.run(
            host='0.0.0.0',  # Any interface
            port=80,
            title=audera.NAME.strip().lower(),
            show=False,
            reload=False,
            reconnect_timeout=60,
        )
    except KeyboardInterrupt:
        app.shutdown()


if __name__ in ['__main__', '__mp_main__']:
    run()
