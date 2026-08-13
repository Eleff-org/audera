# AGENTS.md

## Package layout

List @audera/ui for the Python package layout.

## App pattern

Every UI app follows this two-file pattern:

**`pages.py`** — contains a `Page` class:
- `__init__`: loads that client's state (settings, flags); no platform decorator unless dietpi-only
- `load()`: registers routes, and runs whatever belongs to the process rather than to a page load
- Page methods: one per route (e.g. `index()`, `welcome()`, `connect()`)
- Tab builder methods: `_build_<name>_tab()` — private, called from a page method

**One `Page` per connected client.** `load()` registers route closures that each build their own, and publish it on `app.storage.client['page']` for `current()`. `run()`'s instance only calls `load()`; it renders nothing. A `Page` shared across clients is a correctness bug, not just contention:

- `@ui.refreshable` keys its render targets on the bound instance and on **nothing else** (`refreshable._execute_refresh` filters `target.instance != instance`). One instance makes every `refresh()` a broadcast that clears every open browser's tab.
- Re-entrancy guards on `Page` then guard the wrong scope. `_players_generation` is stamped per build and compared after each `await`; shared, it is a counter that builds in *different* browsers race on, and the loser returns having rendered nothing — an empty tab until that client reloads.
- Latches on `Page` become cross-client freezes: one operator's open menu (`_dialog_open`) would suspend everyone's poll, and one operator's Plex OAuth (`_claim_in_flight`) would refuse everyone's source toggles.

Anything genuinely process-scoped goes in `load()` or at module level, not on the instance — `index.adopt_running_sources` is there because it is a blocking Snapserver read that reconciles the device once, and the command queue (`commands.py`) is a module-level singleton because it serializes host mutations across every client. The cost of a per-client `Page` is `_load_settings()`, one JSON read per page load; in exchange a settings edit is picked up on the next load rather than never.

`tests/ui/test_streamer.py`'s `_page(user)` is how a test reaches the instance the render path holds — the one it constructs to call `load()` is not it.

`ui/setup` is the one app that still shares an instance, and it goes further — it stores live `ui.element` handles on `self` (`network_selector`, `password_input`), which a second browser would overwrite. It is single-client by construction: it serves one onboarding browser over its own access point, and the device leaves setup mode once that browser finishes. Give it the same treatment before it is ever reachable from the LAN.

**`pages/` sub-package** — when `pages.py` grows past a few hundred lines, split it into a `pages/` package instead of one flat file:
- `pages/__init__.py`: the thin `Page` class (`__init__`, `load()`) re-exported so `from …pages import Page` is unchanged. Each route method delegates to a module-level `render(page, …)` — e.g. `def dsp(self, player_id): dsp.render(self, player_id)`.
- One module per route (`pages/index.py`, `pages/dsp.py`, …): a `render(page, …)` function plus that route's private `_build_<name>_tab(page)` / `_on_<action>(page, …)` helpers. `page` carries that client's state (`page.settings`, `page._dialog_open`); the `Page` class is **not** split across files. `@ui.refreshable` helpers stay module-level, keyed on the `page` argument, and are refreshed via `_build_<name>_tab.refresh()`.
- Private helper modules (`pages/_clients.py`, `pages/_plex.py`, …): shared client factories and self-contained flows, imported by the route modules. To avoid an import cycle, route modules never import names from `pages/__init__.py` at runtime — they take `page` as an argument and import `Page` only under `TYPE_CHECKING`.

**`__init__.py`** — thin `run()` entry point only:
```python
def run() -> None:
    page = Page()
    page.load()
    components.theme.apply_defaults()
    try:
        ui.run(...)
    except KeyboardInterrupt:
        app.shutdown()
```

No implementation logic belongs in `__init__.py`.

## NiceGUI conventions

