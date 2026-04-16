"""Tests for the orchestrator module."""

import asyncio
import time
import threading
import pytest

import audera


def blocking_task(duration: float = 2.0) -> str:
    """A blocking task that simulates I/O or computation."""
    print(f"Starting blocking task for {duration}s in thread {threading.current_thread().name}")
    time.sleep(duration)
    print(f"Completed blocking task in thread {threading.current_thread().name}")
    return f"Task completed after {duration}s"


@pytest.fixture
def orchestrator():
    """Fixture to provide a fresh orchestrator instance."""
    orch = audera.orchestrator.Orchestrator()
    yield orch
    orch.shutdown()


def test_orchestrator_basic(orchestrator: audera.orchestrator.Orchestrator):
    """Test basic orchestrator functionality."""
    # Test synchronous task execution
    result = orchestrator.run(
        task_id="test_sync",
        func=blocking_task,
        duration=1.0,
        pool_type="thread"
    )
    assert "1.0s" in result

    # Test task status
    status = orchestrator.get_task_status("test_sync")
    assert status == audera.orchestrator.TaskStatus.COMPLETED


def test_orchestrator_timeout(orchestrator: audera.orchestrator.Orchestrator):
    """Test timeout functionality."""
    with pytest.raises(asyncio.TimeoutError):
        orchestrator.run(
            task_id="test_timeout",
            func=blocking_task,
            duration=5.0,  # Long task
            timeout=1.0,   # Short timeout
            pool_type="thread"
        )

    # Check task status
    status = orchestrator.get_task_status("test_timeout")
    assert status == audera.orchestrator.TaskStatus.TIMEOUT


def test_orchestrator_restart(orchestrator: audera.orchestrator.Orchestrator):
    """Test restart on failure functionality."""
    def failing_task():
        raise ValueError("Simulated failure")

    with pytest.raises(ValueError, match="Simulated failure"):
        orchestrator.run(
            task_id="test_restart",
            func=failing_task,
            restart_on_failure=True,
            pool_type="thread"
        )

    # Check retry count
    task = orchestrator.tasks.get("test_restart")
    assert task is not None
    assert task.retry_count > 0


def test_orchestrator_concurrent(orchestrator: audera.orchestrator.Orchestrator):
    """Test concurrent task execution."""
    start_time = time.time()

    # Run multiple tasks concurrently
    results = []
    for i in range(3):
        result = orchestrator.run(
            task_id=f"concurrent_{i}",
            func=blocking_task,
            duration=1.0,
            pool_type="thread"
        )
        results.append(result)

    end_time = time.time()
    total_time = end_time - start_time

    # Should complete faster than sequential execution
    assert total_time < 2.5  # Less than 3x sequential time
    assert len(results) == 3


def test_orchestrator_cleanup(orchestrator: audera.orchestrator.Orchestrator):
    """Test orchestrator cleanup."""
    # Run a task
    _ = orchestrator.run(
        task_id="cleanup_test",
        func=blocking_task,
        duration=0.5,
        pool_type="thread"
    )

    # Shutdown is handled by fixture

    # Check cleanup
    assert len(orchestrator.tasks) == 0
    assert len(orchestrator.futures) == 0
    assert len(orchestrator.executors) == 0
