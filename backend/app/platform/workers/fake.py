from __future__ import annotations

from collections.abc import Callable

from app.platform.workers.contracts import JobSpec, QueuedJob


class RecordingJobQueue:
    """Deterministic in-memory adapter for application and contract tests."""

    def __init__(self, *, id_factory: Callable[[], str] | None = None) -> None:
        self._id_factory = id_factory
        self._jobs: list[JobSpec] = []

    @property
    def jobs(self) -> tuple[JobSpec, ...]:
        return tuple(self._jobs)

    async def enqueue(self, job: JobSpec, /) -> QueuedJob:
        self._jobs.append(job)
        job_id = (
            self._id_factory()
            if self._id_factory is not None
            else f"fake-job-{len(self._jobs)}"
        )
        return QueuedJob(id=job_id, queue=job.queue)
