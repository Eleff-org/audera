"""Bundled service configuration files, rendered from code.

This module is the single source of truth for the configuration files that
``audera {streamer,player} conf <filename>`` emits. Keeping them in code (rather
than as data files) lets the CamillaDSP playback format and the Snapserver source
list be parameterized while the remaining files stay byte-for-byte stable.
"""

from typing import Literal, Sequence

from audera.domains.sources import default_source, source_lines

# The Snapserver configuration's target path. Provisioning writes it through a shell redirect;
# the Sources tab re-renders it when a source is toggled.
SNAPSERVER_CONF: str = '/etc/snapserver.conf'


def render_camilladsp(playback_format: Literal['S16LE', 'S32LE'] = 'S32LE') -> str:
    """Renders the CamillaDSP configuration file.

    Parameters
    ----------
    playback_format : `Literal['S16LE', 'S32LE']`
        The playback device sample format. Defaults to ``'S32LE'``. HDMI sinks
        reject ``'S32LE'`` and must use ``'S16LE'`` (see ADR 003); the pipeline's
        effective ceiling is 16-bit/48 kHz (ADR 002), so ``'S16LE'`` loses no
        quality. The capture device stays ``'S32LE'`` to match Snapclient's
        32-bit loopback output.

    Returns
    -------
    `str`
        The rendered CamillaDSP configuration.
    """
    return f"""---
devices:
  samplerate: 48000
  chunksize: 1024
  
  # DRIFT: Enables monitoring the buffer level to sync Capture and Playback clocks.
  enable_rate_adjust: true
  
  # LATENCY STABILITY: Desired number of samples in the playback buffer. 
  # Set to equal chunksize for a balance of stability and low "blind" latency.
  target_level: 1024
  
  # REACTION SPEED: How often (in seconds) to calculate the correction ratio.
  # 5s is responsive enough for network streams without causing audible pitch "wobble."
  adjust_period: 5

  # RESAMPLER SETTINGS: Omit 'resampler' entirely to disable resampling and let ALSA's
  # internal clock handle adjustment — saves significant CPU power on the RPi Zero 2 W.
  # Uncomment and set a type if clicks/pops occur:
  #
  # resampler:
  #   type: FastAsync    # Pi Zero choice: least CPU, good for near-1:1 rate adjustment
  #   # type: BalancedAsync  # Higher quality; may spike CPU on Pi Zero 2 W
  #   # type: AccurateAsync  # Best quality; intended for Pi 4 or desktop PCs
  #   # capture_samplerate: 44100  # Uncomment if source is 44.1k and DAC is 48k

  # HDMI STABILITY: Keep the ALSA device open at all times to prevent HDMI audio dropout.
  # Closing the device after silence causes the HDMI sink to de-clock and drop the connection.
  silence_threshold: null   # keep ALSA device open, prevent HDMI dropout
  silence_timeout: null
  stop_on_rate_change: false

  capture:
    type: Alsa
    channels: 2
    device: "hw:Loopback,1"
    format: S32LE

  playback:
    type: Alsa
    channels: 2
    device: "hw:0" # Must match the DAC soundcard index
    format: {playback_format}

# Essential even if empty for the config to be valid
filters: {{}}

pipeline: []
"""


