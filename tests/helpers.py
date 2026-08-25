"""Pure cross-lane test helpers.

Fixtures live in `conftest.py`; this module holds plain functions imported as
`from tests.helpers import …` (the repo root is on `sys.path` for both the in-process and
in-container lanes — the same form the systemd lane uses for `tests.systemd.inside.conftest`).
Nothing here touches the event loop, so the async settling helpers in `tests/ui/` keep their own
`await asyncio.sleep` bodies.
"""

import time
from typing import Callable, Optional, TypeVar

_T = TypeVar('_T')

# Distinct sentinel so a real `None`/`{}`/`[]` read never counts as a prior agreement.
_UNSET = object()


def poll_until(
    fn: Callable[[], _T],
    predicate: Callable[[_T], bool],
    timeout: float,
    interval: float,
    *,
    stable: int = 1,
    on_timeout: Optional[Callable[[_T], _T]] = None,
) -> _T:
    """Polls `fn()` until `predicate` holds, returning the last value at the deadline.

    Synchronous by design: every caller is a probe that blocks its own thread, not the event loop.
    Returns rather than raises at the deadline, so a caller's own assertion reports the value it read;
    pass `on_timeout` to raise (or otherwise transform the final value) instead.

    Parameters
    ----------
    fn: `Callable[[], _T]`
        The reading to poll. Called on the calling thread, so it must not block indefinitely.
    predicate: `Callable[[_T], bool]`
        Holds when the reading is the one the caller is waiting for.
    timeout: `float`
        How long to poll before giving up.
    interval: `float`
        The gap between readings.
    stable: `int`
        How many consecutive *equal* readings must satisfy `predicate` before returning. `1` returns
        on the first satisfying read; `2` expresses "settled" — two agreeing reads in a row, so a value
        still changing between polls is not mistaken for a settled one.
    on_timeout: `Optional[Callable[[_T], _T]]`
        Invoked with the last reading at the deadline; its return value is returned. `None` returns the
        last reading as-is. Raise from here to fail on timeout rather than return.
    """
    deadline = time.monotonic() + timeout
    agreed: object = _UNSET
    streak = 0
    while True:
        value = fn()
        if predicate(value):
            if streak and value == agreed:
                streak += 1
            else:
                agreed = value
                streak = 1
            if streak >= stable:
                return value
        else:
            agreed = _UNSET
            streak = 0
        if time.monotonic() >= deadline:
            return on_timeout(value) if on_timeout is not None else value
        time.sleep(interval)


def raise_with_logs(container, message: str, timeout: float) -> None:
    """Raises `TimeoutError(message)` with the container's tail-2000 logs appended.

    The log fetch is guarded: a container that died mid-boot may refuse `get_logs()`, and the timeout
    the caller is reporting must survive that.

    Parameters
    ----------
    container:
        A testcontainers container handle exposing `get_logs() -> (bytes, bytes)`.
    message: `str`
        The full failure message; the caller bakes in whatever `timeout`/state context it needs.
    timeout: `float`
        The elapsed budget, accepted so the signature reads at the call site even though `message`
        already carries it.
    """
    try:
        stdout, stderr = container.get_logs()
        log_text = f'\nstdout: {stdout.decode(errors="replace")[-2000:]}\nstderr: {stderr.decode(errors="replace")[-2000:]}'
    except Exception:
        log_text = ' (container logs unavailable)'
    raise TimeoutError(f'{message}{log_text}')
