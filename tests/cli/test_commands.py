"""Tests for the `audera` CLI, driven as a process."""

import pytest
import yaml

import audera.dal.sources as sources_dal
from audera.cli import commands, conf
from audera.domains.sources import CATALOG
from audera.services import netifaces
from audera.ui import setup, streamer
from audera.ui.setup import _mock


def test_conf_snapserver_emits_what_the_renderer_produces(audera_cli):
    """The whole document reaches stdout, and an unrecorded set renders the bootstrap set.

    Provisioning redirects this into `/etc/snapserver.conf`, so the comparison is byte-for-byte.
    `audera_cli`'s home is empty, which is a freshly flashed device.
    """
    result = audera_cli('streamer', 'conf', 'snapserver.conf')
    assert result.returncode == 0
    assert result.stdout == conf.render_snapserver(list(sources_dal.DEFAULT_ENABLED))
    assert 'default_source = AirPlay\n' in result.stdout


def test_conf_snapserver_follows_the_recorded_source_set(audera_cli):
    """A reprovision renders the operator's sources rather than the bootstrap default.

    `~/.audera/sources.json` outlives a flash. A conf rendered from `DEFAULT_ENABLED` would drop
    the stream the operator runs, and Snapserver would reassign every group at the first client
    connect.
    """
    sources_dal.adopt(['PlexAmp'])
    out = audera_cli('streamer', 'conf', 'snapserver.conf').stdout
    # Anchored on the newline: `default_source = ` contains `source = ` as a substring.
    assert out.count('\nsource = ') == 1
    assert 'name=PlexAmp' in out
    assert 'default_source = PlexAmp\n' in out


def test_conf_snapserver_pins_the_datadir(audera_cli):
    # `server.json` holds player names, volumes, latencies, group membership and each group's
    # `stream_id`. Left empty, snapserver locates it under the `$HOME` the unit sets for
    # go-librespot, so the persisted player configuration would follow that `HOME`.
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
        # Snapserver forks and reaps Spotify's backend, so an enabled Spotify has no unit to move.
        pytest.param(['Spotify'], [], ['nqptp', 'plexamp', 'plexamp-mdns'], id='no-units'),
    ],
)
def test_units_lists_the_recorded_sources_units(audera_cli, recorded, enabled_units, disabled_units):
    """Both lists name the units of the recorded sources.

    One unit per line, in catalog order, which puts AirPlay's PTP clock first among the units
    provisioning starts before snapserver forks shairport-sync.
    """
    if recorded is not None:
        sources_dal.adopt(recorded)

    # Compared against the rendered lines rather than a `.split()`, so an empty list is an empty
    # stdout rather than a blank line. `os/dietpi/lib/streamer.sh` word-splits this output unquoted
    # and guards on it being empty.
    assert audera_cli('streamer', 'units', '--enabled').stdout == ''.join(f'{unit}\n' for unit in enabled_units)
    assert audera_cli('streamer', 'units', '--disabled').stdout == ''.join(f'{unit}\n' for unit in disabled_units)


def test_units_lists_are_disjoint_and_cover_the_catalog(audera_cli):
    # Provisioning enables one list and disables the other, so a unit in both has its state decided
    # by whichever call ran last, and a unit in neither keeps the previous image's state.
    enabled = audera_cli('streamer', 'units', '--enabled').stdout.split()
    disabled = audera_cli('streamer', 'units', '--disabled').stdout.split()

    assert not set(enabled) & set(disabled)
    assert sorted(enabled + disabled) == sorted(unit for source in CATALOG for unit in source.units)


def test_units_requires_a_selection(audera_cli):
    # `--enabled`/`--disabled` is a required mutually exclusive group. argparse's refusal is only
    # observable from a process.
    result = audera_cli('streamer', 'units')
    assert result.returncode == 2
    assert 'one of the arguments --enabled --disabled is required' in result.stderr


