# AGENTS.md

## Package layout

List @audera/ui for the Python package layout.

## App pattern

Every UI app follows this two-file pattern:

**`pages.py`** — contains a `Page` class:
- `__init__`: loads state (settings, clients); no platform decorator unless dietpi-only
- `load()`: registers routes via `ui.page(route)(self.method)`
- Page methods: one per route (e.g. `index()`, `welcome()`, `connect()`)
- Tab builder methods: `_build_<name>_tab()` — private, called from a page method

**`pages/` sub-package** — when `pages.py` grows past a few hundred lines, split it into a
`pages/` package instead of one flat file:
- `pages/__init__.py`: the thin `Page` class (`__init__`, `load()`) re-exported so
  `from …pages import Page` is unchanged. Each route method delegates to a module-level
  `render(page, …)` — e.g. `def dsp(self, player_id): dsp.render(self, player_id)`.
- One module per route (`pages/index.py`, `pages/dsp.py`, …): a `render(page, …)` function
  plus that route's private `_build_<name>_tab(page)` / `_on_<action>(page, …)` helpers.
  `page` carries the shared state (`page.settings`, `page._dialog_open`); the `Page` class is
  **not** split across files. `@ui.refreshable` helpers stay module-level, keyed on the
  `page` argument, and are refreshed via `_build_<name>_tab.refresh()`.
- Private helper modules (`pages/_clients.py`, `pages/_plex.py`, …): shared client factories
  and self-contained flows, imported by the route modules. To avoid an import cycle, route
  modules never import names from `pages/__init__.py` at runtime — they take `page` as an
  argument and import `Page` only under `TYPE_CHECKING`.

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

## Previewing UI changes (screenshot loop)

The user iterates on UI from screenshots. Most player UI only renders with live Snapcast clients, so preview a component in isolation rather than the full app:

1. Write a throwaway `_btn_preview.py` at the repo root that reproduces the exact widget/props against `components.theme.apply_defaults()`. Reuse **port 8080** every run so the user doesn't open new browser tabs.
2. Run it as a **background task** (not `foo &`) so it can be killed cleanly. `uv run python`'s child process holds the socket, and a stray one causes a port conflict (WinError 10048) on the next run — stop it with the task tooling, not `kill`.
3. Screenshot headless and review, then iterate:
   ```bash
   "/c/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu --screenshot=/tmp/preview.png --force-device-scale-factor=4 --virtual-time-budget=4000 http://127.0.0.1:8080
   ```
   `--force-device-scale-factor` zooms for pixel inspection; `--virtual-time-budget` gives Material Symbols web-fonts time to load.
4. **Clean up before committing**: stop the background server, delete `_btn_preview.py`, and free port 8080. The harness is never committed.

The real app runs with `reload=False`, so the user restarts it to see applied changes.
