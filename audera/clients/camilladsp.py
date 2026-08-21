"""CamillaDSP WebSocket client"""

import json
import math
import time

import websockets.exceptions
import websockets.sync.client

import audera
from audera.errors import ServiceError, Unreachable

_CMD_GET_CONFIG_JSON = 'GetConfigJson'
_CMD_SET_CONFIG_JSON = 'SetConfigJson'
_CMD_VALIDATE_CONFIG = 'ValidateConfig'
_CMD_GET_CLIPPED_SAMPLES = 'GetClippedSamples'
_CMD_RESET_CLIPPED_SAMPLES = 'ResetClippedSamples'


class CamillaDSPClient:
    """A synchronous client for the CamillaDSP WebSocket API.

    Parameters
    ----------
    host: `str`
        The hostname or IP address of the CamillaDSP instance.
    port: `int`
        The WebSocket port of CamillaDSP (default 1234).
    """

    def __init__(self, host: str, port: int = audera.CAMILLADSP_PORT):
        self.host = host
        self.port = port
        self._url = 'ws://%s:%d' % (host, port)

    MIN_DB: float = -50.0
    MAX_DB: float = 0.0
    DEFAULT_PERCENT_VOLUME: int = 25

    def _call(self, command: str, value=None) -> dict:
        """Sends a command to CamillaDSP and returns the response.

        Parameters
        ----------
        command: `str`
            The CamillaDSP command name.
        value: optional
            The command argument, if any.
        """
        payload = {command: value} if value is not None else command
        try:
            # `open_timeout` bounds only the handshake; without a read deadline a peer that never
            # replies blocks `recv()` forever. Cap the exchange like `SnapserverClient._call`.
            deadline = time.monotonic() + 30
            with websockets.sync.client.connect(self._url, open_timeout=5) as ws:
                ws.send(json.dumps(payload))
                remaining = deadline - time.monotonic()
                response = json.loads(ws.recv(timeout=min(10, remaining)))
        except (OSError, TimeoutError, ConnectionError, websockets.exceptions.WebSocketException) as exc:
            raise Unreachable('CamillaDSP unreachable [%s]: %s' % (command, exc)) from exc
        if isinstance(response, dict) and 'Invalid' in response:
            raise ServiceError('CamillaDSP error [%s]: %s' % (command, response['Invalid']))
        inner = response.get(command, response) if isinstance(response, dict) else response
        if isinstance(inner, dict) and inner.get('result') == 'Error':
            raise ServiceError('CamillaDSP error [%s]: %s' % (command, inner))
        return response

    def get_config(self) -> dict:
        """Returns the current CamillaDSP pipeline configuration as a `dict`."""
        response = self._call(_CMD_GET_CONFIG_JSON)
        inner = response.get(_CMD_GET_CONFIG_JSON, response)
        if 'value' in inner:
            return json.loads(inner['value'])
        return inner

    def set_config(self, config: dict):
        """Applies a new CamillaDSP pipeline configuration.

        Parameters
        ----------
        config: `dict`
            The CamillaDSP pipeline configuration.
        """
        # SetConfigJson expects the config as a JSON string, not a dict
        self._call(_CMD_SET_CONFIG_JSON, json.dumps(config))

    def validate_config(self, config: dict) -> None:
        """Validates a CamillaDSP pipeline configuration without applying it.

        Gates every Save: the compiled pipeline is checked by the daemon before it is
        pushed via `set_config`, so an invalid config never reaches the running graph.
        Raises `ServiceError` when the daemon reports any non-`Ok` result.

        Parameters
        ----------
        config: `dict`
            The CamillaDSP pipeline configuration.
        """
        response = self._call(_CMD_VALIDATE_CONFIG, json.dumps(config))
        inner = response.get(_CMD_VALIDATE_CONFIG, response) if isinstance(response, dict) else response

        # `_call` only raises on a literal `result == 'Error'`, but any non-`Ok` result
        #   (e.g. a validation message / ConfigValidationError) means the config is invalid.
        if isinstance(inner, dict) and inner.get('result') != 'Ok':
            raise ServiceError('CamillaDSP validation failed [%s]: %s' % (_CMD_VALIDATE_CONFIG, inner))

    def get_clipped_samples(self) -> int:
        """Returns the number of clipped samples since the last reset."""
        response = self._call(_CMD_GET_CLIPPED_SAMPLES)
        if isinstance(response, dict):
            val = response.get(_CMD_GET_CLIPPED_SAMPLES)
            if isinstance(val, dict):
                val = val.get('value', 0)
            if isinstance(val, (int, float)):
                return int(val)
        return 0

    def reset_clipped_samples(self) -> None:
        """Zeroes the daemon's clipped-samples counter."""
        self._call(_CMD_RESET_CLIPPED_SAMPLES)

    def get_volume(self) -> float:
        """Returns the current CamillaDSP volume level in dB."""
        response = self._call('GetVolume')
        if isinstance(response, dict):
            val = response.get('GetVolume')
            if isinstance(val, dict):
                val = val.get('value', 0.0)
            if isinstance(val, (int, float)):
                return float(val)
            return 0.0
        return 0.0

    def set_volume(self, level: float):
        """Sets the CamillaDSP volume level.

        Parameters
        ----------
        level: `float`
            The volume level in dB.
        """
        self._call('SetVolume', level)

    def percent_to_db(self, percent: float) -> float:
        """Converts volume percent (0-100) to dB (MIN_DB to MAX_DB).

        Volume is attenuation-only: 0% maps to MIN_DB (-50.0) and 100% maps to MAX_DB
        (0.0, unity gain) — there is no path to a gain above 0 dB.
        """
        if percent <= 0:
            return self.MIN_DB
        db = 20.0 * math.log10(percent / 100.0)
        return max(self.MIN_DB, min(self.MAX_DB, db))

    def db_to_percent(self, db: float) -> float:
        """Converts dB to a precise percent (0.0-100.0) for persistence/display."""
        if not isinstance(db, (int, float)):
            db = 0.0
        if db <= self.MIN_DB:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (10.0 ** (db / 20.0))))

    def set_percent_volume(self, percent: float) -> None:
        """Convenience method to set volume from a 0-100 percent value."""
        self.set_volume(self.percent_to_db(percent))

    def get_percent_volume(self) -> int:
        """Returns current volume as percent (0-100) by querying CamillaDSP."""
        db = self.get_volume()
        return int(round(self.db_to_percent(db)))
