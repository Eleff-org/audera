"""Unit tests for the command queue: submit, coalesce, error propagation."""

import asyncio
import threading

import pytest

from audera.errors import ServiceError, StorageError
from audera.ui.streamer.commands import CommandQueue


@pytest.fixture
async def queue():
    q = CommandQueue()
    q.start()
    yield q
    await q.stop()


async def test_submit_returns_the_callable_result(queue):
    result = await queue.submit(lambda: 42)
    assert result == 42


async def test_submit_forwards_args_and_kwargs(queue):
    def add(a, b, offset=0):
        return a + b + offset

    assert await queue.submit(add, 3, 4, offset=10) == 17


async def test_submit_propagates_exceptions(queue):
    def boom():
        raise StorageError('disk full')

    with pytest.raises(StorageError, match='disk full'):
        await queue.submit(boom)


async def test_submit_propagates_service_error(queue):
    def boom():
        raise ServiceError('unit failed')

    with pytest.raises(ServiceError, match='unit failed'):
        await queue.submit(boom)


async def test_commands_execute_sequentially(queue):
    order = []

    def record(label):
        order.append(label)

    await queue.submit(record, 'a')
    await queue.submit(record, 'b')
    await queue.submit(record, 'c')
    assert order == ['a', 'b', 'c']


async def test_coalesce_keeps_latest(queue):
    entered = threading.Event()
    proceed = threading.Event()
    results = []

    def blocking():
        entered.set()
        proceed.wait(timeout=5)
        return 'blocker'

    def record(value):
        results.append(value)
        return value

    t0 = asyncio.create_task(queue.submit(blocking))
    await asyncio.to_thread(entered.wait, 5)
    t1 = asyncio.create_task(queue.submit(record, 'first', coalesce_key='k'))
    t2 = asyncio.create_task(queue.submit(record, 'second', coalesce_key='k'))
    t3 = asyncio.create_task(queue.submit(record, 'third', coalesce_key='k'))
    await asyncio.sleep(0.05)
    proceed.set()

    await asyncio.gather(t0, t1, t2, t3)
    assert t0.result() == 'blocker'
    assert t1.result() is None
    assert t2.result() is None
    assert t3.result() == 'third'
    assert results == ['third']


async def test_different_coalesce_keys_are_independent(queue):
    entered = threading.Event()
    proceed = threading.Event()
    results = []

    def blocking():
        entered.set()
        proceed.wait(timeout=5)
        return 'blocker'

    def record(value):
        results.append(value)
        return value

    t0 = asyncio.create_task(queue.submit(blocking))
    await asyncio.to_thread(entered.wait, 5)
    t1 = asyncio.create_task(queue.submit(record, 'a1', coalesce_key='a'))
    t2 = asyncio.create_task(queue.submit(record, 'a2', coalesce_key='a'))
    t3 = asyncio.create_task(queue.submit(record, 'b1', coalesce_key='b'))
    await asyncio.sleep(0.05)
    proceed.set()

    await asyncio.gather(t0, t1, t2, t3)
    assert t1.result() is None
    assert t2.result() == 'a2'
    assert t3.result() == 'b1'
    assert set(results) == {'a2', 'b1'}


async def test_no_coalesce_key_runs_all(queue):
    entered = threading.Event()
    proceed = threading.Event()
    results = []

    def blocking():
        entered.set()
        proceed.wait(timeout=5)

    def record(value):
        results.append(value)

    t0 = asyncio.create_task(queue.submit(blocking))
    await asyncio.to_thread(entered.wait, 5)
    t1 = asyncio.create_task(queue.submit(record, 'x'))
    t2 = asyncio.create_task(queue.submit(record, 'y'))
    await asyncio.sleep(0.05)
    proceed.set()

    await asyncio.gather(t0, t1, t2)
    assert results == ['x', 'y']


async def test_error_in_one_command_does_not_stop_the_worker(queue):
    def boom():
        raise ValueError('oops')

    with pytest.raises(ValueError):
        await queue.submit(boom)

    assert await queue.submit(lambda: 'ok') == 'ok'