def render_snapserver(enabled: Sequence[str]) -> str:
    """Renders the Snapserver configuration file.

    A pure renderer: `enabled` is required rather than defaulted to the bootstrap set, so the
    output depends on the argument alone. `commands.py` passes `sources_dal.get_enabled()`.

    Parameters
    ----------
    enabled : `Sequence[str]`
        The enabled source ids. An empty sequence is rejected. Order and duplicates are ignored,
        and the rendered order is always the catalog's.

    Returns
    -------
    `str`
        The rendered Snapserver configuration.

    Raises
    ------
    `ValueError`
        When no catalogued source is enabled. Snapserver dereferences a null default stream at
        the first client connect, so a zero-stream configuration crashes it and is not emitted.
        It does not fall back to the bootstrap set, which would let the data-access layer and
        `/etc/snapserver.conf` disagree.
    """
    ids = list(enabled)

    # Guard on the rendered lines rather than on `ids`, so an enabled set naming only
    # uncatalogued sources is caught alongside an empty one.
    lines = source_lines(ids)
    if not lines:
        raise ValueError(f'At least one catalogued audio source must be enabled, got {ids!r}.')

    sources = '\n'.join(lines)
    # Derived rather than accepted as a parameter, so no caller can name a default no rendered
    # source provides, which Snapserver mis-routes without reporting an error.
    default = default_source(ids)

    # `rf` rather than `r`: any future brace in the literal below raises a `ValueError` at call
    # time.
    return rf"""

###############################################################################
#     ______                                                                  #
#    / _____)                                                                 #
#   ( (____   ____   _____  ____    ___  _____   ____  _   _  _____   ____    #
#    \____ \ |  _ \ (____ ||  _ \  /___)| ___ | / ___)| | | || ___ | / ___)   #
#    _____) )| | | |/ ___ || |_| ||___ || ____|| |     \ V / | ____|| |       #
#   (______/ |_| |_|\_____||  __/ (___/ |_____)|_|      \_/  |_____)|_|       #
#                          |_|                                                #
#                                                                             #
#  Snapserver config file                                                     #
#                                                                             #
###############################################################################

# default values are commented
# uncomment and edit to change them

# Settings can be overwritten on command line with:
#  "--<section>.<name>=<value>", e.g. --server.threads=4


# General server settings #####################################################
#
[server]
# Number of additional worker threads to use
# - For values < 0 the number of threads will be 2 (on single and dual cores)
#   or 4 (for quad and more cores)
# - 0 will utilize just the processes main thread and might cause audio drops
#   in case there are a couple of longer running tasks, such as encoding
#   multiple audio streams
threads = -1

# the pid file when running as daemon (-d or --daemon)
#pidfile = /var/run/snapserver/pid

# the user to run as when daemonized (-d or --daemon)
#user = snapserver
# the group to run as when daemonized (-d or --daemon)
#group = snapserver

# directory where persistent data is stored (server.json)
# if empty, data dir will be
#  - "/var/lib/snapserver/" when running as daemon
#  - "$HOME/.config/snapserver/" when not running as daemon
#
# Set explicitly rather than left empty. `server.json` here is where Snapcast persists what
# Audera does not store: client names, volumes, latencies, group membership, and each group's
# `stream_id`. An empty value resolves against `$HOME`, which provisioning sets on this unit for
# go-librespot, so changing that variable would make snapserver start from an empty state file
# with every player renamed back to its MAC. The value below is upstream's own daemon default.
datadir = /var/lib/snapserver/

# enable mDNS to publish services
#mdns_enabled = true
#
###############################################################################


# Secure Socket Layer #########################################################
#
[ssl]
# Certificate files are either specified by their full or relative path. Certificates with
# relative path are searched for in the current path and in "/etc/snapserver/certs"

# Certificate file in PEM format
#certificate =

# Private key file in PEM format
#certificate_key =

# Password for decryption of the certificate_key (only needed for encrypted certificate_key file)
#key_password =

# Verify client certificates
#verify_clients = false

# List of client CA certificate files, can be configured multiple times
#client_cert =
#client_cert =
#
###############################################################################


# HTTP RPC ####################################################################
#
[http]
# enable HTTP Control and streaming (HTTP POST and websockets)
enabled = true

# address to listen on, can be specified multiple times
# use "0.0.0.0" to bind to any IPv4 address or :: to bind to any IPv6 address
# or "127.0.0.1" or "::1" to bind to localhost IPv4 or IPv6, respectively
# use the address of a specific network interface to just listen on and accept
# connections from that interface
bind_to_address = 0.0.0.0

# which port the server should listen on
port = 1780

# Publish HTTP service via mDNS as '_snapcast-http._tcp'
#publish_http = true

# enable HTTPS Json RPC (HTTPS POST and ssl websockets)
#ssl_enabled = false

# same as 'bind_to_address' but for SSL
#ssl_bind_to_address = ::

# same as 'port' but for SSL
#ssl_port = 1788

# Publish HTTPS service via mDNS as '_snapcast-https._tcp'
#publish_https = true

# serve a website from the doc_root location
# disabled if commented or empty
doc_root = /usr/share/snapserver/snapweb

# Hostname or IP under which clients can reach this host
# used to serve cached cover art
# use <hostname> as placeholder for your actual host name
#host = <hostname>

# Optional custom URL prefix for generated URLs where clients can reach
# cached album art, to e.g. match scheme behind a reverse proxy.
#url_prefix = https://<hostname>
#
###############################################################################


# TCP #########################################################################
#
[tcp-control]
# enable TCP Json RPC
enabled = true

# address to listen on, can be specified multiple times
# use "0.0.0.0" to bind to any IPv4 address or :: to bind to any IPv6 address
# or "127.0.0.1" or "::1" to bind to localhost IPv4 or IPv6, respectively
# use the address of a specific network interface to just listen on and accept
# connections from that interface
bind_to_address = 0.0.0.0

# which port the control server should listen on
port = 1705

# Publish TCP control service via mDNS as '_snapcast-ctrl._tcp'
#publish = true

[tcp-streaming]
# enable TCP streaming
#enabled = true

# address to listen on, can be specified multiple times
# use "0.0.0.0" to bind to any IPv4 address or :: to bind to any IPv6 address
# or "127.0.0.1" or "::1" to bind to localhost IPv4 or IPv6, respectively
# use the address of a specific network interface to just listen on and accept
# connections from that interface
#bind_to_address = ::

# which port the streaming server should listen on
#port = 1704

# Publish TCP streaming service via mDNS as '_snapcast._tcp'
#publish = true
#
###############################################################################


# Stream settings #############################################################
#
[stream]
# source URI of the PCM input stream, can be configured multiple times
# The following notation is used in this paragraph:
#  <angle brackets>: the whole expression must be replaced with your specific setting
# [square brackets]: the whole expression is optional and can be left out
# [key=value]: if you leave this option out, "value" will be the default for "key"
#
# Format: TYPE://host/path?name=<name>[&codec=<codec>][&sampleformat=<sampleformat>][&chunk_ms=<chunk ms>][&controlscript=<control script filename>[&controlscriptparams=<control script command line arguments>]]
#  parameters have the form "key=value", they are concatenated with an "&" character
#  parameter "name" is mandatory for all sources, while codec, sampleformat and chunk_ms are optional
#  and will override the default codec, sampleformat or chunk_ms settings
# Available types are:
# pipe: pipe:///<path/to/pipe>?name=<name>[&mode=create], mode can be "create" or "read"
# librespot: librespot:///<path/to/librespot>?name=<name>[&username=<my username>&password=<my password>][&devicename=Snapcast][&bitrate=320][&wd_timeout=7800][&volume=100][&onevent=""][&normalize=false][&autoplay=false][&params=<generic librepsot process arguments>]
#  note that you need to have the librespot binary on your machine
#  sampleformat will be set to "44100:16:2"
# file: file:///<path/to/PCM/file>?name=<name>
# process: process:///<path/to/process>?name=<name>[&wd_timeout=0][&log_stderr=false][&params=<process arguments>]
# airplay: airplay:///usr/local/etc/shairport-sync.conf?name=Bathroom[&port=7000]
#  note that you need to have the airplay binary on your machine
#  sampleformat will be set to "44100:16:2"
# tcp server: tcp://<listen IP, e.g. 127.0.0.1>:<port>?name=<name>[&mode=server]
# tcp client: tcp://<server IP, e.g. 127.0.0.1>:<port>?name=<name>&mode=client
# alsa: alsa:///?name=<name>&device=<alsa device>[&send_silence=false][&idle_threshold=100][&silence_threshold_percent=0.0]
# meta: meta:///<name of source#1>/<name of source#2>/.../<name of source#N>?name=<name>
{sources}

# The name of the default source for new clients to connect to
# Otherwise defaults to first non-meta source
default_source = {default}

# Plugin directory, containing scripts, referred by "controlscript"
#plugin_dir = /usr/share/snapserver/plug-ins

# Sandbox directory, containing executables, started by "process" and "librespot" streams
#sandbox_dir = /usr/share/snapserver/sandbox

# Default sample format: <sample rate>:<bits per sample>:<channels>
#sampleformat = 48000:16:2

# Default transport codec
# (flac|ogg|opus|pcm)[:options]
# Start Snapserver with "--stream:codec=<codec>:?" to get codec specific options
#codec = flac

# Default source stream read chunk size [ms].
# The server will continously read this number of milliseconds from the source into buffer and pass this buffer to the encoder.
# The encoded buffer is sent to the clients. Some codecs have a higher latency and will need more data, e.g. Flac will need ~26ms chunks
#chunk_ms = 20

# Buffer [ms]
# The end-to-end latency, from capturing a sample on the server until the sample is played-out on the client
#buffer = 1000

# Send audio to muted clients
#send_to_muted = false
#
###############################################################################


# Streaming client options ####################################################
#
[streaming_client]

# Volume assigned to new snapclients [percent]
# Defaults to 100 if unset
#initial_volume = 100
#
###############################################################################


# Logging options #############################################################
#
[logging]

# log sink [null,system,stdout,stderr,file:<filename>]
# when left empty: if running as daemon "system" else "stdout"
#sink =

# log filter <tag>:<level>[,<tag>:<level>]*
# with tag = * or <log tag> and level = [trace,debug,info,notice,warning,error,fatal]
#filter = *:info
#
###############################################################################
"""


