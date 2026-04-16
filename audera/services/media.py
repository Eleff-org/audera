""" Synchronous UDP-based synchronizer for media time using monotonic clocks """

from typing import Tuple, Optional
import socket
import time
import struct
import logging


class Synchronizer:
    """
    Synchronous UDP-based synchronizer for media time using monotonic clocks.

    Handles time synchronization between streamer and players, calculating time offsets
    and round-trip times (RTT) for precise media playback alignment.
    """

    def __init__(self, logger: logging.Logger, sync_port: int, timeout: float):
        """
        Initialize the synchronizer.

        Args:
            logger: Logger instance for sync events and errors.
            sync_port: UDP port for synchronization.
            timeout: Socket timeout in seconds.
        """
        self.logger = logger
        self.sync_port = sync_port
        self.timeout = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)

    def sync_streamer(self, player_address: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Streamer-side sync: Receive t1 from player, send t2/t3, receive offset/RTT.

        Args:
            player_address: IP address of the player.

        Returns:
            Tuple of (time_offset, rtt) if successful, else (None, None).
        """
        try:
            # Receive t1 from player
            data, addr = self.sock.recvfrom(1024)
            if addr[0] != player_address:
                raise ValueError(f"Request from unexpected address {addr[0]}")
            if len(data) != 8:
                raise ValueError("Invalid t1 packet size")
            t1, = struct.unpack("!d", data)

            # Record t2 and t3
            t2 = time.monotonic()
            t3 = time.monotonic()

            # Send t2 and t3 to player
            packet = struct.pack("!dd", t2, t3)
            self.sock.sendto(packet, (player_address, self.sync_port))

            # Receive offset and rtt from player
            data, addr = self.sock.recvfrom(1024)
            if addr[0] != player_address:
                raise ValueError(f"Response from unexpected address {addr[0]}")
            if len(data) != 16:
                raise ValueError("Invalid offset/rtt packet size")
            offset, rtt = struct.unpack("!dd", data)

            self.logger.info(
                f"Streamer synced with player {player_address}, offset {offset:.7f}, RTT {rtt:.4f}"
            )
            return offset, rtt

        except (socket.timeout, OSError, ValueError) as e:
            self.logger.error(f"Streamer sync failed with {player_address}: {e}")
            return None, None

    def sync_player(self, streamer_address: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Player-side sync: Send t1 to streamer, receive t2/t3, send offset/RTT.

        Args:
            streamer_address: IP address of the streamer.

        Returns:
            Tuple of (time_offset, rtt) if successful, else (None, None).
        """
        try:
            # Bind to sync port
            self.sock.bind(('', self.sync_port))

            # Record t1 and send to streamer
            t1 = time.monotonic()
            packet = struct.pack("!d", t1)
            self.sock.sendto(packet, (streamer_address, self.sync_port))

            # Receive t2 and t3 from streamer
            data, addr = self.sock.recvfrom(1024)
            if addr[0] != streamer_address:
                raise ValueError(f"Response from unexpected address {addr[0]}")
            if len(data) != 16:
                raise ValueError("Invalid t2/t3 packet size")
            t2, t3 = struct.unpack("!dd", data)

            # Record t4
            t4 = time.monotonic()

            # Calculate offset and rtt
            offset = ((t2 - t1) + (t3 - t4)) / 2
            rtt = (t4 - t1) - (t3 - t2)

            # Send offset and rtt to streamer
            packet = struct.pack("!dd", offset, rtt)
            self.sock.sendto(packet, (streamer_address, self.sync_port))

            self.logger.info(
                f"Player synced with streamer {streamer_address}, offset {offset:.7f}, RTT {rtt:.4f}"
            )
            return offset, rtt

        except (socket.timeout, OSError, ValueError) as e:
            self.logger.error(f"Player sync failed with {streamer_address}: {e}")
            return None, None

    def close(self):
        """Close the UDP socket."""
        self.sock.close()
