from audera.models.stream import Stream


def test_stream_current_track_set_roundtrip():
    # A set `current_track` survives the `to_dict`/`from_dict` round-trip. Previously only
    # the retired streams DAL tests asserted this; it lives here now as a pure model test.
    stream = Stream(id='s1', name='PlexAmp', uri='tcp://0.0.0.0:4953', status='playing', current_track='Band — Track')
    assert Stream.from_dict(stream.to_dict()) == stream


def test_stream_current_track_none_roundtrip():
    # `to_dict()` emits `''` for a `None` track and the `_coerce_current_track` validator
    # coerces the falsy `''` back to `None`, so the round-trip lands as `None`.
    stream = Stream(id='s1', name='PlexAmp', uri='tcp://0.0.0.0:4953', status='idle', current_track=None)
    result = Stream.from_dict(stream.to_dict())
    assert result.current_track is None
    assert result == stream
