"""Plex-Amp local HTTP API client"""

import xml.etree.ElementTree
from typing import Optional

import httpx

import audera
from audera.models import stream


class PlexAmpClient:
    """A synchronous client for the Plex-Amp local HTTP API.

    Parameters
    ----------
    host: `str`
        The hostname or IP address of the Plex-Amp instance.
    port: `int`
        The HTTP port of Plex-Amp (default 32500).
    """

    def __init__(self, host: str, port: int = audera.PLEXAMP_PORT):
        self.host = host
        self.port = port
        self._base = 'http://%s:%d' % (host, port)

    def get_now_playing(self) -> Optional[stream.Stream]:
        """Returns the currently playing stream via the timeline poll endpoint,
        or `None` if nothing is playing.
        """
        response = httpx.get(
            '%s/player/timeline/poll' % self._base,
            params={'wait': '0', 'commandID': '1', 'includeMetadata': '1'},
            timeout=5,
        )
        response.raise_for_status()
        root = xml.etree.ElementTree.fromstring(response.text)
        tl = root.find('./Timeline[@type="music"]')
        if tl is None or tl.get('state') == 'stopped':
            return None
        # When includeMetadata=1, track attributes are on the first child element
        meta = tl[0] if len(tl) else tl
        title = meta.get('title', '')
        grandparent = meta.get('grandparentTitle', '')
        track_title = '%s — %s' % (grandparent, title) if grandparent else title
        return stream.Stream(
            id=meta.get('ratingKey', ''),
            name=meta.get('parentTitle', track_title),
            uri='',
            status='playing' if tl.get('state') == 'playing' else 'paused',
            current_track=track_title or None,
        )

    def play(self, machine_id: str):
        """Resumes playback on the given Plex player.

        Parameters
        ----------
        machine_id: `str`
            The Plex machine identifier for the player.
        """
        httpx.get(
            '%s/player/playback/play' % self._base,
            params={'commandID': '1', 'machineIdentifier': machine_id},
        ).raise_for_status()

    def pause(self, machine_id: str):
        """Pauses playback on the given Plex player.

        Parameters
        ----------
        machine_id: `str`
            The Plex machine identifier for the player.
        """
        httpx.get(
            '%s/player/playback/pause' % self._base,
            params={'commandID': '1', 'machineIdentifier': machine_id},
        ).raise_for_status()

    def skip(self, machine_id: str):
        """Skips to the next track on the given Plex player.

        Parameters
        ----------
        machine_id: `str`
            The Plex machine identifier for the player.
        """
        httpx.get(
            '%s/player/playback/skipNext' % self._base,
            params={'commandID': '1', 'machineIdentifier': machine_id},
        ).raise_for_status()
