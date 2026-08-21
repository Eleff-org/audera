"""Snapcast JSON-RPC WebSocket client"""

import ipaddress
import json
import time
import uuid
from typing import Any, List, Optional

import websockets.exceptions
import websockets.sync.client

import audera
from audera.errors import ServiceError, Unreachable
from audera.models import player


def _normalize_host_ip(raw: str) -> str:
    try:
        ip = ipaddress.ip_address(raw)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
    except ValueError:
        pass
    return raw


class SnapserverClient:
    """A synchronous client for the Snapcast JSON-RPC 2.0 WebSocket API.

    Parameters
    ----------
    host: `str`
        The hostname or IP address of the Snapcast server.
    port: `int`
        The HTTP port of the Snapcast server (default 1780). JSON-RPC WebSocket
        is served at /jsonrpc on the HTTP server, not the binary TCP control port (1705).
    """

    def __init__(self, host: str, port: int = audera.SNAPSERVER_PORT):
        self.host = host
        self.port = port
        self._url = 'ws://%s:%d/jsonrpc' % (host, port)

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        """Sends a JSON-RPC request and returns the result.

        Parameters
        ----------
        method: `str`
            The JSON-RPC method name.
        params: `dict`, optional
            The method parameters.
        """
        payload: dict[str, Any] = {
            'id': str(uuid.uuid4()),
            'jsonrpc': '2.0',
            'method': method,
        }
        if params:
            payload['params'] = params
        try:
            deadline = time.monotonic() + 30
            with websockets.sync.client.connect(self._url, open_timeout=5) as ws:
                ws.send(json.dumps(payload))
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise Unreachable('Snapserver timeout [%s]: no response within 30s' % method)
                    response = json.loads(ws.recv(timeout=min(10, remaining)))
                    if response.get('id') == payload['id']:
                        break
        except (OSError, TimeoutError, ConnectionError, websockets.exceptions.WebSocketException) as exc:
            raise Unreachable('Snapserver unreachable [%s]: %s' % (method, exc)) from exc
        if 'error' in response:
            raise ServiceError('Snapserver error [%s]: %s' % (method, response['error']))
        return response.get('result', {})

    def get_status(self) -> dict:
        """Returns the full Snapcast server status."""
        return self._call('Server.GetStatus')

    def get_clients(self) -> List[player.Player]:
        """Returns all Snapcast clients as `audera.models.player.Player` objects."""
        status = self.get_status()
        clients = []
        for group in status.get('server', {}).get('groups', []):
            for client in group.get('clients', []):
                # Skip a frame with no `id`; every other field uses `.get(...)` so a partial
                # payload degrades to a defaulted entry instead of a `KeyError`.
                client_id = client.get('id')
                if not client_id:
                    continue
                host = client.get('host', {})
                config = client.get('config', {})
                volume = config.get('volume', {})
                config_name = config.get('name', '').strip()
                host_ip = _normalize_host_ip(host.get('ip', ''))
                clients.append(
                    player.Player(
                        id=client_id,
                        host=host_ip,
                        port=host.get('port', 0),
                        connected=client.get('connected', False),
                        volume=volume.get('percent', 0),
                        muted=volume.get('muted', False),
                        group_id=group.get('id', ''),
                        name=config_name if config_name else host.get('name', host_ip),
                        latency_ms=config.get('latency', 0),
                    )
                )
        return clients

    def get_groups(self) -> List[player.Group]:
        """Returns all Snapcast groups as `audera.models.player.Group` objects."""
        status = self.get_status()
        groups = []
        for group in status.get('server', {}).get('groups', []):
            groups.append(
                player.Group(
                    id=group['id'],
                    name=group.get('name', ''),
                    client_ids=[c['id'] for c in group.get('clients', [])],
                    stream_id=group.get('stream_id', ''),
                    muted=group.get('muted', False),
                    volume=group.get('volume', {}).get('percent', 100),
                )
            )
        return groups

    def get_stream_status(self) -> dict[str, str]:
        """Returns the status of every Snapcast stream, keyed by stream id.

        The status is Snapserver's own value for the stream, one of `'playing'`, `'idle'`, or
        `'disabled'`.
        """
        status = self.get_status()
        stream_status = {}
        for stream in status.get('server', {}).get('streams', []):
            # Skip a stream with no `id`; it can't be keyed. `status` defaults to '' for a partial frame.
            stream_id = stream.get('id')
            if not stream_id:
                continue
            stream_status[stream_id] = stream.get('status', '')
        return stream_status

    def set_client_volume(self, client_id: str, percent: int, muted: bool = False) -> dict:
        """Sets the volume for a Snapcast client.

        Parameters
        ----------
        client_id: `str`
            The Snapcast client identifier.
        percent: `int`
            The volume level (0-100).
        muted: `bool`
            Whether the client is muted.
        """
        return self._call(
            'Client.SetVolume',
            {
                'id': client_id,
                'volume': {'percent': percent, 'muted': muted},
            },
        )

    def set_client_latency(self, client_id: str, latency_ms: int) -> dict:
        """Sets the latency offset for a Snapcast client.

        Parameters
        ----------
        client_id: `str`
            The Snapcast client identifier.
        latency_ms: `int`
            The latency offset in milliseconds (-500 to 500).
        """
        return self._call(
            'Client.SetLatency',
            {'id': client_id, 'latency': latency_ms},
        )

    def set_group_stream(self, group_id: str, stream_id: str) -> dict:
        """Assigns a stream to a Snapcast group.

        Parameters
        ----------
        group_id: `str`
            The Snapcast group identifier.
        stream_id: `str`
            The Snapcast stream identifier.
        """
        return self._call(
            'Group.SetStream',
            {
                'id': group_id,
                'stream_id': stream_id,
            },
        )

    def set_group_mute(self, group_id: str, muted: bool) -> dict:
        """Sets the mute state for a Snapcast group.

        Parameters
        ----------
        group_id: `str`
            The Snapcast group identifier.
        muted: `bool`
            Whether the group should be muted.
        """
        return self._call(
            'Group.SetMute',
            {
                'id': group_id,
                'mute': muted,
            },
        )

    def set_client_name(self, client_id: str, name: str) -> dict:
        """Sets the display name for a Snapcast client.

        Parameters
        ----------
        client_id: `str`
            The Snapcast client identifier.
        name: `str`
            The new display name for the client.
        """
        return self._call(
            'Client.SetName',
            {
                'id': client_id,
                'name': name,
            },
        )
