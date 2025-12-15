"""Task pool orchestrator"""

from typing import Literal, Any, Callable, Optional
import asyncio
import concurrent.futures
import threading
import time
import logging
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    """Enumeration of possible task states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A `class` that represents an orchestrated task."""
    id: str
    func: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    retry_count: int = 0


class Orchestrator:
    """A `class` that represents an event loop orchestrator that runs critical tasks in
    isolated thread/process pools.

    This orchestrator prevents blocking of the main asyncio event loop by executing
    critical tasks in separate execution contexts (threads or processes).
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize the orchestrator.

        Parameters
        ----------
        logger : Optional[logging.Logger]
            Logger instance for task event logging. If None, uses default logger.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.tasks: dict[str, Task] = {}
        self.executors: dict[str, concurrent.futures.Executor] = {}
        self.futures: dict[str, concurrent.futures.Future] = {}
        self._shutdown_event = threading.Event()

    def run(
        self,
        task_id: str,
        func: Callable,
        *args,
        restart_on_failure: bool = False,
        timeout: Optional[float] = None,
        pool_type: Literal["thread", "process"] = "thread",
        **kwargs
    ) -> Any:
        """Execute a task in an isolated execution context.

        Parameters
        ----------
        task_id : str
            Unique identifier for the task
        func : Callable
            The function to execute
        *args
            Positional arguments for the function
        restart_on_failure : bool, default False
            Whether to restart the task if it fails
        timeout : Optional[float], default None
            Maximum execution time in seconds
        pool_type : Literal["thread", "process"], default "thread"
            Type of execution pool to use
        **kwargs
            Keyword arguments for the function

        Returns
        -------
        Any
            The result of the function execution

        Raises
        ------
        Exception
            If the task fails and restart_on_failure is False
        asyncio.TimeoutError
            If the task exceeds the timeout
        """
        # Create task object
        task = Task(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs
        )
        self.tasks[task_id] = task

        # Get or create executor
        executor_key = f"{pool_type}_pool"
        if executor_key not in self.executors:
            if pool_type == "thread":
                self.executors[executor_key] = concurrent.futures.ThreadPoolExecutor(
                    max_workers=4,
                    thread_name_prefix=f"audera-{pool_type}"
                )
            elif pool_type == "process":
                self.executors[executor_key] = concurrent.futures.ProcessPoolExecutor(
                    max_workers=2
                )
            else:
                raise NotImplementedError(f"Pool-type ['{pool_type}'] is not supported.")

        executor = self.executors[executor_key]

        # Log task start
        self.logger.info(f"Starting task {{{task_id}}} in the {pool_type} pool...")

        # Submit task to executor
        future = executor.submit(func, *args, **kwargs)
        self.futures[task_id] = future

        task.status = TaskStatus.RUNNING
        task.start_time = time.monotonic()

        try:
            # Wait for completion with timeout
            result = future.result(timeout=timeout)

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.end_time = time.monotonic()

            self.logger.info(
                f"Task {{{task_id}}} completed successfully in "
                f"{task.end_time - task.start_time:.2f} [sec.]."
            )

            return result

        except concurrent.futures.TimeoutError:
            task.status = TaskStatus.TIMEOUT
            task.end_time = time.monotonic()
            self.logger.error(f"Task {{{task_id}}} timed out after {timeout} [sec.].")

            if restart_on_failure:
                self.logger.info(f"Restarting task {{{task_id}}}...")
                return self.run(
                    task_id,
                    func,
                    *args,
                    restart_on_failure=True,
                    timeout=timeout,
                    pool_type=pool_type,
                    **kwargs
                )
            else:
                raise asyncio.TimeoutError(f"Task {{{task_id}}} timed out after {timeout} [sec.].")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = e
            task.end_time = time.monotonic()

            self.logger.error(
                f"Task {{{task_id}}} failed after {task.end_time - task.start_time:.2f} [sec.]. {e}"
            )

            if restart_on_failure:
                task.retry_count += 1
                self.logger.info(f"Retrying task {{{task_id}}}... (attempt {task.retry_count})")
                return self.run(
                    task_id,
                    func,
                    *args,
                    restart_on_failure=True,
                    timeout=timeout,
                    pool_type=pool_type,
                    **kwargs
                )
            else:
                raise e

        finally:
            # Clean up future reference
            if task_id in self.futures:
                del self.futures[task_id]

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get the status of a task.

        Parameters
        ----------
        task_id : str
            The task identifier

        Returns
        -------
        Optional[TaskStatus]
            The current task status, or None if task doesn't exist
        """
        task = self.tasks.get(task_id)
        return task.status if task else None

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task.

        Parameters
        ----------
        task_id : str
            The task identifier

        Returns
        -------
        bool
            True if task was cancelled, False otherwise
        """
        future = self.futures.get(task_id)
        if future and not future.done():
            cancelled = future.cancel()
            if cancelled:
                task = self.tasks.get(task_id)
                if task:
                    task.status = TaskStatus.CANCELLED
                    task.end_time = time.monotonic()
                self.logger.info(f"Task {{{task_id}}} cancelled successfully.")
            return cancelled
        return False

    async def arun(
        self,
        task_id: str,
        coro_func,
        restart_on_failure: bool = False,
        timeout: Optional[float] = None,
        pool_type: Literal["thread", "process"] = "thread"
    ):
        """Run a coroutine function asynchronously using the orchestrator for isolation.

        This method wraps the synchronous `run` method to avoid blocking the asyncio event loop.

        Parameters
        ----------
        task_id : str
            Unique identifier for the task
        coro_func
            The coroutine function to execute
        restart_on_failure : bool, default False
            Whether to restart the task if it fails
        timeout : Optional[float], default None
            Maximum execution time in seconds
        pool_type : Literal["thread", "process"], default "thread"
            Type of execution pool to use

        Returns
        -------
        Any
            The result of the coroutine execution

        Raises
        ------
        Exception
            If the task fails and restart_on_failure is False
        asyncio.TimeoutError
            If the task exceeds the timeout
        """
        try:

            # Since orchestrator.run() is synchronous, we need to run it in a thread
            #   to avoid blocking the event loop

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.run(
                    task_id=task_id,
                    func=lambda: asyncio.run(coro_func()),
                    restart_on_failure=restart_on_failure,
                    timeout=timeout,
                    pool_type=pool_type
                )
            )
            return result
        except Exception as e:
            self.logger.error(f"Orchestrated task {{{task_id}}} failed. {e}")
            raise

    def shutdown(self):
        """Shutdown the orchestrator and clean up resources."""
        self.logger.info("Shutting down the orchestrator...")

        # Cancel all pending tasks
        for task_id in list(self.futures.keys()):
            self.cancel_task(task_id)

        # Shutdown executors
        for executor in self.executors.values():
            executor.shutdown(wait=True)

        self.executors.clear()
        self.futures.clear()
        self.tasks.clear()
        self._shutdown_event.set()

        self.logger.info("Orchestrator shutdown successfully.")