- **Page registration**: `ui.page(route)(self.method)` inside `load()`
- **Refreshable sections**: `@ui.refreshable` on tab-builder methods; call `self._build_<name>_tab.refresh()` to re-render
- **Reactive binding**: `bind_visibility_from(obj, 'attr', backward=fn)`, `bind_enabled_from(obj, 'attr', backward=fn)`
- **Async operations**: page and callback methods marked `async`; blocking I/O wrapped in `asyncio.to_thread()`
- **Polling timers**: `ui.timer(interval, callback, once=False)`; store handle in a `list[ui.timer]` when the reference is needed inside the callback
- **Notifications**: `ui.notify(message, position='top-right', type='positive'|'negative'|'warning')`

## Components

- `header.render(title, subtitle)` — renders the app header bar
- `theme.apply_defaults()` — applies the dark colour palette; call once in `run()` before `ui.run()`
- `theme.PRIMARY / SECONDARY / ACCENT / TEXT` — colour constants for consistent styling

## Code style (UI additions)

- Private tab builders: `_build_<name>_tab()` naming convention
- Async callbacks inside tab builders: `_on_<action>()` for user-triggered events, `_poll_<thing>()` for timer callbacks
- Tailwind utility classes for layout; keep consistent with existing NiceGUI patterns in the codebase
- No `ui.run()` calls outside of `__init__.py`
- Module-level helpers (no instance state needed) stay as module-level private functions, not `@staticmethod`

## UX optionality

Features with more than one valid UX ("mute checkbox vs. disabled toggle") are registered in `audera/ui/features.py`'s `FEATURES` catalog, not hard-coded as a single rendering path. Every feature ships 2-3 `Option`s; the first is the default. Resolve a user's selection with `audera.ui.features.selected(settings, key)` or `flag_enabled(settings, key, option)` — never read `settings.features[...]` directly.

When asked to implement a new UI feature, treat optionality as the default, not an afterthought: if there's more than one defensible UX for it, propose a `Feature` catalog entry (or ask the user which options to offer) before picking one and hard-coding it. Only skip the catalog when a feature genuinely has one correct UX with no reasonable alternative.

A new `FEATURES` entry names every option with an `FF_*` constant (ADR 004 §2); `player_grouping` and `dsp_band_editor` follow this. `player_selection` and `volume` predate the ADR and still use bare literals.

The Sources tab has no `FEATURES` entry. Its two candidates, the "at least one source stays enabled" guard and reassigning listeners before their stream stops existing, are correctness guards rather than options: a zero-stream `snapserver.conf` crashes Snapserver at the first client connect, and a stream removed under a live group mis-routes it with no error.

## Catalog-driven tabs

The Sources tab renders from `audera.domains.sources.CATALOG` rather than from a hand-written list of cards. Rules that follow:

- Iterate the catalog and filter by the enabled set, not the reverse. `dal.sources.get_enabled()` stores whatever was toggled and does not filter, so intersect it with `CATALOG` at the point of use (`index._enabled_ids`). An id left behind by a removed catalog entry must render no card and must not count toward the "at least one enabled" guard.
- A source's id, label, URI, and units are not restated in the UI. A control offering destinations maps id → label, renders the label, and sends the id to `Group.SetStream`; the two differ (`Spotify` vs. `Spotify Connect`), and sending the label mis-routes with no error. See the root `AGENTS.md` § Audio sources for the source/stream split.
- Dispatch per-source variation through a table keyed on the catalog's discriminator rather than an `if` chain. `index._SETUP_FLOWS` maps `SourceDefinition.setup` to a `(state, build)` pair. An unrecognised discriminator fails open, showing the stream's real status instead of leaving the card in `setup required` indefinitely; an exception from a flow that does exist fails closed on `_SETUP_REQUIRED`.
- A flow reports a chip label rather than a boolean, since a flow can have more than one incomplete state. `state()` returns `str | None`: `None` once setup is done, otherwise the word the chip shows. PlexAmp has two: `setup required` for a device that was never claimed, and `starting` for one that systemd has started but that has not bound its port yet. The card builder resolves the label once and passes it to both the chip and `build(page, pending)`, so the panel switches on the same word the chip is showing. The label is the flow's own constant, which keeps `_plex` from importing from `index`.

