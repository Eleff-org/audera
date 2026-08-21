import json
import os
import threading

import pytest

import audera.dal.sources as sources_dal
from audera.domains.sources import CATALOG, source_lines
from audera.errors import StorageError


def test_sources_absent_file_returns_the_default(audera_home):
    assert sources_dal.get_enabled() == list(sources_dal.DEFAULT_ENABLED)


def test_sources_round_trip(audera_home):
    sources_dal.set_enabled('Spotify', True)
    assert sources_dal.get_enabled() == ['AirPlay', 'Spotify']


def test_sources_set_enabled_returns_the_new_set(audera_home):
    result = sources_dal.set_enabled('Spotify', True)
    assert result == sources_dal.get_enabled()


def test_sources_enabling_twice_is_idempotent(audera_home):
    sources_dal.set_enabled('Spotify', True)
    assert sources_dal.set_enabled('Spotify', True) == ['AirPlay', 'Spotify']


def test_sources_disabling_an_absent_id_is_a_no_op(audera_home):
    assert sources_dal.set_enabled('Spotify', False) == ['AirPlay']


def test_sources_disable(audera_home):
    sources_dal.set_enabled('Spotify', True)
    assert sources_dal.set_enabled('AirPlay', False) == ['Spotify']


def test_sources_a_failed_write_leaves_the_previous_file_readable(audera_home, monkeypatch):
    # The Players tab reads the enabled set on every render while the Sources tab writes it from a
    # worker thread, so a reader can land mid-write. `io.write_text` moves a sibling file into
    # place, so a half-written set never reaches the destination.
    sources_dal.set_enabled('Spotify', True)

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(sources_dal.io.os, 'replace', _boom)
    with pytest.raises(StorageError):
        sources_dal.set_enabled('PlexAmp', True)

    assert sources_dal.get_enabled() == ['AirPlay', 'Spotify']
    with open(os.path.join(sources_dal.PATH, sources_dal.FILE_NAME), 'r') as f:
        assert json.load(f) == {'sources': {'enabled': ['AirPlay', 'Spotify']}}


def test_sources_corrupt_file_degrades_to_the_default(audera_home):
    # A corrupt file degrades exactly like an absent one: the sources layer never hard-fails a
    # read, it falls back to `DEFAULT_ENABLED`.
    os.makedirs(sources_dal.PATH, exist_ok=True)
    with open(os.path.join(sources_dal.PATH, sources_dal.FILE_NAME), 'w') as f:
        f.write('{ not json')

    assert sources_dal.get_enabled() == list(sources_dal.DEFAULT_ENABLED)
    assert not sources_dal.is_recorded()


def test_sources_setup_state_round_trip(audera_home):
    # Without a record, the card re-derived `setup required` from a live probe every render, and a
    # backend that was slow to answer read as unclaimed.
    assert sources_dal.get_setup('PlexAmp') == {}
    sources_dal.set_setup_complete('PlexAmp', True)
    assert sources_dal.get_setup('PlexAmp') == {'complete': True}


def test_sources_setup_state_and_the_enabled_set_do_not_clobber_each_other(audera_home):
    # Both writes are read-modify-write over the whole document, so neither section clobbers the
    # other.
    sources_dal.set_setup_complete('PlexAmp', True)
    sources_dal.set_enabled('Spotify', True)

    assert sources_dal.get_enabled() == ['AirPlay', 'Spotify']
    assert sources_dal.get_setup('PlexAmp') == {'complete': True}


def test_sources_a_setup_write_alone_is_not_a_recorded_enabled_set(audera_home):
    """A setup write alone leaves the enabled set unrecorded, so adoption still runs.

    `is_recorded()` reads the `enabled` key rather than the file's existence, because a setup write
    creates the file too. Keyed on the file, a claim would permanently refuse adoption and freeze
    the enabled set at `DEFAULT_ENABLED`.
    """
    sources_dal.set_setup_complete('PlexAmp', True)

    assert not sources_dal.is_recorded()
    assert sources_dal.adopt(['PlexAmp']) is True
    assert sources_dal.get_setup('PlexAmp') == {'complete': True}


