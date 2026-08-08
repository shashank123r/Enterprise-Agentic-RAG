"""Thread pool executor for offloading blocking I/O operations.

All synchronous document processing (PDF parsing, OCR, file I/O) is
offloaded to a dedicated thread pool so the FastAPI event loop is
never blocked during ingestion.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, TypeVar

T = TypeVar("T")

# Dedicated thread pool for CPU/IO-bound extraction work
_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="ingestion",
)


async def run_in_executor(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a synchronous function in the ingestion thread pool.

    Use this for all blocking I/O operations during document extraction
    to keep the asyncio event loop responsive.

    Args:
        func: Synchronous function to execute.
        *args: Positional arguments.
        **kwargs: Keyword arguments.

    Returns:
        The return value of ``func``.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EXECUTOR, partial(func, *args, **kwargs))