The tab is not polled. `index.render`'s 10 s timer refreshes the Players tab only: polling the Sources tab would put `get_stream_status()`, and with PlexAmp enabled a `systemctl is-active`, on a 10 s loop, and would cancel the PlexAmp claim flow's own timers every tick. The chips refresh explicitly at load, after each toggle, at claim completion, and on re-entry to the tab.

`_plex._build_starting_panel` is the one exception, and its poll is bounded: `_plexamp_state` stops answering `'starting'` once the port opens or `STARTUP_GRACE` passes, and the refresh that replaces the panel deletes the timer with it. Anything else added here needs the same two properties: a state no other path can observe, and a condition that ends the poll.

Re-entry keeps an unpolled tab from staying stale until the next reload. NiceGUI builds every tab panel eagerly at page load, so a status word that changed while the operator was on another tab has no other path to update. `index.render`'s `tabs.on_value_change` handler performs one read per return, with two refusals:

- The first activation does not repaint. That panel is as fresh as the page, and `refreshable.refresh()` defers the rebuild to a background task rather than running it inline, so an unconditional repaint deletes the source card out from under a toggle the operator clicked on arriving and the handler already running on it raises `RuntimeError: The parent element this slot belongs to has been deleted`. An `entered_sources` latch skips the first entry.
- A claim in flight refuses the repaint, with no notification, since a repaint deletes the claim flow's elements and cancels its timers.

`ui.tabs.on_value_change` reports the tab name rather than the `ui.tab` element, so the handler and the constructor must agree on a string; `_PLAYERS_TAB` / `_SOURCES_TAB` / `_SETTINGS_TAB` state each once.

## Players tab layouts

The Players tab renders under `player_grouping`: **by player** (a flat list of cards) or **by stream** (the same cards nested under a header per stream). One card builder serves both.

