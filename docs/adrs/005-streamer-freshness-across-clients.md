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

7. **Defer and replay.** All three fan-out callbacks (broker dirty, sources observer, settings observer) check `page._dialog_open`; if true, they add the affected tab names to `page._deferred_tabs: set[str]` instead of refreshing. Every path that clears `_dialog_open` replays the deferred set — sources, settings, then players — and replaces it with a fresh empty set.

8. **Debounce.** A burst of Snapserver notifications (e.g. a server restart) produces one callback invocation after a 250 ms quiet period, not one per notification.

9. **Startup/shutdown lifecycle.** `broker.start` on `app.on_startup`, `broker.stop` on `app.on_shutdown`, both wired in `audera/ui/streamer/__init__.py`. DAL observers are registered alongside the broker.

10. **Device-wide settings.** Sources and Settings DAL writes notify all connected browsers via a simple observer pattern (`on_change` / `_notify_observers`). Both observers respect `page._dialog_open`, deferring into `_deferred_tabs` the same way the broker's dirty callback does. A settings change reloads every page's `settings` from disk unconditionally (data, not UI) and refreshes both the Players and Settings tabs.

## Consequences

- The 10 s polling timer and its per-browser reader plumbing are gone; `build_players_tab` is synchronous and reads the broker cache directly.
- A new player connecting or disconnecting is reflected in every open browser within 250 ms of Snapserver's notification, without any browser refreshing.
- Volume changes from any source (the Snapcast Android app, another browser, CamillaDSP directly) propagate to every browser via the broker's volume binding.
- The `_call` id-matching fix eliminates the `{}` response race independently of the broker, so any code that still uses `SnapserverClient` directly benefits.
- The client registry (`pages/__init__.py._registry`) is the only new process-wide mutable state beyond the broker singleton.
