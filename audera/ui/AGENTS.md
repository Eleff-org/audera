# AGENTS.md

UI conventions for the `audera` NiceGUI apps. List @audera/ui for the package layout.

## App structure

One `Page` per connected client: `@ui.refreshable` keys its targets on the bound instance, so a shared `Page` turns every `refresh()` into a broadcast (see the `Page` class docstring). `load()` registers route closures that each build their own `Page`; `run()`'s instance only calls `load()`. Process-scoped work goes in `load()` or at module level, not on the instance.

When `pages.py` outgrows a few hundred lines, split it into a `pages/` package: a thin `Page` class in `__init__.py`, one `render(page, …)` module per route, and `_`-prefixed helper modules. Route modules take `page` as an argument and import `Page` only under `TYPE_CHECKING`. `__init__.py` is a thin `run()` entry point only, with no implementation logic.

`ui/setup` is the exception: it shares one instance and stores live `ui.element` handles on `self`, since it serves a single onboarding browser over its own access point.

## NiceGUI conventions

- Register pages with `ui.page(route)(self.method)` inside `load()`.
- `@ui.refreshable` on tab-builder methods; re-render via `self._build_<name>_tab.refresh()`.
- Bind with `bind_visibility_from` / `bind_enabled_from`.
- Page and callback methods are `async`; wrap blocking I/O in `asyncio.to_thread`.
- Poll with `ui.timer(interval, callback)`.
- Notify with `ui.notify(msg, position='top-right', type='positive'|'negative'|'warning')`.

## Brand

Consume the brand tokens per `brand/AGENTS.md`; UI adds three rules:

- Never hard-code hex. Use `var(--token)` in CSS/Tailwind or the `theme.*` constants in Python.
- `components/theme.py` is the sole adapter: the only file that calls `app.add_static_files()` for brand assets and the only one that sets Quasar's `--q-*` color slots (in `_PAGE_CSS`, from the tokens).
- Light palette only; no dark mode.

## Style

- Private tab builders `_build_<name>_tab()`; user-event callbacks `_on_<action>()`; timer callbacks `_poll_<thing>()`.
- No `ui.run()` outside `__init__.py`.
- Module-level helpers with no instance state stay module-level functions, not `@staticmethod`.

## UX optionality

A UI feature with more than one defensible UX is registered in `audera/ui/features.py`'s `FEATURES` catalog, not hard-coded as one path. Resolve a selection with `features.selected(settings, key)` or `flag_enabled(...)`, never by reading `settings.features[...]` directly. A new entry names every option with an `FF_*` constant (ADR 004 §2). Skip the catalog only when a feature has one correct UX; propose an entry (or ask which options to offer) otherwise.

## Host mutations

UI code never calls `subprocess`; every systemd interaction goes through `audera.services.system`, and the Sources tab goes through `domains.sources.toggle.apply` (which holds the conf write, units, and restart). Reference `/etc/` targets by module attribute (`conf.SNAPSERVER_CONF`), read at call time, so a test can redirect the write into `tmp_path`. Notifications read `getattr(exc, 'stderr', '') or str(exc)` because `@platform.requires` raises `RuntimeError`, which has no `stderr`.

## Event broker and command queue

`streamer/broker.py` brokers Snapserver and volume-DAL events into a cache the UI reads synchronously; `streamer/commands.py` serializes every write path through one `asyncio.Queue`. Both are module-level singletons started on app startup and torn down on shutdown; their module docstrings own the details (seed-then-delta, debounce, reconnect, coalescing).

## Previewing and running locally

The user iterates on UI from screenshots. Most player UI needs live Snapcast clients, so:

- Preview a component in isolation with a throwaway `_preview.py` at the repo root against `theme.apply_defaults()`, or run the full app with `audera streamer start --mock` (binds loopback:8080, skips the Pi network-setup gate; override backends with `AUDERA_*` env vars).
- Run the setup wizard off-device with `audera streamer setup --mock` / `audera player setup --mock`; `ui/setup/_mock.py` stands in for the device seams under the flag.
- Reuse **port 8080** every run, launch as a **background task** (a stray process holds the socket → WinError 10048), and screenshot headless:
  ```bash
  "/c/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu --screenshot=/tmp/preview.png --force-device-scale-factor=4 --virtual-time-budget=4000 http://127.0.0.1:8080
  ```
- The app runs with `reload=False`, so restart it to pick up changes. Clean up `_preview.py` and free the port before committing.
