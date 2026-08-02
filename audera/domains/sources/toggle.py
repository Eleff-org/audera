"""Applying a source toggle to the host.

The `page`-free middle of the Sources tab's enable/disable choreography, which is the part of it
that qualifies as a host-level side effect. The lock, the data-access-layer write, group
reassignment, the readiness wait, and the notifications stay with the handlers, which read
`page`.

The `domains -> cli` import edge below mirrors the `ui -> cli` one `index` already carries.
`cli.conf` is the rendered-configuration module and imports only from `dal` and
`domains.sources.catalog`, so nothing here closes a cycle. `domains/sources/__init__.py` must
not import this module.
"""

from audera import io
from audera.cli import conf
from audera.domains.sources.catalog import SourceDefinition
from audera.services import system

# `conf` and `system` are imported as modules rather than by name so `conf.SNAPSERVER_CONF`,
# `conf.render_snapserver` and `system.systemctl` resolve at call time. Each names something this
# module does not own — `/etc/snapserver.conf` and the init system — and binding them at import
# would fix the choreography to one machine's copy of both.


def apply(source: SourceDefinition, enable: bool, enabled_ids: list[str]) -> None:
    """Writes `snapserver.conf`, moves `source`'s units, and restarts Snapserver.

    The conf is on disk before the restart that reads it, so the streams Snapserver serves
    afterwards match the file. `tests/systemd/inside/test_index.py` asserts that ordering by its
    effect on the served streams.

    Blocking, and called through `asyncio.to_thread` by both handlers. Every step is idempotent,
    so a retry after a partial failure is safe. Failures propagate to the caller, which knows
    which half of the choreography it was in.

    Parameters
    ----------
    source: `audera.domains.sources.catalog.SourceDefinition`
        The catalog entry being toggled.
    enable: `bool`
        Whether the source is being enabled. Selects `enable --now` or `disable --now` for the
        source's units; the conf write and the restart are the same either way, since the conf
        is derived wholly from `enabled_ids`.
    enabled_ids: `list[str]`
        The enabled source ids the conf is rendered from. The set the data-access layer just
        returned, rather than a read-back, so the conf matches the set the caller recorded.
    """
    _write_snapserver_conf(enabled_ids)

    # Every start counts against the unit's start rate limit, manual starts included, and both
    # `snapserver` and a source's units inherit the manager's default of five starts per ten
    # seconds. One toggle restarts Snapserver once, so a sixth toggle inside the interval is
    # refused with `start-limit-hit`, which `Restart=on-failure` cannot recover from, since the
    # limit is what refused the start. Clearing the counters keeps a dead Snapserver recoverable
    # from the UI.
    #
    # Cleared before the units move, so a `failed` that a stop below produces survives as a
    # `failed`. `check=False`: clearing a counter that was never tripped must not fail a toggle.
    # The limit is not disabled per-unit with `StartLimitIntervalSec=0`, since it is the backstop
    # on the crash loop `os/dietpi/AGENTS.md` records, and it could not cover `nqptp`, whose unit
    # file apt owns.
    system.systemctl('reset-failed', *source.units, 'snapserver', check=False)

    # Sources whose backend Snapserver forks itself have no units (`SourceDefinition.units` is
    # empty for Spotify), which makes the restart below the only step that starts or reaps them.
    verb = 'enable' if enable else 'disable'
    for unit in source.units:
        system.systemctl(verb, '--now', unit)

    system.systemctl('restart', 'snapserver')


def _write_snapserver_conf(enabled_ids: list[str]) -> None:
    """Renders `snapserver.conf` for `enabled_ids` and writes it to `conf.SNAPSERVER_CONF`.

    Renders and writes in one helper, so no caller can write a configuration it did not render.
    `conf.render_snapserver`'s `ValueError` is not caught here; the "at least one enabled" guard
    fires upstream.

    Parameters
    ----------
    enabled_ids: `list[str]`
        The enabled source ids.
    """
    # Rendered before anything opens the destination, and moved into place, so a raise from the
    # render leaves the running conf intact rather than a zero-byte file and a Snapserver that
    # will not start. `io.write_text` states the encoding, which the platform default leaves
    # locale-derived; a device whose locale is not UTF-8 would otherwise fail this write after
    # the data-access-layer write, past the abort point, leaving the enabled set and the conf
    # disagreeing.
    io.write_text(conf.SNAPSERVER_CONF, conf.render_snapserver(enabled_ids))
