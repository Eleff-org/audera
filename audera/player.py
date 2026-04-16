""" Player service """

import asyncio
import socket
import struct
import time
from zeroconf import Zeroconf

import audera


class Service():
    """ A `class` that represents the `audera` remote audio output player service.

    The player service runs the following tasks within an async event loop,
        - Shairport-sync remote audio output player service for `airplay` connectivity
        - Audera remote audio output player service for `audera` connectivity

    The player service can be run from the command-line,

    ``` bash
    audera run player
    ```

    Or, through a Python session,

    ``` python
    import asyncio
    import audera

    if __name__ == '__main__':
        asyncio.run(audera.player.Service().run())
    ```

    """

    def __init__(self):
        """ Initializes an instance of the `audera` player service. """

        # Logging
        self.logger = audera.logging.get_player_logger()

        # Initialize orchestrator for task isolation
        self.orchestrator = audera.orchestrator.Orchestrator(logger=self.logger)

        # Initialize identity

        # The `update` method will either get the existing identity, create a new identity or
        #   update the existing identity with new network interface settings. Unlike other
        #   `audera` structure objects, where equality is based on every object attribute,
        #   identities are only considered to be the same if they share the same mac address and
        #   ip-address. Finally, the name and uuid of an identity are immutable, when an identity is updated
        #   the same name and uuid are always retained.

        self.mac_address = audera.netifaces.get_local_mac_address()
        self.player_ip_address = audera.netifaces.get_local_ip_address()
        self.identity: audera.models.identity.Identity = audera.dal.identities.update(
            audera.models.identity.Identity(
                name=audera.models.identity.generate_cool_name(),
                uuid=audera.models.identity.generate_uuid_from_mac_address(self.mac_address),
                mac_address=self.mac_address,
                address=self.player_ip_address
            )
        )

        # Initialize player

        # The `update` method will either get the existing player, create a new player or
        #   update an existing player from the identity.

        self.player: audera.models.player.Player = audera.dal.players.update_identity(self.identity)

        # Initialize playback session

        # The player supports only a single active playback session at a time. When a new streamer
        #   connects, the player automatically disconnects and closes the previous playback
        #   session.

        self.playback_session: audera.sessions.Playback = audera.sessions.Playback()

        # Initialize mDNS

        # The player broadcasts the `audera` mDNS service, `raop@{mac_address}._audera._tcp.local`,
        #   over the network. The broadcast properties include all the attributes of the player.

        self.mdns: audera.mdns.PlayerBroadcaster = audera.mdns.PlayerBroadcaster(
            logger=self.logger,
            zc=Zeroconf(),
            player=self.player,
            service_type=audera.MDNS_TYPE,
            service_description=audera.DESCRIPTION,
            service_port=audera.STREAM_PORT
        )

        # Initialize audio stream playback

        # The `get-interface` and `get-device` methods will either get the existing audio
        #   interface / output device or will create a new default audio interface / output device.
        #   The interface describes the parameters of the digital audio stream (format, sampling
        #   frequency, number of channels, and the number of frames for each broadcasted audio
        #   chunk). The device determines which hardware output device is playing the audio
        #   stream. The system default audio output device is automatically selected.

        self.audio_output = audera.devices.Output(
            logger=self.logger,
            interface=audera.dal.interfaces.get_interface(),
            device=audera.dal.devices.get_device('output'),
            buffer_size=audera.BUFFER_SIZE,
            playback_timing_tolerance=audera.PLAYBACK_TIMING_TOLERANCE
        )

        # Initialize time synchronization
        self.rtt: float = 0.0
        self.media_time: float = 0.0

    async def shairport_sync_player(self):
        """ The async `micro-service` for the shairport-sync remote audio output player
        service that supports audio receiving, playback and synchronization from / with
        `airplay` streamers.

        The purpose of the shairport-sync player is to allow for connectivity with the remote
        audio output player via `airplay` streamers as an alternative to the `audera` streamer.

        The player attempts to start the shairport-sync service as an _independent_ task once.
        If the operating system of the player is not compatible or the service fails to start, then
        the task completes without starting the shairport-sync service.

        If the shairport-sync service is started successfully, then the task periodically checks
        the status of the service, restarting the service continuously with `audera.TIME_OUT` until
        the task is either cancelled by the event loop or cancelled manually through
        `KeyboardInterrupt`.
        """

        while True:

            # Check the operating-system
            if audera.platform.NAME not in ['dietpi', 'linux', 'darwin']:

                # Logging
                self.logger.warning(
                    ''.join([
                        'The shairport-sync service is only available',
                        ' on Linux and MacOS.'
                    ])
                )

                # Exit the loop
                break

            # Start the shairport-sync service as a subprocess
            process = await asyncio.create_subprocess_exec(
                "sudo", "systemctl", "start", "shairport-sync",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:

                # Logging
                self.logger.info(
                    'The shairport-sync service started successfully.'
                )

            else:

                # Logging
                self.logger.error(
                    'The shairport-sync service failed to start.'
                )

                if stderr:

                    # Logging
                    self.logger.error(
                        '[%s] [shairport_sync_player()] %s.' % (
                            'CalledProcessError', stderr.decode().strip()
                        )
                    )

                # Exit the loop
                break

            try:

                # Monitor the status of the shairport-sync service subprocess
                while True:

                    status_process = await asyncio.create_subprocess_exec(
                        "systemctl", "is-active", "--quiet", "shairport-sync"
                    )
                    await status_process.wait()

                    if status_process.returncode != 0:

                        # Logging
                        self.logger.info(
                            ''.join([
                                "The shairport-sync service encountered",
                                " an error, retrying in %.2f [sec.]." % (
                                    audera.TIME_OUT
                                )
                            ])
                        )

                    # Wait, yielding to other tasks in the event loop
                    await asyncio.sleep(audera.TIME_OUT)

            except (
                asyncio.CancelledError,  # Player services cancelled
                KeyboardInterrupt  # Player services cancelled manually
            ):

                # Stop the shairport-sync service
                await asyncio.create_subprocess_exec(
                    "sudo", "systemctl", "stop", "shairport-sync"
                )

                # Logging
                self.logger.info(
                    'The shairport-sync service was cancelled.'
                )

                # Exit the loop
                break

    async def audera_player(self):
        """ The async `micro-service` for the audera remote audio output player service that
        supports audio receiving, playback, and synchronization from / with `audera` streamers.

        The player attempts to start the audio streamer synchronization service, audio stream receiver
        service, and playback service as _dependent_ tasks together.

        If all services complete successfully or lose connection to the audio streamer, then the event
        loop periodically attempts to reconnect to the audio streamer, restarting the services continuously
        with `audera.TIME_OUT` until the tasks are either cancelled by the event loop or cancelled
        manually through `KeyboardInterrupt`.
        """

        # Use orchestrator for mDNS broadcaster (I/O operations)
        mdns_broadcaster = asyncio.create_task(
            self.orchestrator.arun(
                "mdns_broadcaster",
                self.mdns_broadcaster,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        # Use orchestrator for timing-critical streamer synchronization
        streamer_synchronizer = asyncio.create_task(
            self.orchestrator.run(
                "streamer_synchronizer",
                self.streamer_synchronizer_sync,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        # Use orchestrator for audio stream receiver (large packet I/O)
        audio_receiver = asyncio.create_task(
            self.orchestrator.run(
                "audio_receiver",
                self.audio_receiver,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        # Use orchestrator for blocking audio playback task
        audio_playback = asyncio.create_task(
            self.orchestrator.run(
                "audio_playback",
                self.audio_playback,
                restart_on_failure=True,
                timeout=None,
                pool_type="thread"
            )
        )

        await asyncio.gather(
            mdns_broadcaster,
            streamer_synchronizer,
            audio_receiver,
            audio_playback
        )

    async def mdns_broadcaster(self):
        """ Multi-cast DNS remote audio output player service broadcaster.

        The purpose of the mDNS broadcaster is to continuously transmit the remote audio output
        player service, including all the attributes of the player.

        The remote audio output player starts the mDNS service as an _independent_ task,
        until the task is either cancelled by the event loop or cancelled manually through
        `KeyboardInterrupt`.
        """

        # Register and broadcast the mDNS service
        try:
            self.mdns.register()

            # Update the mDNS parameters with the latest player attributes continuously
            while True:

                # Get the latest player attributes
                self.player: audera.models.player.Player = audera.dal.players.get_player(self.player.uuid)

                # Update the mDNS service
                self.mdns.update(self.player)

                # Wait, yielding to other tasks in the event loop
                await asyncio.sleep(audera.TIME_OUT)

        except (
            asyncio.CancelledError,  # mDNS-services cancelled
            KeyboardInterrupt,  # mDNS-services cancelled manually
        ):

            # Logging
            self.logger.info(
                'Broadcasting mDNS service {%s} cancelled.' % (
                    audera.MDNS_TYPE
                )
            )

        finally:

            # Close the mDNS service broadcaster
            self.mdns.unregister()

            # Stop all services
            await self.stop_services()

    def streamer_synchronizer_sync(self):
        """ The synchronous server for audio streamer synchronization using UDP-based media time synchronization.

        The purpose of streamer time synchronization is to ensure that the media time on the remote
        audio output player coincides with the audio streamer on the local network by regularly
        receiving sync requests and responding with time offsets.

        The player runs the synchronizer in a loop, handling sync requests from streamers.
        """

        sync = audera.media.Synchronizer(
            logger=self.logger,
            sync_port=audera.PING_PORT,
            timeout=audera.TIME_OUT,
        )

        try:
            while True:
                offset, rtt = sync.sync_player()
                if offset:
                    self.rtt = rtt
                    self.media_time = time.time() + offset
        except Exception as e:
            self.logger.error(
                '[%s] [streamer_synchronizer_sync()] %s.' % (
                    type(e).__name__, str(e)
                )
            )
        finally:
            sync.close()

    def audio_receiver(self):
        """ The synchronous UDP receiver for audio receiving and buffering.

        The player attempts to start the receiver as a _dependent_ task, receiving continuous
        UDP packets from audio streamers forever until the task completes, is cancelled by the event
        loop or is cancelled manually through `KeyboardInterrupt`.

        The audio receiver service depends on the audio streamer synchronizer.
        """

        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', audera.STREAM_PORT))

        try:
            while True:
                data, _ = sock.recvfrom(
                    self.audio_output.interface.chunk *
                    self.audio_output.interface.channels *
                    (self.audio_output.interface.bit_rate // 8) +
                    24  # headers: length(4) + time(8) + terminator(4) + name(6) + escapes(2)
                )

                # Extract timestamp for priority queue
                timestamp = struct.unpack("d", data[4:12])[0]

                # Add audio stream packet to the buffer with timestamp priority
                self.audio_output.buffer.put((timestamp, data))

        except KeyboardInterrupt:
            pass
        finally:
            sock.close()

    def audio_playback(self):
        """ Plays a timestamped audio stream packet from the playback buffer, discarding incomplete
        or late packets.

        The player attempts to start the audio stream playback service as a _dependent_ task, until the
        task completes, is cancelled by the event loop or is cancelled manually through `KeyboardInterrupt`.

        The audio playback service depends on the audio receiver.
        """

        # Logging
        self.logger.info(
            ' '.join([
                "Playing {%s}-bit audio at {%s}" % (
                    self.audio_output.interface.bit_rate,
                    self.audio_output.interface.rate
                ),
                "with {%s} channel(s) through output device {%s (%s)}." % (
                    self.audio_output.interface.channels,
                    self.audio_output.device.name,
                    self.audio_output.device.index
                )
            ])
        )

        # Set the playback state of the remote audio output player
        self.player = audera.dal.players.play(self.player.uuid)

        # Play the audio stream from the playback buffer until audio playback is cancelled
        #   by the event loop or cancelled manually through `KeyboardInterrupt`

        self.audio_output.start()

        # Manage / update the parameters of the digital audio stream
        try:
            while True:

                # The `update` method opens a new audio stream with an updated interface and
                #   device settings and returns `True` when the stream is updated, closing the
                #   previous audio stream. If the interface and device settings are unchanged
                #   then the previous audio stream is retained.

                if self.audio_output.update(
                    interface=audera.dal.interfaces.get_interface(),
                    device=audera.dal.devices.get_device('output')
                ):

                    # Clear the buffer
                    self.audio_output.clear_buffer()

                    # Logging
                    self.logger.info(
                        ' '.join([
                            "Playing {%s}-bit audio at {%s}" % (
                                self.audio_output.interface.bit_rate,
                                self.audio_output.interface.rate
                            ),
                            "with {%s} channel(s) through output device {%s (%s)}." % (
                                self.audio_output.interface.channels,
                                self.audio_output.device.name,
                                self.audio_output.device.index
                            )
                        ])
                    )

                    # Restart the audio stream
                    self.audio_output.start()

                # Yield to other tasks
                time.sleep(audera.TIME_OUT)

        except OSError as e:  # All other streamer communication I / O errors

            # Logging
            self.logger.error(
                '[%s] [audio_playback()] %s.' % (
                    type(e).__name__, str(e)
                )
            )
            self.logger.error(
                    "The audio stream playback encountered an error."
            )

        except KeyboardInterrupt:

            # Logging
            self.logger.info(
                'The audio stream playback was cancelled.'
            )

        finally:

            # Set the playback state of the remote audio output player
            self.player = audera.dal.players.stop(self.player.uuid)

            # Reset the buffer
            self.audio_output.clear_buffer()

            # Close the audio services
            self.audio_output.close()

    async def stop_services(self):
        """ Stops the async tasks. """
        self.orchestrator.shutdown()

    async def start_services(self):
        """ Runs the shairport-sync player service and the `audera` player service with orchestration
        for dynamic control and isolation of blocking operations.
        """

        # Schedule the shairport-sync player service
        # shairport_sync_player = asyncio.create_task(
        #     self.orchestrator.arun(
        #         "shairport_sync_player",
        #         self.shairport_sync_player,
        #         restart_on_failure=True,
        #         timeout=None,
        #         pool_type="thread"
        #     )
        # )

        # Schedule the audera player service (handles its own orchestration internally)
        audera_player = asyncio.create_task(self.audera_player())

        services = [
            # shairport_sync_player,
            audera_player
        ]

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
        """ Starts all async remote audio output player services. """

        # Logging
        for line in audera.LOGO:
            self.logger.message(line)
        self.logger.message('')
        self.logger.message('')
        self.logger.message('>>> Running the player service.')
        self.logger.message('')
        self.logger.message('    Player information')
        self.logger.message('')
        self.logger.message('        name    : %s' % self.player.name)
        self.logger.message('        uuid    : %s' % self.player.uuid)
        self.logger.message('        address : %s' % self.player.address)
        self.logger.message('')

        # Run services
        await self.start_services()
