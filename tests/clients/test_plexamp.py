import re
import xml.etree.ElementTree
from pathlib import Path

import respx
from httpx import Response

from audera.clients import PlexAmpClient
from audera.models.stream import Stream

_BASE = 'http://127.0.0.1:32500'
_CLIENT = PlexAmpClient('127.0.0.1', 32500)

_FIXTURES = Path(__file__).parent.parent / 'fixtures' / 'plexamp'

_TIMELINE_ACTIVE = (_FIXTURES / 'timeline_active.xml').read_text()
_TIMELINE_IDLE = (_FIXTURES / 'timeline_idle.xml').read_text()


@respx.mock
def test_get_now_playing_active():
    respx.get(re.compile(r'.*/player/timeline/poll.*')).mock(return_value=Response(200, text=_TIMELINE_ACTIVE))
    # Derive expectations from the fixture so a regenerated `timeline_active.xml` (see
    # tests/fixtures/plexamp/README.md) doesn't require hand-editing pinned literals; the
    # assertions still catch a client transform bug (wrong field mapping, dropped em-dash).
    root = xml.etree.ElementTree.fromstring(_TIMELINE_ACTIVE)
    timeline = root.find('./Timeline[@type="music"]')
    assert timeline is not None, 'fixture is missing its music <Timeline>'
    track = timeline.find('./Track')
    assert track is not None, 'active fixture is missing its <Track>'

    result = _CLIENT.get_now_playing()
    assert isinstance(result, Stream)
    assert result.id == track.get('ratingKey')
    assert result.name == track.get('parentTitle')
    assert result.current_track == f'{track.get("grandparentTitle")} — {track.get("title")}'
    assert result.status == ('playing' if timeline.get('state') == 'playing' else 'paused')


@respx.mock
def test_get_now_playing_idle():
    respx.get(re.compile(r'.*/player/timeline/poll.*')).mock(return_value=Response(200, text=_TIMELINE_IDLE))
    result = _CLIENT.get_now_playing()
    assert result is None


@respx.mock
def test_play():
    route = respx.get(re.compile(r'.*/player/playback/play.*')).mock(return_value=Response(200))
    _CLIENT.play(machine_id='my-machine')
    assert route.called
    request = route.calls.last.request
    assert 'my-machine' in str(request.url)


@respx.mock
def test_pause():
    route = respx.get(re.compile(r'.*/player/playback/pause.*')).mock(return_value=Response(200))
    _CLIENT.pause(machine_id='my-machine')
    assert route.called


@respx.mock
def test_skip():
    route = respx.get(re.compile(r'.*/player/playback/skipNext.*')).mock(return_value=Response(200))
    _CLIENT.skip(machine_id='my-machine')
    assert route.called