def test_conf_rejects_an_unknown_filename(audera_cli):
    result = audera_cli('streamer', 'conf', 'nope.conf')
    assert result.returncode == 1
    assert "Unknown streamer config file: 'nope.conf'" in result.stderr


def test_conf_rejects_a_cross_role_filename(audera_cli):
    # A name valid for the other role is rejected exactly as an unknown one is, so a player can
    # never emit a streamer's snapserver.conf onto itself.
    result = audera_cli('player', 'conf', 'snapserver.conf')
    assert result.returncode == 1
    assert "Unknown player config file: 'snapserver.conf'" in result.stderr


def test_a_subject_is_required(audera_cli):
    assert audera_cli().returncode == 2


def test_conf_go_librespot_pins_the_values_it_argues_for(audera_cli):
    # go-librespot is configured once at provision time and never re-rendered, so every value below
    # stays as written until the device is reprovisioned.
    result = audera_cli('streamer', 'conf', 'go-librespot.yml')
    assert result.stdout == conf.render_go_librespot()
    config = yaml.safe_load(result.stdout)

    # Snapserver reads the forked child's stdout, so the pipe backend must write there.
    assert config['audio_backend'] == 'pipe'
    assert config['audio_output_pipe'] == '/dev/stdout'

    # Per-song levelling at unity gain. Snapcast documents `+6.0`, which adds clipping exposure the
    # DSP editor's auto-protected pre-amp cannot account for.
    assert config['normalisation_disabled'] is False
    assert config['normalisation_use_album_gain'] is False
    assert config['normalisation_pregain'] == 0.0

    # Zeroconf is the only auth path Spotify still supports, and persisting its credentials lets a
    # disabled source be re-enabled without re-pairing from a phone.
    assert config['zeroconf_enabled'] is True
    assert config['credentials']['type'] == 'zeroconf'
    assert config['credentials']['zeroconf']['persist_credentials'] is True

    # Upstream's `builtin` default is never auto-detected away from. This host already runs
    # avahi-daemon, and upstream recommends avahi to avoid port conflicts on UDP 5353.
    assert config['zeroconf_backend'] == 'avahi'

    # The API server is off because nothing uses it yet. The now-playing metadata follow-up enables
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


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_conf_camilladsp_default_playback_device_is_hw0(audera_cli, subject):
    out = audera_cli(subject, 'conf', 'camilladsp.yml').stdout
    assert '    device: "hw:0"\n' in out


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_conf_camilladsp_playback_device_override(audera_cli, subject):
    out = audera_cli(subject, 'conf', 'camilladsp.yml', '--playback-device', 'plughw:0').stdout
    # Playback device becomes plughw:0; capture device stays hw:Loopback,1.
    assert '    device: "plughw:0"\n' in out
    assert '    device: "hw:Loopback,1"\n' in out


# The systemd units and the nginx/PlexAmp artifacts provisioning redirects into place. The systemd
# lane renders these from `conf.render_*` directly, so a process test is the only coverage of
# `_emit_conf`'s dispatch: a name mapped to the wrong renderer, or to none, ships a wrong or empty
# file the shell redirects verbatim.

_STREAMER_ARTIFACTS = [
    ('snapserver.service', conf.render_snapserver_service),
    ('camilladsp.service', conf.render_camilladsp_service),
    ('plexamp.service', conf.render_plexamp_service),
    ('plexamp-mdns.service', conf.render_plexamp_mdns_service),
    ('plexamp-mdns.sh', conf.render_plexamp_mdns_helper),
    ('audera-streamer.service', conf.render_audera_streamer_service),
    ('nqptp-timeout.conf', conf.render_nqptp_timeout),
    ('nginx-site', conf.render_nginx_site),
]


