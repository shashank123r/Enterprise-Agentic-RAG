"""Structured task lifecycle manager for background indexing jobs.

Replaces fire-and-forget asyncio.create_task() with tracked, cancellable,
and manageable task references. Tasks survive request boundaries and can
be cancelled, monitored, and cleaned up.

Usage:
    manager = TaskManager()
    task = await manager.create_task("job-123", some_coro())
    await manager.cancel_task("job-123")
    await manager.shutdown()  # Cancels all active tasks
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)


class TaskManager:
    """Manages background asyncio tasks with lifecycle tracking.

    Each task is identified by a job_id and can be individually
    cancelled, monitored, or awaited. On shutdown, all active
    tasks are cancelled gracefully.

    Thread-safe for concurrent access via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    async def create_task(
        self,
        job_id: str,
        coro: asyncio.Future[Any] | Any,
        name: str | None = None,
    ) -> asyncio.Task[Any]:
        """Create and register a tracked background task.

        Args:
            job_id: Unique job identifier for the task.
            coro: Coroutine to run in the background.
            name: Optional human-readable task name.

        Returns:
            The created asyncio.Task.

        Raises:
            ValueError: If a task with this job_id already exists.
        """
        async with self._lock:
            if job_id in self._tasks:
                raise ValueError(f"Task already exists for job: {job_id}")

            cancel_event = asyncio.Event()
            self._cancel_events[job_id] = cancel_event

            task = asyncio.create_task(
                self._run_with_cleanup(job_id, coro, cancel_event),
                name=name or f"indexing:{job_id}",
            )
            self._tasks[job_id] = task

            logger.debug("Created background task", job_id=job_id, task_name=name)
            return task

    async def cancel_task(self, job_id: str) -> bool:
        """Cancel a specific task by job_id.

        Sets the cancel event (so the task can check it) and
        also cancels the asyncio.Task itself.

        Args:
            job_id: Job ID to cancel.

        Returns:
            True if the task was found and cancelled, False otherwise.
        """
        async with self._lock:
            # Set the cancel event for cooperative cancellation
            cancel_event = self._cancel_events.get(job_id)
            if cancel_event is not None:
                cancel_event.set()

            task = self._tasks.get(job_id)
            if task is None:
                return False

            task.cancel()
            logger.info("Cancelled background task", job_id=job_id)
            return True

    async def get_task(self, job_id: str) -> asyncio.Task[Any] | None:
        """Get a tracked task by job_id."""
        async with self._lock:
            return self._tasks.get(job_id)

    async def task_done(self, job_id: str) -> bool:
        """Check if a task has completed.

        Returns:
            True if the task is done or doesn't exist, False if still running.
        """
        async with self._lock:
            task = self._tasks.get(job_id)
            if task is None:
                return True
            return task.done()

    async def get_cancel_event(self, job_id: str) -> asyncio.Event | None:
        """Get the cancel event for a job.

        Used by background tasks to check if they should stop.
        """
        async with self._lock:
            return self._cancel_events.get(job_id)

    async def active_count(self) -> int:
        """Get the number of currently tracked active tasks."""
        async with self._lock:
            return len(self._tasks)

    async def active_job_ids(self) -> list[str]:
        """Get list of all currently active job IDs."""
        async with self._lock:
            return list(self._tasks.keys())

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Cancel all active tasks and wait for them to finish.

        Args:
            timeout: Maximum seconds to wait for tasks to finish.
        """
        self._shutdown_event.set()

        async with self._lock:
            # Set all cancel events
            for event in self._cancel_events.values():
                event.set()

            # Cancel all tasks
            for job_id, task in self._tasks.items():
                task.cancel()
                logger.debug("Shutdown cancelling task", job_id=job_id)

            tasks = list(self._tasks.values())

        if tasks:
            _done, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                for t in pending:
                    logger.warning("Task did not finish during shutdown", task_name=t.get_name())

        async with self._lock:
            self._tasks.clear()
            self._cancel_events.clear()

        logger.info("Task manager shutdown complete", cancelled=len(tasks))

    async def _run_with_cleanup(
        self,
        job_id: str,
        coro: asyncio.Future[Any] | Any,
        cancel_event: asyncio.Event,
    ) -> Any:
        """Run a coroutine and clean up the task registry on completion.

        Args:
            job_id: Job identifier for cleanup.
            coro: Coroutine to execute.
            cancel_event: Event that's set when cancellation is requested.

        Returns:
            The result of the coroutine, or None if cancelled.
        """
        try:
            return await coro
        except asyncio.CancelledError:
            logger.info("Background task cancelled", job_id=job_id)
            raise
        except Exception as e:
            logger.exception("Background task failed", job_id=job_id, error=str(e))
            raise
        finally:
            async with self._lock:
                self._tasks.pop(job_id, None)
                self._cancel_events.pop(job_id, None)
                logger.debug("Cleaned up task registry", job_id=job_id)
