""" CamillaDSP WebSocket client """

import json

import websockets.sync.client


class CamillaDSPClient():
    """ A synchronous client for the CamillaDSP WebSocket API.

    Parameters
    ----------
    host: `str`
        The hostname or IP address of the CamillaDSP instance.
    port: `int`
        The WebSocket port of CamillaDSP (default 1234).
    """

    def __init__(self, host: str, port: int = 1234):
        self.host = host
        self.port = port
        self._url = 'ws://%s:%d' % (host, port)

    def _call(self, command: str, value=None) -> dict:
        """ Sends a command to CamillaDSP and returns the response.

        Parameters
        ----------
        command: `str`
            The CamillaDSP command name.
        value: optional
            The command argument, if any.
        """
        payload = {command: value} if value is not None else command
        with websockets.sync.client.connect(self._url) as ws:
            ws.send(json.dumps(payload))
            response = json.loads(ws.recv())
        if isinstance(response, dict) and response.get('result') == 'Error':
            raise RuntimeError('CamillaDSP error [%s]: %s' % (command, response))
        return response

    def get_config(self) -> dict:
        """ Returns the current CamillaDSP pipeline configuration as a `dict`. """
        response = self._call('GetConfig')
        if isinstance(response, dict):
            return response.get('GetConfig', response)
        return {}

    def set_config(self, config: dict):
        """ Applies a new CamillaDSP pipeline configuration.

        Parameters
        ----------
        config: `dict`
            The CamillaDSP pipeline configuration.
        """
        self._call('SetConfig', config)

    def get_volume(self) -> float:
        """ Returns the current CamillaDSP volume level in dB. """
        response = self._call('GetVolume')
        if isinstance(response, dict):
            return response.get('GetVolume', 0.0)
        return 0.0

    def set_volume(self, level: float):
        """ Sets the CamillaDSP volume level.

        Parameters
        ----------
        level: `float`
            The volume level in dB.
        """
        self._call('SetVolume', level)
