# ADR 005: Streamer Freshness Across Connected Clients

**Date:** 2026-08-08
**Status:** Accepted

## Context

The streamer UI polled Snapserver every 10 seconds per browser, rebuilding the entire Players tab whether or not anything changed. Sources and Settings tabs did not propagate across clients at all. `SnapserverClient._call` had a race where Snapserver notifications could land as the response, returning `{}` and blanking the Players tab.

## Decisions

1. **Read path.** The event broker receives events from Snapserver (persistent WebSocket) and local metadata (volume DAL), caches the combined state, and signals callbacks when it changes. The UI reads from the cache.

2. **Diff before rebuild.** `broker.Cache.snapshot()` returns an immutable tuple of all cached state. After every notification, compare against the prior snapshot; signal dirty only on change.

3. **Bound volume exception.** The volume slider is bound from `broker.get().cache.volumes[client_id]` via NiceGUI's binding system (100 ms propagation). Persistence uses `update:model-value` (a Quasar event that fires only on user interaction, not on programmatic `set_value()`), so a broker push cannot echo back to the device.

4. **Short-lived writes.** Writes use short-lived connections via `_call` because Snapserver's `excludeSession` excludes the writing socket from notifications.

5. **Seed then delta.** `Server.GetStatus` on connect populates the cache. Notifications update it in place. `Client.OnConnect` triggers a full reseed via a short-lived connection, since the new client's state is not in the notification payload.

6. **Step-aligned pushes.** Every value pushed to the volume slider is `int(round(…))`. An unaligned value makes Quasar snap the slider and emit a phantom `update:model-value`, echoing back to the device.

7. **Defer and replay.** Every fan-out callback (broker dirty, plus the sources, settings, volume, and balance observers) checks `page._dialog_open`; if true, it adds the affected tab names to `page._deferred_tabs: set[str]` instead of refreshing. Every path that clears `_dialog_open` replays the deferred set — sources, settings, then players — and replaces it with a fresh empty set.

8. **Debounce.** A burst of Snapserver notifications (e.g. a server restart) produces one callback invocation after a 250 ms quiet period, not one per notification.

9. **Startup/shutdown lifecycle.** `broker.start` on `app.on_startup`, `broker.stop` on `app.on_shutdown`, both wired in `audera/ui/streamer/__init__.py`. DAL observers are registered alongside the broker.

10. **Fan out every UI-visible write.** Any DAL write whose result is reflected in a tab must expose the observer pattern (`on_change` / `_notify_observers`, notified at the end of `save`/`set`) and fan out through a handler in `ui/streamer/__init__.py` that marshals onto the UI loop and refreshes the affected tabs on every connected page. A local `refresh()` on the acting page is not sufficient — it leaves other browsers, and often the acting one, stale. This is an invariant, not a fixed list: a new write path adds an observer. Every observer respects `page._dialog_open`, deferring into `_deferred_tabs` the same way the broker's dirty callback does. Current observers: sources, settings, volume, balance. A settings change additionally reloads every page's `settings` from disk (data, not UI). A volume change pushes the DAL volumes into the broker cache for the slider bindings and refreshes Settings so the "Listening at reference" indicator tracks loudness changes that cross no Snapcast mute boundary (and therefore produce no broker dirty).

## Consequences

- The 10 s polling timer and its per-browser reader plumbing are gone; `build_players_tab` is synchronous and reads the broker cache directly.
- A new player connecting or disconnecting is reflected in every open browser within 250 ms of Snapserver's notification, without any browser refreshing.
- Volume changes from any source (the Snapcast Android app, another browser, CamillaDSP directly) propagate to every browser via the broker's volume binding.
- The `_call` id-matching fix eliminates the `{}` response race independently of the broker, so any code that still uses `SnapserverClient` directly benefits.
- The client registry (`pages/__init__.py._registry`) is the only new process-wide mutable state beyond the broker singleton.