- Fetch once per render, not per card. `build_players_tab` makes every Snapcast read (`get_clients()`, `get_groups()`, and `get_stream_status()`) and passes the result down as a per-card `_Assignment`, built by the I/O-free `_assignment()`. A card that issues a read of its own multiplies the poll by the number of players.
- Every read goes off-thread, runs concurrently, and is bounded, because the page builder is `async`. Both service clients connect with a 5 s `open_timeout`, and the builder runs on the event loop that serves every session, so one unreachable host would otherwise hold the whole UI. The page uses `asyncio.to_thread` per read, `asyncio.gather` per round, and `index._READ_TIMEOUT` over each round. The ceiling exists for NiceGUI: an `async` page builder that has not returned by `response_timeout` (3 s, and this page takes the default) is cancelled and its client deleted, so an overrun renders no page at all rather than a degraded tab. `wait_for` cancels the await rather than the worker thread, which keeps blocking until its own `open_timeout`, leaving an orphaned thread and an unblocked event loop.
- An `async` `@ui.refreshable` is not re-entrant, where a synchronous one is. `_execute_refresh` clears the target's container and then runs the builder inline when it is sync, but as a background task when it is `async`, so two refreshes in the same tick both clear and then both append and every element renders twice. The 10 s poll and any handler that refreshes are such a pair. `build_players_tab` stamps `Page._players_generation` before its first `await` and returns at each resumption point where a newer build has since started. Anything else made `async` behind a refreshable needs the same guard.
- The volume slider is seeded at construction and never written to afterwards. `on_change` is its write path to CamillaDSP and to Snapcast's mute state, so a programmatic `set_value()` is indistinguishable from a drag: it pushes volume to the hardware and clears mute. Constructing the element with a `value=` does not fire it, and the seed is step-aligned to the integer slider, since an unaligned one fires a phantom `update:model-value` on the next refresh. A fresher reading therefore reaches the UI by rebuilding the card rather than by updating it in place, so any scheme for deferring the volume read has to land in the cache and wait for a rebuild rather than touch a live element. `test_players_tab_disabled_experience_toggle_off_mutes_client` catches a violation: it touches no slider and still sees `set_client_volume`.
- An unreadable volume is withheld rather than defaulted. `_volumes` reports `None` and the card renders a disabled slider labelled `—`, with no Mute binding to re-enable it. A `DEFAULT_PERCENT_VOLUME` fallback draws a slider at 25%, indistinguishable from a player genuinely at 25% and the base a drag would then write against.
- `get_stream_status()` is read under both layouts, because liveness gates attachment as well as the by-stream header's status word. If the 10 s poll ever shows up in a profile, the agreed remedy is one new client method returning clients and groups together, rather than a second payload parser in the page or a `stream_id` on `Player`, which would replicate state Snapcast owns.
- Two triggers share one menu, and only one of them is active at a time. `_build_move_menu` is single-copy; `by_stream` selects which element opens it, and is consulted at two points in `_build_player_card`. The chip is a body row, so a minimized card drops it; the move button is a header-row button beside DSP and settings, so a minimized card keeps it disabled. `_move_refusal` is likewise shared, so both triggers refuse on the same grounds (no group, or no attachable destination) and only the rendering of the refusal differs.
- A destination Snapserver is not feeding is shown disabled beside its status word rather than dropped, so the reason is visible. That is also why the menu serves both layouts: a `ui.select` over a `dict[id, label]` cannot disable a single option.
- Refresh only when the layout encodes the change. By stream, a card's position is its assignment, so a move must re-render. By player, the chip repaints its own label and tint in place, because a refresh reseeds every volume slider from CamillaDSP and cancels a live drag on a different card. Both layouts refresh on failure, so the control returns to the server's state; `_on_stream_change` returns a `bool` for that reason, since an in-place repaint must not touch its own elements after a failure has already replaced them.
- Clear `_dialog_open` before refreshing, not after. Both triggers latch it while the menu is open so the poll cannot destroy it mid-interaction, and a flag latched by an element the refresh deleted freezes the poll for the life of the page. `ui.menu.on_value_change` covers open and close in one event, where the select it replaced needed Quasar's `popup-show`/`popup-hide` pair.
- Destinations are the enabled set ∩ `CATALOG`, plus the current stream when it is not in that set. The current stream leads the list and is what the chip names; a chip reading `Unassigned` for a player parked on an uncatalogued stream would be false. `_move_destinations` then drops the current stream from the menu, since selecting it is not a move, and `_sections` gives that stream its own header.
- A per-client control carries the client id in its marker. `UserInteraction.click()` fires on every match, so a shared marker on a per-card control makes a test act on all cards as soon as a second player exists. Carry both markers, `mark(f'player-dsp player-dsp-{id}')`, since `Element.mark()` splits on whitespace and `ElementFilter` matches on any one marker.

## Host mutations

UI code never calls `subprocess` directly; every systemd interaction goes through `audera.services.system` (see the root `AGENTS.md` for why the seam exists). The Sources tab does not call that seam itself either: `domains.sources.toggle.apply` holds the conf write, the units and the restart, and `index._enable_source` / `_disable_source` keep only what needs `page`. Beyond that:

