"""Multi-cast DNS management"""

import socket
from typing import Dict, List

from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

import audera
from audera.models.identity import Identity

SERVICE_TYPE: str = '_audera._tcp.local.'

_logger = audera.logging.get_player_logger()


class PlayerBroadcaster:
    """Broadcasts a player as an mDNS service on the local network.

    Parameters
    ----------
    identity: `audera.models.identity.Identity`
        The device identity to broadcast.
    port: `int`
        The port on which the player FastAPI server is listening.
    """

    def __init__(self, identity: Identity, port: int):
        self.identity = identity
        self.port = port

    @property
    def registered_name(self) -> str:
        return '%s.%s' % (self.identity.name, SERVICE_TYPE)

    def _make_info(self) -> ServiceInfo:
        return ServiceInfo(
            type_=SERVICE_TYPE,
            name=self.registered_name,
            addresses=[socket.inet_aton(self.identity.address)],
            port=self.port,
            properties={
                'uuid': self.identity.uuid,
                'name': self.identity.name,
            },
        )

    def _make_async_info(self) -> AsyncServiceInfo:
        return AsyncServiceInfo(
            type_=SERVICE_TYPE,
            name=self.registered_name,
            addresses=[socket.inet_aton(self.identity.address)],
            port=self.port,
            properties={
                'uuid': self.identity.uuid,
                'name': self.identity.name,
            },
        )

    def start(self):
        """Registers the mDNS service (sync, for use outside an event loop)."""
        zc = Zeroconf()
        try:
            zc.register_service(self._make_info())
            _logger.info(
                'mDNS service {%s} registered at {%s:%s}.'
                % (SERVICE_TYPE, self.identity.address, self.port)
            )
        except Exception as e:
            _logger.error(
                '[%s] mDNS service {%s} registration failed. %s.'
                % (type(e).__name__, SERVICE_TYPE, str(e))
            )
        finally:
            self._sync_zc = zc

    def stop(self):
        """Unregisters the mDNS service (sync, for use outside an event loop)."""
        zc = getattr(self, '_sync_zc', None)
        if zc is None:
            return
        try:
            zc.unregister_service(self._make_info())
        except Exception:
            pass
        finally:
            zc.close()
            _logger.info('mDNS service {%s} unregistered.' % SERVICE_TYPE)

    async def async_start(self):
        """Registers the mDNS service (async, for use inside a running event loop)."""
        self._async_zc = AsyncZeroconf()
        try:
            await self._async_zc.async_register_service(self._make_async_info())
            _logger.info(
                'mDNS service {%s} registered at {%s:%s}.'
                % (SERVICE_TYPE, self.identity.address, self.port)
            )
        except Exception as e:
            _logger.error(
                '[%s] mDNS service {%s} registration failed. %s.'
                % (type(e).__name__, SERVICE_TYPE, str(e))
            )

    async def async_stop(self):
        """Unregisters the mDNS service (async, for use inside a running event loop)."""
        zc = getattr(self, '_async_zc', None)
        if zc is None:
            return
        try:
            await zc.async_unregister_service(self._make_async_info())
        except Exception:
            pass
        finally:
            await zc.async_close()
            _logger.info('mDNS service {%s} unregistered.' % SERVICE_TYPE)


class PlayerDiscovery:
    """Discovers player mDNS services on the local network.

    Parameters
    ----------
    time_out: `float`
        How long (in seconds) to wait for initial discovery before returning results.
    """

    def __init__(self, time_out: float = 5.0):
        self.time_out = time_out
        self.players: Dict[str, tuple[str, int]] = {}
        self.zc = Zeroconf()
        self.browser = ServiceBrowser(
            zc=self.zc,
            type_=SERVICE_TYPE,
            handlers=[self.on_service_state_change_callback],
        )

    def on_service_state_change_callback(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: int,
    ):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
                self.players[name] = (ip, info.port)
                _logger.info('Player {%s} discovered at {%s:%s}.' % (name, ip, info.port))

        elif state_change == ServiceStateChange.Removed:
            if name in self.players:
                del self.players[name]
                _logger.info('Player {%s} removed.' % name)

        elif state_change == ServiceStateChange.Updated:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.addresses:
                ip = socket.inet_ntoa(info.addresses[0])
                self.players[name] = (ip, info.port)
                _logger.info('Player {%s} updated at {%s:%s}.' % (name, ip, info.port))

    def get_players(self) -> List[tuple[str, str, int]]:
        """Returns a list of discovered players as `(name, ip, port)` tuples."""
        return [(name.removesuffix('.' + SERVICE_TYPE), ip, port) for name, (ip, port) in self.players.items()]

    def close(self):
        """Closes the service browser and Zeroconf instance."""
        if self.browser:
            self.browser.cancel()
        self.zc.close()