def test_sources_clear_setup_discards_the_record(audera_home):
    # Disabling a source is the only thing that discards its setup state, since the next enable
    # faces a backend that is no longer claimed.
    sources_dal.set_setup_complete('PlexAmp', True)
    sources_dal.clear_setup('PlexAmp')
    assert sources_dal.get_setup('PlexAmp') == {}


def test_sources_clear_setup_of_an_unrecorded_source_is_a_no_op(audera_home):
    # `_disable_source` clears unconditionally, so this runs for every source that never had a
    # setup flow at all.
    sources_dal.set_enabled('Spotify', True)
    sources_dal.clear_setup('Spotify')
    assert sources_dal.get_enabled() == ['AirPlay', 'Spotify']


def test_sources_set_setup_complete_notifies_observers(audera_home):
    """Setup writes must fan out so other browsers drop the claim chip after a successful claim.

    Regression: only enabled-set writes notified, so browser B kept showing setup-required after
    browser A finished the Plex claim.
    """
    fired: list[bool] = []
    sources_dal.on_change(lambda: fired.append(True))
    try:
        sources_dal.set_setup_complete('PlexAmp', True)
        assert fired == [True]
    finally:
        sources_dal._observers.pop()


def test_sources_clear_setup_notifies_only_when_a_record_is_removed(audera_home):
    fired: list[bool] = []
    sources_dal.on_change(lambda: fired.append(True))
    try:
        sources_dal.clear_setup('PlexAmp')
        assert fired == []

        sources_dal.set_setup_complete('PlexAmp', True)
        fired.clear()
        sources_dal.clear_setup('PlexAmp')
        assert fired == [True]
        assert sources_dal.get_setup('PlexAmp') == {}
    finally:
        sources_dal._observers.pop()


def test_sources_absent_file_is_not_recorded(audera_home):
    # `get_enabled()` returns the same list for an absent file and for a recorded default set,
    # so adoption reads `is_recorded()` to tell the two apart.
    assert not sources_dal.is_recorded()
    assert sources_dal.get_enabled() == list(sources_dal.DEFAULT_ENABLED)


def test_sources_adopt_records_the_observed_set(audera_home):
    assert sources_dal.adopt(['PlexAmp']) is True
    assert sources_dal.is_recorded()
    assert sources_dal.get_enabled() == ['PlexAmp']


def test_sources_adopt_never_overwrites_a_recorded_set(audera_home):
    sources_dal.set_enabled('Spotify', True)
    # A recorded set takes precedence over anything inferred from the server.
    assert sources_dal.adopt(['PlexAmp']) is False
    assert sources_dal.get_enabled() == ['AirPlay', 'Spotify']


def test_sources_adopt_refuses_an_empty_set(audera_home):
    # An empty observation means an unreachable Snapserver, and recording it would render a
    # zero-stream conf.
    assert sources_dal.adopt([]) is False
    assert not sources_dal.is_recorded()


def test_sources_concurrent_set_enabled_and_set_setup_complete(audera_home):
    """Both mutations survive when two threads race on the same file."""
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _toggle():
        try:
            barrier.wait(timeout=5)
            sources_dal.set_enabled('Spotify', True)
        except Exception as exc:
            errors.append(exc)

    def _setup():
        try:
            barrier.wait(timeout=5)
            sources_dal.set_setup_complete('PlexAmp', True)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_toggle)
    t2 = threading.Thread(target=_setup)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, errors
    assert 'Spotify' in sources_dal.get_enabled()
    assert sources_dal.get_setup('PlexAmp') == {'complete': True}


def test_sources_default_enabled_does_not_drift_from_the_catalog():
    # The DAL does not import the catalog, so nothing else stops `DEFAULT_ENABLED` from naming an
    # uncatalogued id, which would make `render_snapserver()` raise on a flash.
    assert sources_dal.DEFAULT_ENABLED
    assert set(sources_dal.DEFAULT_ENABLED) <= {source.id for source in CATALOG}
    assert source_lines(sources_dal.DEFAULT_ENABLED)