- `/etc/` targets are module constants, referenced by attribute. Import the module (`from audera.cli import conf`) and read `conf.SNAPSERVER_CONF` at call time, so a test can redirect the write into `tmp_path`. `from audera.cli.conf import SNAPSERVER_CONF` binds the device path at import and writes to the real file under test.
- Notifications read `getattr(exc, 'stderr', '') or str(exc)`. `getattr` rather than `exc.stderr` because `@platform.requires('dietpi')` raises `RuntimeError`, which has no `stderr`; reading it directly raises `AttributeError` inside the handler on every dev-box toggle.
- Order the choreography so it rolls forward, with a single abort point. The data-access layer goes first because the enabled set is the intent and `/etc/snapserver.conf` is derived from it; the restart goes last, when every input it reads is already on disk. On the disable path, reassigning listeners is the only abort point: before the DAL write, aborting changes nothing, and after the conf is written the stream no longer exists to reassign anyone off. Steps past that point notify with `type='negative'` and leave the new state rather than unwinding.
- Wait for the restarted Snapserver before repainting anything that reads it. `systemctl restart snapserver` returns once systemd has forked the process, not once it is serving; the unit declares no readiness protocol, so the JSON-RPC socket refuses connections for seconds afterwards and a refresh inside that window renders every enabled source `not running`. `index._await_snapserver` polls `Server.GetStatus` off-thread until it answers or `_READY_TIMEOUT` passes, and runs outside the command queue so it does not block other commands. A non-empty status is a sound readiness signal only because of `CATALOG`'s rule 2: the conf just loaded always names a stream, so `{}` means unreachable. It returns rather than raises on timeout, since `not running` is then the correct chip.
- Guards that protect an invariant are re-read inside the queue. The disabled switch and the pre-dialog check are both decided against a render that may be seconds stale; only the check taken inside `_disable_source_write`, against a freshly read enabled set, enforces the invariant.
- A dev box behaves differently from the device. `sources_dal.set_enabled` is plain JSON under `~/.audera` and has no platform gate, so a source toggle on a developer's machine mutates `~/.audera/sources.json` and only then fails at the `/etc/` write or the `systemctl` call, leaving the enabled set changed.

## Previewing UI changes (screenshot loop)

The user iterates on UI from screenshots. Most player UI only renders with live Snapcast clients, so preview a component in isolation rather than the full app:

1. Write a throwaway `_preview.py` at the repo root that reproduces the exact widget/props against `components.theme.apply_defaults()`. Reuse **port 8080** every run so the user doesn't open new browser tabs.
2. Run it as a **background task** (not `foo &`) so it can be killed cleanly. `uv run python`'s child process holds the socket, and a stray one causes a port conflict (WinError 10048) on the next run — stop it with the task tooling, not `kill`.
3. Screenshot headless and review, then iterate:
   ```bash
   "/c/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu --screenshot=/tmp/preview.png --force-device-scale-factor=4 --virtual-time-budget=4000 http://127.0.0.1:8080
   ```
   `--force-device-scale-factor` zooms for pixel inspection; `--virtual-time-budget` gives Material Symbols web-fonts time to load.
4. **Clean up before committing**: stop the background server, delete `_preview.py`, and free port 8080. The harness is never committed.

The real app runs with `reload=False`, so the user restarts it to see applied changes.

## Event broker

`audera/ui/streamer/broker.py` brokers events from two sources — Snapserver (persistent WebSocket) and local metadata (volume DAL) — into a single cache the UI reads from.

