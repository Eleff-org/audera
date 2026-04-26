import audera.dal.streams as streams
from audera.models.stream import Stream


def _make_stream(id='stream1', name='PlexAmp', status='idle') -> Stream:
    return Stream(
        id=id,
        name=name,
        uri='tcp://0.0.0.0:4953',
        status=status,
        current_track=None,
    )


def test_stream_create(audera_home):
    stream = _make_stream()
    streams.create(stream)
    assert streams.exists(stream.id)


def test_stream_get(audera_home):
    stream = _make_stream()
    streams.create(stream)

    result = streams.get_stream(stream.id)
    assert result == stream


def test_stream_update(audera_home):
    stream = _make_stream()
    streams.create(stream)

    updated = Stream(
        id=stream.id,
        name=stream.name,
        uri=stream.uri,
        status='playing',
        current_track='Artist — Song',
    )
    streams.update(updated)

    result = streams.get_stream(stream.id)
    assert result.status == 'playing'
    assert result.current_track == 'Artist — Song'


def test_stream_delete(audera_home):
    stream = _make_stream()
    streams.create(stream)
    streams.delete(stream.id)
    assert not streams.exists(stream.id)


def test_get_all_streams(audera_home):
    s1 = _make_stream(id='s1', name='Lounge')
    s2 = _make_stream(id='s2', name='Bedroom')
    streams.create(s1)
    streams.create(s2)

    result = streams.get_all_streams()
    ids = {s.id for s in result}
    assert ids == {'s1', 's2'}


def test_get_all_streams_empty(audera_home):
    result = streams.get_all_streams()
    assert result == []


def test_stream_current_track_none_roundtrip(audera_home):
    stream = _make_stream()
    streams.create(stream)

    result = streams.get_stream(stream.id)
    assert result.current_track is None


def test_stream_current_track_set_roundtrip(audera_home):
    stream = Stream(id='s1', name='Test', uri='', status='playing', current_track='Band — Track')
    streams.create(stream)

    result = streams.get_stream(stream.id)
    assert result.current_track == 'Band — Track'
