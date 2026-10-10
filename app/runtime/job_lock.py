"""Per-job locks for planning-stage execution.

Process-local only. Serializes skip-check plus stage execution for one job_id
so the orchestrator and HTTP Eye/Brain/Stylist/Compile handlers cannot
double-dispatch. RLock allows advance_planning to hold the lock while
calling execute_job_* which acquire the same lock.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_registry_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}


def job_lock(job_id: str) -> threading.RLock:
    """Return the re-entrant lock for this job_id, creating it if needed."""

    with _registry_guard:
        lock = _locks.get(job_id)
        if lock is None:
            lock = threading.RLock()
            _locks[job_id] = lock
        return lock


@contextmanager
def locked_job(job_id: str) -> Iterator[None]:
    """Hold the per-job lock for the duration of the with-block."""

    with job_lock(job_id):
        yield
