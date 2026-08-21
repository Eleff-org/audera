import re
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
    result = _CLIENT.get_now_playing()
    assert isinstance(result, Stream)
    assert result.id == '200896'
    assert result.status == 'playing'
    assert result.current_track == 'Of Monsters and Men — Television Love'
    assert result.name == 'All Is Love and Pain in the Mouse Parade'


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
