""" Streamer service """

from typing import Optional
import asyncio
import socket
import time
import struct
from zeroconf import Zeroconf
# import statistics

import audera


class Service():
    """ A `class` that represents the `audera` streamer service.

    The streamer service runs the following tasks within an async event loop,
        - UDP-based media time synchronization
        - Remote audio output player mDNS browsing with player connection, playback session management
            and multi-player synchronization.
        - Audio stream capturing and broadcasting

    The streamer service can be run from the command-line,

    ``` bash
    audera run streamer
    ```

    Or, through a Python session,

    ``` python
    import asyncio
    import audera

    if __name__ == '__main__':
        asyncio.run(audera.streamer.Service().run())
    ```

    """

    def __init__(self):
        """ Initializes an instance of the `audera` streamer service. """

        # Logging
        self.logger = audera.logging.get_streamer_logger()

        # Initialize orchestrator for task isolation
        self.orchestrator = audera.orchestrator.Orchestrator(logger=self.logger)

        # Initialize identity

        # The `update` method will either get the existing identity, create a new identity or
        #   update the existing identity with new network interface settings. Unlike other
        #   `audera` structure objects, where equality is based on every object attribute,
        #   identities are only considered to be the same if they share the same uuid and
        #   mac address. Finally, the name of an identity is immutable, when an identity is updated
        #   the same name is always retained.

        self.mac_address = audera.netifaces.get_local_mac_address()
        self.streamer_ip_address = audera.netifaces.get_local_ip_address()
        self.identity: audera.models.identity.Identity = audera.dal.identities.update(
            audera.models.identity.Identity(
                name=audera.models.identity.generate_cool_name(),
                uuid=audera.models.identity.generate_uuid_from_mac_address(self.mac_address),
                mac_address=self.mac_address,
                address=self.streamer_ip_address
            )
        )

        # Initialize stream session

        # The `update` method will either get the existing session, create a new session or
        #   update the existing session with new players. If a session already exists then the
        #   same session volume will be retained. Currently, any / all available players are
        #   automatically attached to the current playback session. An available player is any
        #   player that is both enabled and connected to the local network.

        self.stream_session: audera.sessions.Stream = audera.sessions.Stream(
            session=audera.dal.sessions.update(
                audera.models.session.Session(
                    uuid=self.identity.uuid,
                    mac_address=self.identity.mac_address,
                    address=self.identity.address,
                    players=[],
                    provider='audera'
                )
            )
        )

        # Initialize mDNS

        # The streamer browses the network for remote audio output players that are broadcasting
        #   the `audera` mDNS service, `raop@{mac_address}._audera._tcp.local`. The browser
        #   automatically attaches players to the current session when they connect, removes
        #   players when they disconnect, and updates players when any of the mDNS service
        #   properties change.

        self.mdns: audera.mdns.PlayerBrowser = audera.mdns.PlayerBrowser(
            logger=self.logger,
            zc=Zeroconf(),
            type_=audera.MDNS_TYPE,
            time_out=audera.TIME_OUT
        )

        # Initialize audio stream

        # The `get-interface` and `get-device` methods will either get the existing audio
        #   interface / input-device or will create a new default audio interface / input-device.
        #   The interface describes the parameters of the digital audio stream (format, sampling
        #   frequency, number of channels, and the number of frames for each broadcasted audio
        #   chunk). The device determines which hardware input device is supplying the audio
        #   stream. The system default audio input device is automatically selected.

        self.audio_input = audera.devices.Input(
            logger=self.logger,
            interface=audera.dal.interfaces.get_interface(),
            device=audera.dal.devices.get_device('input'),
            playback_delay=audera.PLAYBACK_DELAY
        )
        self.last_audio_capture_time: Optional[float] = None

        # Initialize playback delay and rtt-history
        self.rtt_history: list[float] = []

    def get_streamer_time(self) -> float:
        """ Returns the monotonic time on the streamer. """
        return time.monotonic()

    def get_playback_time(self) -> float:
        """ Returns the playback time based on the current time, playback delay, the
        monotonic time and the last audio capture time.
        """
        playback_time = self.get_streamer_time() + self.audio_input.playback_delay

        # Set the last audio capture time to the current playback time for the first chunk in
        #   the audio capture stream. Otherwise, extend the last audio capture time by the chunk
        #   duration for all following chunks in the audio capture stream.

        if not self.last_audio_capture_time:
            self.last_audio_capture_time = playback_time
        else:
            self.last_audio_capture_time += self.audio_input.chunk_duration

        return self.last_audio_capture_time

    async def mdns_browser(self):
        """ The async `micro-service` for the multi-cast DNS remote audio output player service
        browser.

        The purpose of the mDNS browser is to automatically connect, disconnect, update and synchronize
        any / all remote audio output players.

        The streamer starts the mDNS service as an _independent_ task, until the task is either
        cancelled by the event loop or cancelled manually through `KeyboardInterrupt`.
        """

        # Browse for remote audio output players broadcasting the mDNS service
        try:
            self.mdns.browse()

            # Update the playback session, opening connections to all remote audio
            #   output players attached to the session continuously

            while True:

                if self.mdns.players:

                    # Synchronize all remote audio output players attached to the stream
                    #   session and open stream connections to all remote audio output players
                    #   concurrently

                    await self.synchronize()

                else:
                    self.mdns.refresh()

                    # Logging
                    self.logger.info(
                        ''.join([
                            "Waiting for remote audio output players to connect,",
                            " retrying in %.2f [sec.]." % (audera.TIME_OUT)
                        ])
                    )

                # Wait, yielding to other tasks in the event loop
                await asyncio.sleep(audera.TIME_OUT)

        except (
            asyncio.CancelledError,  # mDNS-services cancelled
            KeyboardInterrupt,  # mDNS-services cancelled manually
        ):

            # Logging
            self.logger.info(
                'Browsing for mDNS service {%s} cancelled.' % (
                    audera.MDNS_TYPE
                )
            )

        finally:

            # Close the mDNS service browser
            self.mdns.close()

            # Close the stream session
            await self.stream_session.close()

            # Stop all services
            await self.stop_services()

    async def synchronize(self):
        """ Synchronizes any / all connected remote audio output players . """

        try:

            # Retain the current connected remote audio output players for broadcasting
            players = audera.dal.players.get_all_available_players()

            # Synchronize the players
            for player in players:
                sync = audera.media.Synchronizer(
                    logger=self.logger,
                    sync_port=audera.PING_PORT,
                    timeout=audera.TIME_OUT,
                )
                offset, rtt = sync.sync_streamer(player.address)
                sync.close()

                if offset:
                    # Synchronization successful, attach the player
                    player = audera.dal.players.play(player.uuid)
                    self.stream_session.attach_player(player=player)
                    # Logging
                    self.logger.info(
                        'Remote audio output player {%s (%s)} attached.' % (
                            player.name,
                            player.short_uuid
                        )
                    )
                else:
                    # Synchronization failed, detach the player
                    await self.stream_session.detach_player(player)

                    # Logging
                    self.logger.info(
                        'Remote audio output player {%s (%s)} detached.' % (
                            player.name,
                            player.short_uuid
                        )
                    )

        except OSError as e:  # All other streamer communication I / O errors

            # Logging
            self.logger.error(
                '[%s] [multi_player_synchronizer()] %s.' % (
                    type(e).__name__, str(e)
                )
            )
            self.logger.error(
                ''.join([
                    "Multi-player synchronization encountered",
                    " an error, retrying in %.2f [sec.]." % (
                        audera.TIME_OUT
                    )
                ])
            )

    def audio_streamer(self):
        """ The async audio stream `micro-service` for audio capturing and broadcasting. The
        streamer captures audio data from the hardware audio input-device and broadcasts the audio
        stream to all connected remote audio output players as timestamped packets concurrently.

        The streamer attempts to start the stream service as an _dependent_ task, restarting the
        service forever with `audera.TIME_OUT` until the task is either cancelled by the event
        loop or cancelled manually through `KeyboardInterrupt`.

        The audio stream service depends on the mDNS browser.
        """

        # Logging
        self.logger.info(
            ' '.join([
                "Streaming {%s}-bit audio at {%s}" % (
                    self.audio_input.interface.bit_rate,
                    self.audio_input.interface.rate
                ),
                "with {%s} channel(s) from input device {%s (%s)}." % (
                    self.audio_input.interface.channels,
                    self.audio_input.device.name,
                    self.audio_input.device.index
                )
            ])
        )

        # Retain the current number of connected remote audio output players, if a new player
        #   is attached then time-out to allow for the remote audio output player
        #   buffers to empty to resynchronize audio.

        previous_num_players = 0

        # Create UDP socket for broadcasting
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Serve the audio stream until the mDNS browser is cancelled by the event loop or
        #   cancelled manually through `KeyboardInterrupt`

        try:
            while True:

                # Manage / update the parameters of the digital audio stream

                # The `update` method opens a new audio stream with an updated interface and
                #   device settings and returns `True` when the stream is updated, closing the
                #   previous audio stream. If the interface and device settings are unchanged
                #   then the previous audio stream is retained.

                if self.audio_input.update(
                    interface=audera.dal.interfaces.get_interface(),
                    device=audera.dal.devices.get_device('input')
                ):

                    # Logging
                    self.logger.info(
                        ''.join([
                            "Streaming {%s}-bit audio at {%s}" % (
                                self.audio_input.interface.bit_rate,
                                self.audio_input.interface.rate
                            ),
                            " with {%s} channel(s) from input device {%s (%s)}." % (
                                self.audio_input.interface.channels,
                                self.audio_input.device.name,
                                self.audio_input.device.index
                            ),
                            " Restarting the audio stream in %.2f [sec.]..." % (
                                audera.TIME_OUT
                            )
                        ])
                    )

                    # Timeout to allow for the remote audio output player buffers to empty
                    #   when a new audio stream is opened.

                    time.sleep(audera.TIME_OUT)

                    # Reset the last audio capture time
                    self.last_audio_capture_time = None

                # Retain the current available remote audio output players for broadcasting
                players = audera.dal.players.get_all_available_players()

                # Timeout to allow for the remote audio output player buffers to empty
                #   when a new player is attached since the previous broadcast. By allowing
                #   the buffers to empty, no player will try to play pre-buffered audio out of
                #   sync with the other players.

                if len(players) > previous_num_players:

                    # Logging
                    self.logger.info(
                        ''.join([
                            "Allowing remote audio output player buffers to drain.",
                            " Restarting the audio stream in %.2f [sec.]..." % (
                                audera.TIME_OUT
                            )
                        ])
                    )

                    time.sleep(audera.TIME_OUT)

                    # Reset the last audio capture time
                    self.last_audio_capture_time = None

                # Update the number of remote audio output players
                previous_num_players = len(players)

                # Read the next audio data chunk from the audio stream
                chunk = self.audio_input.stream.read(
                    self.audio_input.interface.chunk,
                    exception_on_overflow=False
                )

                # Get playback time
                playback_time = self.get_playback_time()

                # Debug
                # self.logger.info(
                #     'Capturing audio stream packet with playback time %.7f [sec.].' % (
                #         playback_time
                #     )
                # )

                # Convert the audio data chunk to a timestamped packet, including the length of
                #   the packet as well as the packet terminator. Assign the timestamp as the target
                #   playback time accounting for a fixed playback delay from the current time on
                #   the streamer.

                length = struct.pack(">I", len(chunk))
                playback_time = struct.pack(
                    "d",
                    playback_time
                )
                packet = (
                    length  # 4 bytes
                    + playback_time  # 8 bytes
                    + chunk
                    + audera.PACKET_TERMINATOR  # 4 bytes
                    + audera.NAME.encode()  # 6 bytes
                    + audera.PACKET_ESCAPE  # 1 byte
                    + audera.PACKET_ESCAPE  # 1 byte
                )

                # Broadcast the packet to the players
                for player in players:
                    try:
                        sock.sendto(packet, (player.address, audera.STREAM_PORT))
                    except OSError as e:
                        # Log send failure
                        self.logger.error(
                            'Failed to send audio packet to player {%s (%s)}: %s' % (
                                player.name,
                                player.short_uuid,
                                str(e)
                            )
                        )

        except OSError as e:  # All other streamer communication I / O errors

            # Logging
            self.logger.error(
                '[%s] [audio_streamer()] %s.' % (
                    type(e).__name__, str(e)
                )
            )
            self.logger.error(
                    "The audio stream capture encountered an error."
            )

        except KeyboardInterrupt:  # Streamer services cancelled manually

            # Logging
            self.logger.info(
                'The audio stream capture was cancelled.'
            )

        finally:

            # Close the audio stream
            self.audio_input.stream.stop_stream()
            self.audio_input.stream.close()
            self.audio_input.port.terminate()

            # Close the UDP socket
            sock.close()

    async def stop_services(self):
        """ Stops the async tasks. """
        self.orchestrator.shutdown()

    async def start_services(self):
        """ Runs the async mDNS browser service, time-synchronization service, multi-player
        synchronization service, and the audio stream service using the orchestrator for isolation.
        """

        # Schedule the mDNS browser service in isolated thread pool
        mdns_browser = asyncio.create_task(
            self.orchestrator.arun(
                "mdns_browser",
                self.mdns_browser,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        # Schedule the audio streamer in isolated thread pool
        audio_streamer = asyncio.create_task(
            self.orchestrator.run(
                "audio_streamer",
                self.audio_streamer,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        services = [mdns_browser, audio_streamer]

        # Run services
        try:
            while services:
                done, services = await asyncio.wait(
                    services,
                    return_when=asyncio.FIRST_COMPLETED
                )

                done: set[asyncio.Task]
                services: set[asyncio.Task]

                for service in done:
                    if service.exception():

                        # Logging
                        self.logger.error(
                            '[%s] [%s()] %s.' % (
                                type(service.exception()).__name__,
                                service.get_coro().__name__,
                                service.exception()
                            )
                        )

        # Wait for services to complete
        finally:
            await asyncio.gather(
                *services,
                return_exceptions=True
            )

    async def run(self):
        """ Starts all async streamer services. """

        # Logging
        for line in audera.LOGO:
            self.logger.message(line)
        self.logger.message('')
        self.logger.message('')
        self.logger.message('>>> Running the streamer service.')
        self.logger.message('')
        self.logger.message('    Streamer information')
        self.logger.message('')
        self.logger.message('        name    : %s' % self.identity.name)
        self.logger.message('        uuid    : %s' % self.identity.uuid)
        self.logger.message('        address : %s' % self.identity.address)
        self.logger.message('')

        # Start services
        await self.start_services()
