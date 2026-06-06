"""CamillaDSP WebSocket client"""

import json
import math

import websockets.sync.client

import audera


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

    MAX_SAFE_DB: float = -3.0

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
        with websockets.sync.client.connect(self._url, open_timeout=5) as ws:
            ws.send(json.dumps(payload))
            response = json.loads(ws.recv())
        if isinstance(response, dict) and response.get('result') == 'Error':
            raise RuntimeError('CamillaDSP error [%s]: %s' % (command, response))
        return response

    def get_config(self) -> dict:
        """Returns the current CamillaDSP pipeline configuration as a `dict` (or the raw value)."""
        response = self._call('GetConfig')
        if isinstance(response, dict):
            inner = response.get('GetConfig', response)
            if isinstance(inner, dict) and 'value' in inner:
                return inner['value']
            return inner
        return {}

    def set_config(self, config: dict):
        """Applies a new CamillaDSP pipeline configuration.

        Parameters
        ----------
        config: `dict`
            The CamillaDSP pipeline configuration.
        """
        self._call('SetConfig', config)

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

    def percent_to_db(self, percent: int) -> float:
        """Converts volume percent (0-100) to dB, clamped to MAX_SAFE_DB.

        At 0% returns -90.0 rather than -inf to avoid undefined dB behaviour.
        """
        if percent <= 0:
            return -90.0
        db = 20.0 * math.log10(percent / 100.0)
        # dB is a negative scale: louder = less negative, so min() clamps at MAX_SAFE_DB.
        return min(db, self.MAX_SAFE_DB)

    def db_to_percent(self, db: float) -> int:
        """Converts dB back to percent (0-100) for UI display."""
        if not isinstance(db, (int, float)):
            db = 0.0
        if db <= -90.0:
            return 0
        percent = int(100.0 * (10.0 ** (db / 20.0)))
        return max(0, min(100, percent))

    def set_percent_volume(self, percent: int) -> None:
        """Convenience method to set volume from a 0-100 percent value."""
        self.set_volume(self.percent_to_db(percent))

    def get_percent_volume(self) -> int:
        """Returns current volume as percent (0-100) by querying CamillaDSP."""
        db = self.get_volume()
        return self.db_to_percent(db)