@pytest.mark.parametrize(('filename', 'renderer'), _STREAMER_ARTIFACTS, ids=[name for name, _ in _STREAMER_ARTIFACTS])
def test_conf_streamer_artifacts_emit_what_their_renderers_produce(audera_cli, filename, renderer):
    result = audera_cli('streamer', 'conf', filename)
    assert result.returncode == 0
    assert result.stdout == renderer()


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_conf_snapclient_service_is_role_branched(audera_cli, subject):
    """`snapclient.service` renders per role: the streamer's reads the local Snapserver, the player's not.

    A player that emitted the streamer's unit would point its snapclient at a loopback Snapserver that
    is not there and order after a `snapserver.service` it never installs.
    """
    result = audera_cli(subject, 'conf', 'snapclient.service')
    assert result.returncode == 0
    assert result.stdout == conf.render_snapclient_service(subject)
    if subject == 'streamer':
        assert '--host 127.0.0.1' in result.stdout
        assert 'snapserver.service' in result.stdout
    else:
        assert '--host' not in result.stdout
        assert 'snapserver.service' not in result.stdout


def test_conf_player_emits_the_player_service(audera_cli):
    result = audera_cli('player', 'conf', 'audera-player.service')
    assert result.returncode == 0
    assert result.stdout == conf.render_audera_player_service()


def test_conf_camilladsp_service_sources_the_port_from_settings(audera_cli):
    """The DSP WebSocket port is `settings.camilladsp_port`, not a shell literal.

    Overriding `AUDERA_CAMILLADSP_PORT` moves the `-p` in the rendered unit, which the hardcoded
    `1234` this replaced — one of four inline shell literals that had to silently agree — could not.
    """
    assert '-p 1234 ' in audera_cli('streamer', 'conf', 'camilladsp.service').stdout

    overridden = audera_cli('streamer', 'conf', 'camilladsp.service', env_overrides={'AUDERA_CAMILLADSP_PORT': '9999'}).stdout
    assert '-p 9999 ' in overridden
    assert '-p 1234 ' not in overridden


def test_conf_nginx_site_sources_the_ui_port_from_settings(audera_cli):
    """The proxied UI port is `settings.server_port`, not the literal `80` the heredoc carried."""
    assert 'proxy_pass http://127.0.0.1:80;' in audera_cli('streamer', 'conf', 'nginx-site').stdout

    overridden = audera_cli('streamer', 'conf', 'nginx-site', env_overrides={'AUDERA_SERVER_PORT': '8443'}).stdout
    assert 'proxy_pass http://127.0.0.1:8443;' in overridden
    assert 'proxy_pass http://127.0.0.1:80;' not in overridden


def test_conf_plexamp_service_keeps_the_dns_retry_loop_literal(audera_cli):
    """The `$(seq 1 30)` retry and `$i` reach the unit as text, for the shell systemd starts.

    A renderer that interpolated them would emit a unit the shell cannot loop, so PlexAmp would launch
    before `plex.tv` resolves.
    """
    out = audera_cli('streamer', 'conf', 'plexamp.service').stdout
    assert 'for i in $(seq 1 30); do' in out


def test_conf_plexamp_audio_uuid_has_no_trailing_newline(audera_cli):
    """The device id is `S` + `render_asound`'s pcm, stored verbatim with no trailing newline.

    PlexAmp reads the file byte-for-byte, so a stray newline or a pcm that does not byte-match the
    `asound.conf` name routes audio to a device the snapfifo does not feed.
    """
    result = audera_cli('streamer', 'conf', 'plexamp-audio-uuid')
    assert result.returncode == 0
    assert result.stdout == f'S{conf.PLEXAMP_PCM}'
    assert not result.stdout.endswith('\n')
    assert f'pcm.{conf.PLEXAMP_PCM} ' in audera_cli('streamer', 'conf', 'asound.conf').stdout


# The `start`/`setup` verbs launch a blocking server, so process tests cover only argparse wiring.


