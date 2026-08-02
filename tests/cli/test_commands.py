"""Tests for the `audera` CLI, driven as the process provisioning drives it."""

import pytest
import yaml

import audera.dal.sources as sources_dal
from audera.cli import conf
from audera.domains.sources import CATALOG


def test_conf_snapserver_emits_what_the_renderer_produces(audera_cli):
    """The whole document reaches stdout, and an unrecorded set is the bootstrap set.

    Provisioning redirects this into `/etc/snapserver.conf`, so the comparison is byte-for-byte
    rather than on fragments. `audera_cli`'s home is empty, which is a freshly flashed device.
    """
    result = audera_cli('streamer', 'conf', 'snapserver.conf')
    assert result.returncode == 0
    assert result.stdout == conf.render_snapserver(list(sources_dal.DEFAULT_ENABLED))
    assert 'default_source = AirPlay\n' in result.stdout


def test_conf_snapserver_follows_the_recorded_source_set(audera_cli):
    """A reprovision renders the operator's sources rather than the bootstrap default.

    `~/.audera/sources.json` outlives a flash, so a conf rendered from `DEFAULT_ENABLED` would
    name a stream the operator turned off and drop the one they run, and Snapserver would
    reassign every group onto the former at the first client connect.
    """
    sources_dal.adopt(['PlexAmp'])
    out = audera_cli('streamer', 'conf', 'snapserver.conf').stdout
    # Anchored on the newline: `default_source = ` contains `source = ` as a substring.
    assert out.count('\nsource = ') == 1
    assert 'name=PlexAmp' in out
    assert 'default_source = PlexAmp\n' in out


def test_conf_snapserver_pins_the_datadir(audera_cli):
    # `server.json` holds what Audera does not store: player names, volumes, latencies, group
    # membership, and each group's `stream_id`. Snapserver locates it at
    # `$HOME/.config/snapserver/` when this key is empty and the process is in the foreground,
    # which the unit is, and the unit sets a `HOME` for go-librespot. Left empty, the persisted
    # player configuration follows that `HOME`, and moving the path starts snapserver from an
    # empty state file.
    assert '\ndatadir = /var/lib/snapserver/\n' in audera_cli('streamer', 'conf', 'snapserver.conf').stdout


def test_conf_snapserver_sandbox_dir_stays_commented(audera_cli):
    # `sandbox_dir` does not exist before snapserver 0.33.0; uncommenting it hands the
    # pinned 0.31.0 an unknown key at boot.
    assert '#sandbox_dir = ' in audera_cli('streamer', 'conf', 'snapserver.conf').stdout


@pytest.mark.parametrize(
    ('recorded', 'enabled_units', 'disabled_units'),
    [
        # Nothing recorded is a fresh flash, which is `DEFAULT_ENABLED`.
        pytest.param(None, ['nqptp'], ['plexamp', 'plexamp-mdns'], id='unrecorded'),
        pytest.param(['PlexAmp'], ['plexamp', 'plexamp-mdns'], ['nqptp'], id='plexamp'),
        pytest.param(['AirPlay', 'PlexAmp'], ['nqptp', 'plexamp', 'plexamp-mdns'], [], id='both'),
        # Snapserver forks and reaps Spotify's backend, so an enabled Spotify has no unit to move and
        # provisioning is left with nothing to enable.
        pytest.param(['Spotify'], [], ['nqptp', 'plexamp', 'plexamp-mdns'], id='no-units'),
    ],
)
def test_units_lists_the_recorded_sources_units(audera_cli, recorded, enabled_units, disabled_units):
    """Provisioning's two lists, which between them leave no catalogued unit in the previous image's state.

    One unit per line, in catalog order, which is what puts AirPlay's PTP clock first among the units
    provisioning starts before snapserver forks shairport-sync.
    """
    if recorded is not None:
        sources_dal.adopt(recorded)

    # Compared against the rendered lines rather than against a `.split()`, so an empty list is an
    # empty stdout rather than a blank line. `os/dietpi/lib/streamer.sh` word-splits this output
    # unquoted and guards on it being empty.
    assert audera_cli('streamer', 'units', '--enabled').stdout == ''.join(f'{unit}\n' for unit in enabled_units)
    assert audera_cli('streamer', 'units', '--disabled').stdout == ''.join(f'{unit}\n' for unit in disabled_units)


