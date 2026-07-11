"""Provider-neutral background-work contracts and test adapters."""

from app.platform.workers.contracts import JobOrigin, JobQueue, JobSpec, QueuedJob

__all__ = ["JobOrigin", "JobQueue", "JobSpec", "QueuedJob"]
