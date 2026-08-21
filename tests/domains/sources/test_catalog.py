"""Tests for the audio-source catalog and the conf it renders.

The catalog's three rules are asserted directly rather than through the CLI that emits them.
"""

import itertools

import pytest
import yaml

from audera.cli import conf
from audera.domains.sources import CATALOG, default_source, source_lines

ALL_IDS = [source.id for source in CATALOG]
SUBSETS = [list(subset) for size in range(len(ALL_IDS) + 1) for subset in itertools.combinations(ALL_IDS, size)]

# go-librespot's three valid pipe formats, by bit depth. The Spotify source URI states a bit depth
# too, and nothing at runtime checks that the two agree.
PIPE_FORMAT_BITS: dict[str, int] = {'s16le': 16, 's32le': 32, 'f32le': 32}


def test_catalog_ids_are_unique():
    # The id is the Snapcast stream name, so a duplicate would map two sources onto one stream.
    assert len(ALL_IDS) == len(set(ALL_IDS))


@pytest.mark.parametrize('enabled', SUBSETS)
def test_source_lines_renders_one_line_per_enabled_source(enabled):
    lines = source_lines(enabled)
    assert len(lines) == len(enabled)
    for line in lines:
        assert line.startswith('source = ')


@pytest.mark.parametrize('enabled', SUBSETS)
def test_source_lines_follows_catalog_order(enabled):
    lines = source_lines(enabled)
    expected = [source.id for source in CATALOG if source.id in enabled]
    assert [line.split('name=')[1].split('&')[0] for line in lines] == expected


@pytest.mark.parametrize('enabled', SUBSETS)
def test_source_lines_is_invariant_to_input_order_and_duplicates(enabled):
    assert source_lines(list(reversed(enabled))) == source_lines(enabled)
    assert source_lines(enabled + enabled) == source_lines(enabled)


def test_source_lines_skips_uncatalogued_ids():
    # Removing a catalog entry must stay safe for a device whose sources.json names it.
    assert source_lines(['Nope']) == []
    assert source_lines(ALL_IDS + ['Nope']) == source_lines(ALL_IDS)


def test_source_lines_resolves_the_id_placeholder():
    for line in source_lines(ALL_IDS):
        assert '{id}' not in line
    assert 'name=PlexAmp' in source_lines(['PlexAmp'])[0]
    assert 'name=Spotify' in source_lines(['Spotify'])[0]
    assert 'name=AirPlay' in source_lines(['AirPlay'])[0]


def test_spotify_states_a_sampleformat():
    # go-librespot's pipe is fixed at 44100/2; without this it plays at the wrong speed.
    assert 'sampleformat=44100:16:2' in source_lines(['Spotify'])[0]


def test_airplay_states_no_sampleformat():
    # snapserver forces 44100:16:2 on airplay:// and ignores any supplied value.
    assert 'sampleformat' not in source_lines(['AirPlay'])[0]


def test_spotify_passes_no_config_dir():
    # go-librespot resolves `--config_dir`'s default through `os.UserConfigDir()` and returns
    # its error before `flag.Parse` runs, so with no `$HOME` the flag is never read, and with one
    # it is redundant. Provisioning's `snapserver.service.d` drop-in sets `HOME`.
    assert 'config_dir' not in source_lines(['Spotify'])[0]


def test_spotify_logs_the_backend_stderr():
    # Snapserver forks go-librespot, so there is no unit and no `journalctl -u` for it. With
    # `log_stderr=false` a backend that cannot start reports the failure nowhere on the host.
    assert 'log_stderr=true' in source_lines(['Spotify'])[0]


@pytest.mark.parametrize('enabled', [subset for subset in SUBSETS if subset])
def test_default_source_is_the_first_catalogued_entry_enabled(enabled):
    assert default_source(list(reversed(enabled))) == next(source.id for source in CATALOG if source.id in enabled)


def test_default_source_prefers_catalog_order_over_input_order():
    assert default_source(['PlexAmp', 'Spotify']) == 'Spotify'
    assert default_source(['PlexAmp', 'AirPlay']) == 'AirPlay'


def test_default_source_is_empty_when_nothing_catalogued_is_enabled():
    assert default_source([]) == ''
    assert default_source(['Nope']) == ''


@pytest.mark.parametrize('enabled', [[], ['Nope']])
def test_render_snapserver_rejects_an_empty_stream_list(enabled):
    # Rule 2. Zero streams crashes snapserver at the first client connect, including when the ids
    # name no catalog entry.
    with pytest.raises(ValueError):
        conf.render_snapserver(enabled)


def test_render_snapserver_default_source_follows_the_enabled_set():
    # Rule 3. A `default_source` naming a stream the conf does not provide mis-routes every
    # reassigned group without reporting an error.
    assert 'default_source = Spotify\n' in conf.render_snapserver(['Spotify'])
    assert 'default_source = Spotify\n' in conf.render_snapserver(['PlexAmp', 'Spotify'])


def test_render_snapserver_ignores_argument_order():
    assert conf.render_snapserver(['AirPlay', 'PlexAmp']) == conf.render_snapserver(['PlexAmp', 'AirPlay'])


def test_go_librespot_pipe_format_agrees_with_the_spotify_source_uri():
    # go-librespot states the sample format and snapserver states the rate and channels, in two
    # files, and neither validates the other. A mismatch produces a byte-misaligned stream rather
    # than an error.
    config = yaml.safe_load(conf.render_go_librespot())
    pipe_bits = PIPE_FORMAT_BITS[config['audio_output_pipe_format']]

    sampleformat = source_lines(['Spotify'])[0].split('sampleformat=')[1].split('&')[0]
    _, uri_bits, _ = sampleformat.split(':')

    assert pipe_bits == int(uri_bits)