def test_units_lists_are_disjoint_and_cover_the_catalog(audera_cli):
    # Provisioning enables one list and disables the other, so a unit in both would have its state
    # decided by whichever call ran last, and a unit in neither keeps the state the previous image
    # left it in.
    enabled = audera_cli('streamer', 'units', '--enabled').stdout.split()
    disabled = audera_cli('streamer', 'units', '--disabled').stdout.split()

    assert not set(enabled) & set(disabled)
    assert sorted(enabled + disabled) == sorted(unit for source in CATALOG for unit in source.units)


def test_units_requires_a_selection(audera_cli):
    # `--enabled`/`--disabled` is a required mutually exclusive group. A bare `units` silently
    # meaning one of them would make the wrong provisioning call look right, so argparse refuses
    # it — which is only observable from a process.
    result = audera_cli('streamer', 'units')
    assert result.returncode == 2
    assert 'one of the arguments --enabled --disabled is required' in result.stderr


def test_conf_rejects_an_unknown_filename(audera_cli):
    result = audera_cli('streamer', 'conf', 'nope.conf')
    assert result.returncode == 1
    assert "Unknown config file: 'nope.conf'" in result.stderr


def test_a_subject_is_required(audera_cli):
    assert audera_cli().returncode == 2


def test_conf_go_librespot_pins_the_values_it_argues_for(audera_cli):
    # go-librespot is configured once at provision time and never re-rendered, so every value
    # below stays as it was written until the device is reprovisioned.
    result = audera_cli('streamer', 'conf', 'go-librespot.yml')
    assert result.stdout == conf.render_go_librespot()
    config = yaml.safe_load(result.stdout)

    # Snapserver reads the forked child's stdout, so the pipe backend must write there.
    assert config['audio_backend'] == 'pipe'
    assert config['audio_output_pipe'] == '/dev/stdout'

    # Per-song levelling at unity gain. Snapcast documents `+6.0`, which would add clipping
    # exposure the DSP editor's auto-protected pre-amp cannot account for.
    assert config['normalisation_disabled'] is False
    assert config['normalisation_use_album_gain'] is False
    assert config['normalisation_pregain'] == 0.0

    # Zeroconf is the only auth path Spotify still supports, and persisting what it returns lets
    # a disabled source be re-enabled without re-pairing from a phone.
    assert config['zeroconf_enabled'] is True
    assert config['credentials']['type'] == 'zeroconf'
    assert config['credentials']['zeroconf']['persist_credentials'] is True

    # `builtin` is upstream's default, intended for hosts with no avahi, and is never
    # auto-detected away from. This host runs an avahi-daemon for AirPlay, `plexamp-mdns`, and
    # `audera.local`, and upstream recommends avahi to avoid port conflicts on UDP 5353.
    assert config['zeroconf_backend'] == 'avahi'

    # The API server is off because nothing uses it yet. The now-playing metadata follow-up flips
    # it, alongside snapserver >= 0.34's bundled meta_go-librespot.py.
    assert config['server']['enabled'] is False


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_conf_camilladsp_default_format_is_s32le(audera_cli, subject):
    result = audera_cli(subject, 'conf', 'camilladsp.yml')
    assert result.stdout == conf.render_camilladsp()
    # Default leaves both capture and playback at S32LE.
    assert result.stdout.count('format: S32LE') == 2
    assert 'format: S16LE' not in result.stdout


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_conf_camilladsp_s16le_only_changes_playback(audera_cli, subject):
    out = audera_cli(subject, 'conf', 'camilladsp.yml', '--playback-format', 'S16LE').stdout
    # Playback becomes S16LE; capture stays S32LE to match Snapclient's loopback.
    assert '    format: S16LE\n' in out
    assert out.count('format: S16LE') == 1
    assert out.count('format: S32LE') == 1
    # Comments are preserved end-to-end (scope + render fidelity).
    assert 'HDMI STABILITY' in out