@pytest.mark.parametrize('subject', ['streamer', 'player'])
def test_setup_help_exits_zero(audera_cli, subject):
    # The `setup` verb is registered under both subjects and its `--mock` flag parses.
    assert audera_cli(subject, 'setup', '--help').returncode == 0


def test_streamer_start_accepts_mock_flag(audera_cli):
    # `--help` short-circuits before the blocking `streamer.run()`, so the flag is observably parsed.
    assert audera_cli('streamer', 'start', '--mock', '--help').returncode == 0


# In-process unit tests, matching the lazy-import contract `commands.py` documents. `setup.run` and
# `streamer.run` are patched out so nothing binds a socket.


@pytest.mark.parametrize(
    ('command', 'role'),
    [(commands.streamer_setup, 'streamer'), (commands.player_setup, 'player')],
)
def test_setup_applies_seams_then_runs(monkeypatch, command, role):
    calls = []
    monkeypatch.setattr(_mock, 'apply_seams', lambda: calls.append('apply_seams'))
    monkeypatch.setattr(_mock, 'loopback_bind', lambda: calls.append('loopback_bind'))
    monkeypatch.setattr(setup, 'run', lambda **kwargs: calls.append(('run', kwargs)))

    command(mock=True)

    assert calls == ['apply_seams', 'loopback_bind', ('run', {'role': role})]


def test_streamer_start_mock_skips_the_connected_gate(monkeypatch):
    calls = []
    monkeypatch.setattr(_mock, 'apply_seams', lambda: calls.append('apply_seams'))
    monkeypatch.setattr(_mock, 'loopback_bind', lambda: calls.append('loopback_bind'))
    monkeypatch.setattr(streamer, 'run', lambda: calls.append('run'))
    monkeypatch.setattr(netifaces, 'connected', lambda: calls.append('connected') or True)

    commands.streamer_start(mock=True)

    # The gate is skipped (`connected` never consulted), loopback is bound, and the web-app keeps
    # the real OS by not applying the seams.
    assert 'connected' not in calls
    assert 'apply_seams' not in calls
    assert calls == ['loopback_bind', 'run']


def test_streamer_start_runs_without_setup_when_the_retry_gate_passes(monkeypatch):
    """A connected device does not enter setup on a normal boot."""
    calls = []
    monkeypatch.setattr(netifaces, 'connected_with_retry', lambda: calls.append('gate') or True)
    monkeypatch.setattr(setup, 'run', lambda **kwargs: calls.append(('setup', kwargs)))
    monkeypatch.setattr(streamer, 'run', lambda: calls.append('run'))

    commands.streamer_start()

    assert calls == ['gate', 'run']


def test_streamer_start_enters_setup_when_the_retry_gate_fails(monkeypatch):
    """A persistently offline device enters setup after all retries are exhausted."""
    calls = []
    monkeypatch.setattr(netifaces, 'connected_with_retry', lambda: calls.append('gate') or False)
    monkeypatch.setattr(setup, 'run', lambda **kwargs: calls.append(('setup', kwargs)))
    monkeypatch.setattr(streamer, 'run', lambda: calls.append('run'))

    commands.streamer_start()

    assert calls == ['gate', ('setup', {'role': 'streamer'}), 'run']


def test_player_start_runs_without_setup_when_the_retry_gate_passes(monkeypatch):
    calls = []
    monkeypatch.setattr(netifaces, 'connected_with_retry', lambda: calls.append('gate') or True)
    monkeypatch.setattr(setup, 'run', lambda **kwargs: calls.append(('setup', kwargs)))

    commands.player_start()

    assert calls == ['gate']


def test_player_start_enters_setup_when_the_retry_gate_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(netifaces, 'connected_with_retry', lambda: calls.append('gate') or False)
    monkeypatch.setattr(setup, 'run', lambda **kwargs: calls.append(('setup', kwargs)))

    commands.player_start()

    assert calls == ['gate', ('setup', {'role': 'player'})]
