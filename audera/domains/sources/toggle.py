"""Applying a source toggle to the host.

The `page`-free middle of the Sources tab's enable/disable choreography. The lock, the
data-access-layer write, group reassignment, the readiness wait, and the notifications stay with
the handlers, which read `page`.

`domains/sources/__init__.py` must not import this module. The `domains -> cli` import edge below
mirrors the `ui -> cli` one `index` already carries; `cli.conf` imports only from `dal` and
`domains.sources.catalog`, so nothing here closes a cycle.
"""

from audera import io
from audera.cli import conf
from audera.domains.sources.catalog import SourceDefinition
from audera.services import system

# `conf` and `system` are imported as modules rather than by name so `conf.SNAPSERVER_CONF`,
# `conf.render_snapserver` and `system.systemctl` resolve at call time and can be patched on their
# own modules.


def apply(source: SourceDefinition, enable: bool, enabled_ids: list[str]) -> None:
    """Writes `snapserver.conf`, moves `source`'s units, and restarts Snapserver.

    The conf must be on disk before the restart that reads it, so the streams Snapserver serves
    afterwards match the file.

    Blocking, and called through `asyncio.to_thread` by both handlers. Every step is idempotent,
    so a retry after a partial failure is safe. Failures propagate to the caller.

    Parameters
    ----------
    source: `audera.domains.sources.catalog.SourceDefinition`
        The catalog entry being toggled.
    enable: `bool`
        Whether the source is being enabled. Selects `enable --now` or `disable --now` for the
        source's units; the conf write and the restart are the same either way.
    enabled_ids: `list[str]`
        The enabled source ids the conf is rendered from. Passed in rather than read back, so the
        conf matches the set the caller recorded.
    """
    _write_snapserver_conf(enabled_ids)

    # Manual starts count against a unit's start rate limit, and both `snapserver` and a source's
    # units inherit the manager's default of five starts per ten seconds. Each toggle restarts
    # Snapserver once, so without this the sixth toggle inside the interval is refused with
    # `start-limit-hit`, which `Restart=on-failure` cannot recover from. Cleared before the units
    # move, so a `failed` produced by a stop below survives. `check=False`, since clearing a
    # counter that was never tripped must not fail a toggle. The limit is not disabled per-unit
    # with `StartLimitIntervalSec=0`; it is the backstop on the crash loop `os/dietpi/AGENTS.md`
    # records, and it could not cover `nqptp`, whose unit file apt owns.
    system.systemctl('reset-failed', *source.units, 'snapserver', check=False)

    # A source whose backend Snapserver forks itself has no units, so the restart below is the
    # only step that starts or reaps it.
    verb = 'enable' if enable else 'disable'
    for unit in source.units:
        system.systemctl(verb, '--now', unit)

    system.systemctl('restart', 'snapserver')


def _write_snapserver_conf(enabled_ids: list[str]) -> None:
    """Renders `snapserver.conf` for `enabled_ids` and writes it to `conf.SNAPSERVER_CONF`.

    Renders and writes in one helper, so no caller can write a configuration it did not render.
    `conf.render_snapserver`'s `ValueError` is not caught here, since the "at least one enabled"
    guard fires upstream.

    Parameters
    ----------
    enabled_ids: `list[str]`
        The enabled source ids.
    """
    # Rendered before anything opens the destination and moved into place, so a raise from the
    # render leaves the running conf intact rather than a zero-byte file Snapserver cannot start
    # from. `io.write_text` also fixes the encoding, which the platform default leaves
    # locale-derived.
    io.write_text(conf.SNAPSERVER_CONF, conf.render_snapserver(enabled_ids))
