# ADR 006: Command Queue and Error Hierarchy

**Date:** 2026-08-09
**Status:** Accepted

## Context

The streamer UI wrote to three kinds of targets (Snapserver via sync WebSocket, CamillaDSP via sync WebSocket, local JSON DALs) using three different serialization mechanisms (`asyncio.Lock`, `threading.Lock`, event-loop-implicit), inconsistent error handling (blanket `except Exception` or nothing), and no backpressure on the volume slider. A source toggle could race with a second toggle, and a fast volume drag queued dozens of identical round-trips.

## Decisions

### Exception hierarchy

1. **Three typed exceptions.** `CommandError` (base), with `Unreachable`, `ServiceError`, and `StorageError` subclasses in `audera/errors.py`. Every UI write handler catches `CommandError` (plus `RuntimeError` for `@platform.requires` on a dev box) instead of `Exception`.

2. **Translation boundaries.** Each client and service boundary catches raw exceptions and re-raises the typed equivalent:

   | Boundary | Raw | Typed |
   |----------|-----|-------|
   | `SnapserverClient._call` | network errors | `Unreachable` |
   | `SnapserverClient._call` | `'error'` in response | `ServiceError` |
   | `CamillaDSPClient._call` | network errors | `Unreachable` |
   | `CamillaDSPClient._call` | `'Error'`/`'Invalid'` in response | `ServiceError` |
   | `CamillaDSPClient.validate_config` | non-`'Ok'` result | `ServiceError` |
   | `io.write_text` | `OSError` | `StorageError` |
   | `system.systemctl` | `CalledProcessError` | `ServiceError` (preserving stderr) |
   | `system.systemctl` | `TimeoutExpired`, `FileNotFoundError` | `Unreachable` |

3. **`platform.requires` stays `RuntimeError`.** It is a programming-environment guard, not a command failure.

### Command queue

4. **One queue, one worker.** `audera/ui/streamer/commands.py` holds a `CommandQueue` with an `asyncio.Queue` and a single worker task. Every UI write path submits through it, so one command at a time reaches the target. `_CHOREOGRAPHY_LOCK` is removed.

5. **Coalescing, not debouncing.** When the worker is busy, pending commands with the same `coalesce_key` collapse to the latest. Replaced commands resolve with `None`. No timers or artificial delays; the volume slider stays real-time.

6. **Volume coalescing key.** The volume slider submits with `coalesce_key=('volume', client_id)`. A fast drag produces one write per worker cycle, not one per event.

7. **Readiness waits stay outside.** `_await_snapserver` polls for up to 20 s after a source toggle. It runs outside the queue so it does not block other commands.

8. **DAL threading locks stay.** `volume_dal._WRITE_LOCK` and `sources_dal._WRITE_LOCK` are retained as defense-in-depth; the CLI also writes to these DALs.

9. **Singleton lifecycle.** `commands.start()` in `_start()` after `broker.start()`. `commands.stop()` on `app.on_shutdown` before `broker.stop()`.

## Consequences

- Every write handler narrows from `except Exception` to `except CommandError`, surfacing the right message instead of a stack trace or a silent swallow.
- A source toggle that fails at `systemctl restart` reports "is enabled, but applying it failed" and rolls forward, identical to the prior behavior but via the queue.
- The volume slider on a slow CamillaDSP cannot queue unbounded writes; at most one pending write per player survives.
- The `_CHOREOGRAPHY_LOCK` is gone. The queue serializes all writes inherently.
- Client tests now assert `ServiceError` and `Unreachable` instead of `RuntimeError`.