- **Singleton.** `broker.start(host, port)` creates the module-level `EventBroker` instance on `app.on_startup`. `broker.get()` returns it; `broker.stop()` tears it down on `app.on_shutdown`.
- **Persistent async WebSocket.** A reader task holds a `websockets.asyncio.client.connect` to `ws://host:1780/jsonrpc`. Writes use short-lived connections via `_call` (Snapserver's `excludeSession` excludes the writing socket from notifications).
- **`broker.Cache`.** A mutable cache of `clients`, `groups`, `stream_status`, and `volumes`. `build_players_tab` reads this directly; no async I/O is needed.
- **Seed then delta.** `Server.GetStatus` on connect seeds the cache. Notifications update it in place. `Client.OnConnect` reseeds via a short-lived connection (the new client's state is not in the payload).
- **Diff before signal.** `snapshot()` returns an immutable tuple. After every notification, compare against the prior snapshot; signal dirty only on change. An idle system does not rebuild.
- **Debounce.** 250 ms quiet period before invoking dirty callbacks.
- **Reconnect.** Exponential backoff from 1 s to 30 s.

## Command queue

`audera/ui/streamer/commands.py` serializes all UI write paths — Snapserver RPCs, CamillaDSP pushes, DAL saves, systemd toggles — through a single `asyncio.Queue` with one worker task.

- **Singleton.** `commands.start()` in `_start()` after `broker.start()`. `commands.get()` returns the `CommandQueue`. `commands.stop()` on `app.on_shutdown` before `broker.stop()`.
- **`submit(fn, *args, coalesce_key=None, **kwargs)`.** Wraps the callable in a `_PendingCommand` with a `Future`, puts it on the queue, returns `await future`. The worker runs each callable via `asyncio.to_thread`.
- **Coalescing.** When the worker is busy and commands pile up, pending commands sharing a `coalesce_key` collapse to the latest; replaced futures resolve with `None`. No timers or artificial delays.
- **Volume coalescing.** The volume slider submits with `coalesce_key=('volume', client_id)`, so a fast drag produces one write per worker cycle.
- **Error propagation.** Exceptions from the callable are set on the future and re-raised in the caller. The worker continues to the next command.
- **What stays outside.** `_await_snapserver` (20 s poll), `adopt_running_sources` (startup reconciliation), broker reads, and the Plex claim flow.

## Client registry and fan-out

`pages/__init__.py._registry` maps NiceGUI client id → `Page`. Populated in the `_index()` and `_dsp()` route closures; cleaned on `client.on_disconnect`. `connected_pages()` returns `(Client, Page)` pairs, filtering disconnected entries.

All three fan-out callbacks — the broker's dirty callback (`_on_dirty`), `_on_sources_changed`, and `_on_settings_changed` — iterate `connected_pages()` and check `page._dialog_open`. If open, they add affected tab names to `page._deferred_tabs` instead of refreshing. Otherwise, `with client:` refreshes the relevant tabs.

## Defer and replay

A rebuild destroys open menus and dialogs. Every path that clears `_dialog_open` calls `_close_dialog(page)`, which replays deferred tab refreshes: if `page._deferred_tabs` is non-empty, it replaces the set with a fresh empty one and refreshes each tab that was deferred — sources, then settings, then players.

## Volume binding

The volume slider persists via `.on('update:model-value')` — a Quasar event that fires only on user interaction, not on programmatic `set_value()`. The slider value is bound from `broker.get().cache.volumes[client_id]` via NiceGUI's binding system. Every pushed value is step-aligned via `int(round(…))` to prevent phantom `update:model-value` emissions.

## Running a local dev server

When a change needs the **full app** against real players — e.g. the DSP editor, which only renders for a live Snapcast client — run the streamer itself pointed at a streamer on the network. Override the deployment settings (`audera/settings.py`) with `AUDERA_`-prefixed env vars and call `streamer.run()` directly: that's exactly what `audera streamer start` runs, minus the Raspberry-Pi network-setup gate that's inappropriate on a dev box.

```bash
AUDERA_SNAPSERVER_HOST=<streamer-ip> AUDERA_PLEXAMP_HOST=<streamer-ip> AUDERA_SERVER_HOST=127.0.0.1 AUDERA_SERVER_PORT=8080 uv run python -c "from audera.ui import streamer; streamer.run()"
```

- **Bind loopback only** (`AUDERA_SERVER_HOST=127.0.0.1`). The app defaults to `0.0.0.0`, which exposes the UI to the whole network — never bind non-loopback for a local review.
- **Port 8080**, not the default `80` (needs admin on Windows and tends to conflict); reuse it every run, same as the screenshot loop.
- Run it as a **background task** so it can be stopped cleanly with the task tooling, not `kill` (see the port-conflict note above).
- The DSP editor lives at `/player/<client-id>/dsp`; enumerate client ids with `SnapserverClient(host=..., port=...).get_clients()` when you need to deep-link a screenshot.
- `reload=False`, so **restart the server** to pick up code changes — stop the background task, then relaunch.