"""Command queue for serialized, coalesced writes.

Every UI write path — Snapserver RPCs, CamillaDSP pushes, DAL saves, systemd toggles — goes
through the queue so that one command at a time reaches the target and fast-moving controls
(the volume slider) coalesce rather than pile up.

Singleton, following ``broker.py``'s pattern: ``start()`` creates the module-level instance,
``get()`` returns it, ``stop()`` tears it down.
"""

import asyncio
from typing import Any, Callable


class _PendingCommand:
    __slots__ = ('fn', 'args', 'kwargs', 'coalesce_key', 'future')

    def __init__(self, fn: Callable, args: tuple, kwargs: dict, coalesce_key: Any, future: asyncio.Future):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.coalesce_key = coalesce_key
        self.future = future


class CommandQueue:
    """An async queue that executes blocking callables one at a time on a worker thread."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[_PendingCommand] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    async def submit(self, fn: Callable, *args: Any, coalesce_key: Any = None, **kwargs: Any) -> Any:
        """Enqueues a callable and returns when it completes (or is coalesced away).

        Parameters
        ----------
        fn: `Callable`
            A blocking callable to run via ``asyncio.to_thread``.
        *args
            Positional arguments forwarded to ``fn``.
        coalesce_key
            When not ``None``, a pending command with the same key is replaced by this one.
            The replaced command's future resolves to ``None``.
        **kwargs
            Keyword arguments forwarded to ``fn``.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        cmd = _PendingCommand(fn, args, kwargs, coalesce_key, future)
        await self._queue.put(cmd)
        return await future

    @staticmethod
    def _coalesce(batch: list[_PendingCommand]) -> list[_PendingCommand]:
        """Coalesces commands sharing a key (keeps the latest), resolves replaced futures with ``None``."""
        if not batch:
            return []

        seen: dict[Any, int] = {}
        removed: set[int] = set()
        survivors: list[_PendingCommand] = []
        for cmd in batch:
            if cmd.coalesce_key is not None:
                prev_idx = seen.pop(cmd.coalesce_key, None)
                if prev_idx is not None:
                    replaced = survivors[prev_idx]
                    removed.add(prev_idx)
                    if not replaced.future.done():
                        replaced.future.set_result(None)
                seen[cmd.coalesce_key] = len(survivors)
            survivors.append(cmd)
        return [s for i, s in enumerate(survivors) if i not in removed]

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            pending: list[_PendingCommand] = []
            while not self._queue.empty():
                try:
                    pending.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            batch = self._coalesce([first] + pending)
            for cmd in batch:
                if cmd.future.cancelled():
                    continue
                try:
                    result = await asyncio.to_thread(cmd.fn, *cmd.args, **cmd.kwargs)
                    if not cmd.future.done():
                        cmd.future.set_result(result)
                except Exception as exc:
                    if not cmd.future.done():
                        cmd.future.set_exception(exc)

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        self._worker = loop.create_task(self._run())

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass


_queue: CommandQueue | None = None


def get() -> CommandQueue:
    assert _queue is not None, 'command queue not started'
    return _queue


def start() -> None:
    global _queue
    _queue = CommandQueue()
    _queue.start()


async def stop() -> None:
    global _queue
    if _queue is not None:
        await _queue.stop()
        _queue = None
