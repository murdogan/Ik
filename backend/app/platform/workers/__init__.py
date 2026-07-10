"""Provider-neutral background-work contracts and test adapters."""

from app.platform.workers.contracts import JobQueue, JobSpec, QueuedJob

__all__ = ["JobQueue", "JobSpec", "QueuedJob"]
