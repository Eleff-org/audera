"""Audio-source catalog

`CATALOG` is the single definition of the audio sources Audera supports. Provisioning, the
Sources tab, the Players tab, and the rendered `snapserver.conf` all derive from it.

Three rules follow from upstream Snapcast behaviour.

1. A `SourceDefinition.id` is immutable. The id is the URI's `?name=` parameter and Snapcast has
   no separate stream id (`pcm_stream.cpp:118-127`), so renaming a source orphans every group
   Snapcast persisted against the old name in its own `server.json`. Change `label` instead.
2. At least one catalogued source must stay enabled. `getDefaultStream()` returns `nullptr` for
   an empty stream list and `server.cpp:393` dereferences it unconditionally at the first client
   connect, so a zero-stream conf crashes Snapserver.
3. `default_source` must always be set, and must name a stream the conf provides. Removing a
   stream reassigns its groups to `default_source` at client-connect time
   (`server.cpp:388-397`), and a value naming no live stream mis-routes them with no error, so
   `default_source()` derives it from the enabled set.
"""

from dataclasses import dataclass
from typing import Iterable, Literal

# The token every `uri` carries in place of the source id.
_ID_PLACEHOLDER = '{id}'


@dataclass(frozen=True)
class SourceDefinition:
    """A `class` that represents a single audio source Audera can run.

    Attributes
    ----------
    id: `str`
        The stable identifier. Immutable: it is also the Snapcast stream name and the key
        `~/.audera/sources.json` stores.
    label: `str`
        The display name shown in the Sources tab, e.g. `'Spotify Connect'`.
    uri: `str`
        The `snapserver.conf` source URI, with `'{id}'` standing in for `id`.
    units: `tuple[str, ...]`
        The systemd units Audera enables and disables alongside this source. Empty when
        Snapserver forks and reaps the backend itself.
    setup: `Literal['plex_claim'] | None`
        The post-enable configuration flow rendered on the source's card, if any.
    description: `str`
        The one-line description shown beneath the label in the Sources tab.
    """

    id: str
    label: str
    uri: str
    units: tuple[str, ...]
    setup: Literal['plex_claim'] | None
    description: str


# Order determines `default_source()`'s priority, `source_units()`'s start order, and the Sources
# tab's render order. AirPlay leads: it is the bootstrap source `dal.sources.DEFAULT_ENABLED`
# names, and leading puts `nqptp` first in the units provisioning starts, which AirPlay needs.
# Entries take keyword arguments, since three adjacent `str` fields make a positional swap silent.
CATALOG: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        id='AirPlay',
        label='AirPlay 2',
        # No `sampleformat`: `airplay://` rewrites the query to 44100:16:2 regardless
        # (`stream_manager.cpp:122-129`). `devicename` becomes shairport-sync's `--name`, which
        # is what iOS advertises; `name` is the Snapcast stream id and is never passed to the
        # binary. `port=7000` selects AirPlay 2; `5000` selects AirPlay 1 without warning.
        uri='airplay:///usr/local/bin/shairport-sync?name={id}&devicename=Audera&port=7000',
        units=('nqptp',),
        setup=None,
        description='Play from iPhone, iPad, or Mac',
    ),
    SourceDefinition(
        id='Spotify',
        label='Spotify Connect',
        uri=(
            'process:///usr/local/bin/go-librespot'
            '?name={id}'
            # go-librespot's pipe output is fixed at 44100/2; without this Spotify plays
            # at the wrong speed against the server default of 48000:16:2.
            '&sampleformat=44100:16:2'
            # No `params=--config_dir`. go-librespot computes that flag's default from
            # `os.UserConfigDir()` and returns its error before `flag.Parse` runs, so the flag is
            # unreachable without a `$HOME` and redundant with one. The `snapserver.service.d`
            # drop-in written by provisioning sets that `$HOME`.
            # How long the stream stays `playing` after the pipe goes quiet. Without it a
            # track gap flaps the status chip.
            '&dryout_ms=2000'
            # Watchdog off. A respawn during ordinary silence would drop an idle Spotify
            # Connect device's zeroconf advertisement.
            '&wd_timeout=0'
            # Snapserver forks go-librespot, so there is no unit for it and no `journalctl -u`
            # output; its stderr is the only record of why the backend failed.
            '&log_stderr=true'
        ),
        units=(),
        setup=None,
        description='Cast from any Spotify app on the network',
    ),
    SourceDefinition(
        id='PlexAmp',
        label='PlexAmp',
        # `mode=create` makes Snapserver own the fifo that `asound.conf` writes into.
        uri='pipe:///tmp/snapfifo?name={id}&sampleformat=48000:16:2&mode=create',
        units=('plexamp', 'plexamp-mdns'),
        setup='plex_claim',
        description='Plex library playback via PlexAmp headless',
    ),
)


def _uri(source: SourceDefinition) -> str:
    """Returns `source`'s URI with the `'{id}'` placeholder resolved.

    Parameters
    ----------
    source: `audera.domains.sources.catalog.SourceDefinition`
        An instance of a `SourceDefinition` object.
    """
    # `str.replace` rather than `%`-formatting, which the Spotify URI's literal `%20` would make
    # raise, or `.format`, which would require `{{`/`}}` doubling on any URI carrying a brace.
    return source.uri.replace(_ID_PLACEHOLDER, source.id)


def source_lines(enabled_ids: Iterable[str]) -> list[str]:
    """Returns the ordered, deduplicated `source =` lines for the enabled sources.

    The result always follows `CATALOG` order, so it is invariant to the order and multiplicity
    of `enabled_ids`. Ids naming no catalog entry are skipped, so a `sources.json` naming a
    retired source still renders.

    Parameters
    ----------
    enabled_ids: `Iterable[str]`
        The enabled source ids, e.g. from `audera.dal.sources.get_enabled()`.
    """
    enabled = set(enabled_ids)
    return [f'source = {_uri(source)}' for source in CATALOG if source.id in enabled]


def source_units(enabled_ids: Iterable[str], *, enabled: bool = True) -> list[str]:
    """Returns the systemd units of the enabled sources, or of every other catalogued source.

    In `CATALOG` order, so provisioning starts AirPlay's PTP clock before anything Snapserver
    forks. A source whose backend Snapserver forks itself has no units and contributes nothing to
    either answer. Ids naming no catalog entry are skipped.

    Parameters
    ----------
    enabled_ids: `Iterable[str]`
        The enabled source ids, e.g. from `audera.dal.sources.get_enabled()`.
    enabled: `bool`
        Whether to return the enabled sources' units, or the complement's.
    """
    ids = set(enabled_ids)
    return [unit for source in CATALOG for unit in source.units if (source.id in ids) is enabled]


def default_source(enabled_ids: Iterable[str]) -> str:
    """Returns the source id Snapserver falls back to for new and reassigned clients.

    The result is the first `CATALOG` entry present in `enabled_ids`. Returns `''` when the
    set is empty or names nothing catalogued, a state that `render_snapserver()` rejects.

    Parameters
    ----------
    enabled_ids: `Iterable[str]`
        The enabled source ids, e.g. from `audera.dal.sources.get_enabled()`.
    """
    enabled = set(enabled_ids)
    for source in CATALOG:
        if source.id in enabled:
            return source.id
    return ''