def render_go_librespot() -> str:
    """Renders the go-librespot (Spotify Connect) configuration file.

    Rendered once at provision time into `/var/lib/snapserver/.config/go-librespot`, which
    go-librespot derives from `$HOME`, set on Snapserver's unit by a provisioning drop-in. The
    content is static, so it does not change when the source is enabled or disabled.

    Returns
    -------
    `str`
        The rendered go-librespot configuration.
    """
    return r"""---
device_name: Audera
device_type: speaker

# Spotify's highest tier, and the ceiling for this source, since the pipe below is
# lossless from here on.
bitrate: 320

# Snapserver reads the child process's stdout, so the pipe backend writes there.
# `s16le` must agree with the Spotify source URI's `sampleformat=44100:16:2` in
# audera/domains/sources/catalog.py. Neither side validates the other, and a mismatch
# produces a byte-misaligned stream, which is audible distortion rather than an error.
audio_backend: pipe
audio_output_pipe: /dev/stdout
audio_output_pipe_format: s16le

# Loudness levelling, per song rather than per album, so every track reaches Snapserver
# at the same loudness. Snapcast's documented `+6.0` pregain is not adopted: the DSP
# editor's auto-protected pre-amp computes clip-safe headroom from the EQ bands alone and
# does not account for gain applied upstream of it.
normalisation_disabled: false
normalisation_use_album_gain: false
normalisation_pregain: 0.0

# Both of the next two default to `false` upstream. Zeroconf is how the speaker is
# discovered on the network, and persisting the credentials it receives lets a disabled
# source be re-enabled without re-pairing from a phone.
zeroconf_enabled: true

# Registers the `_spotify-connect._tcp` service through the running avahi-daemon over D-Bus
# instead of go-librespot's own mDNS responder, the `builtin` default. There is no
# auto-detection; `zeroconf/zeroconf.go:67` branches on this key alone. Upstream reserves
# `builtin` for hosts with no avahi; this host runs avahi for AirPlay, `plexamp-mdns`, and
# `audera.local`.
zeroconf_backend: avahi

credentials:
  type: zeroconf
  zeroconf:
    persist_credentials: true

# go-librespot's HTTP API. Its only consumer would be now-playing metadata, which is out
# of scope for beta.1 and requires snapserver >= 0.34's bundled meta_go-librespot.py.
server:
  enabled: false
"""


def render_asound() -> str:
    """Renders the ALSA (asound) configuration file.

    Returns
    -------
    `str`
        The rendered ALSA configuration.
    """
    return r"""
pcm.snapcast_format {
    type plug
    slave {
        pcm "snapcast_raw"
        format "S16_LE"
        rate 48000
        channels 2
    }
}

pcm.snapcast_raw {
    type file
    slave.pcm "null"
    file "/tmp/snapfifo"
    format "raw"
}

pcm.plexamp_output {
    type plug
    slave.pcm "snapcast_format"
    hint {
        show on
        description "Snapcast"
    }
}

"""
