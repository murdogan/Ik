from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import pytest
from app.platform.request_context import AuthenticationStrength, RequestContext
from app.platform.tenancy import TenantContext
from app.platform.workers import JobQueue, JobSpec
from app.platform.workers.fake import RecordingJobQueue

TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_TENANT_ID = UUID("10000000-0000-4000-8000-000000000002")
TRACE_ID = "0123456789abcdef0123456789abcdef"


async def test_recording_job_queue_preserves_tenant_and_operational_controls() -> None:
    payload = {
        "employee": {"id": "20000000-0000-4000-8000-000000000001"},
        "fields": ["id"],
    }
    job = JobSpec(
        task_name="employees.export",
        tenant_id=TENANT_ID,
        idempotency_key="export-request-001",
        payload=payload,
        timeout_seconds=120,
        max_attempts=3,
        queue="exports",
        correlation_id="request-001",
    )
    payload["employee"]["id"] = "changed-after-construction"
    payload["fields"].append("email")
    queue: JobQueue = RecordingJobQueue()

    queued = await queue.enqueue(job)

    assert queued.id == "fake-job-1"
    assert queued.queue == "exports"
    assert isinstance(queue, RecordingJobQueue)
    assert queue.jobs == (job,)
    assert queue.jobs[0].tenant_id == TENANT_ID
    assert queue.jobs[0].request_context_for_transport() is None
    assert queue.jobs[0].payload == {
        "employee": {"id": "20000000-0000-4000-8000-000000000001"},
        "fields": ("id",),
    }
    recorded_employee = queue.jobs[0].payload["employee"]
    assert isinstance(recorded_employee, Mapping)
    with pytest.raises(TypeError):
        recorded_employee["id"] = "changed-after-enqueue"  # type: ignore[index]

    transport_payload = queue.jobs[0].payload_for_transport()
    transport_payload["employee"]["id"] = "changed-transport-copy"
    assert queue.jobs[0].payload["employee"] == {
        "id": "20000000-0000-4000-8000-000000000001"
    }


async def test_recording_job_queue_supports_injected_deterministic_ids() -> None:
    queue = RecordingJobQueue(id_factory=lambda: "provider-job-001")

    queued = await queue.enqueue(_valid_job())

    assert queued.id == "provider-job-001"


async def test_recording_job_queue_receives_immutable_serialized_safe_context() -> None:
    request_context = RequestContext(
        request_id="request-001",
        trace_id=TRACE_ID,
        tenant=TenantContext(tenant_id=TENANT_ID, slug="never-transported"),
        authentication_strength=AuthenticationStrength.SINGLE_FACTOR,
    ).serialize_for_worker()
    job = JobSpec(
        task_name="employees.export",
        tenant_id=TENANT_ID,
        idempotency_key="export-request-001",
        payload={},
        timeout_seconds=120,
        max_attempts=3,
        correlation_id="request-001",
        request_context=request_context,
    )
    request_context["request_id"] = "mutated-after-construction"
    queue = RecordingJobQueue()

    await queue.enqueue(job)

    assert queue.jobs[0].request_context_for_transport() == {
        "request_id": "request-001",
        "trace_id": TRACE_ID,
        "tenant_id": str(TENANT_ID),
        "actor_id": None,
        "session_id": None,
        "authentication_strength": "single_factor",
        "support_session_id": None,
        "support_operator_actor_id": None,
    }
    assert "never-transported" not in repr(queue.jobs[0].request_context)
    assert isinstance(queue.jobs[0].request_context, Mapping)
    with pytest.raises(TypeError):
        queue.jobs[0].request_context["request_id"] = "mutated"  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda context: context.update({"authorization": "Bearer secret"}), "allowlist"),
        (lambda context: context.update({"tenant_id": str(OTHER_TENANT_ID)}), "tenant_id"),
        (lambda context: context.update({"authentication_strength": "raw-token"}), "strength"),
        (lambda context: context.update({"trace_id": "not-a-trace"}), "correlation"),
    ],
)
def test_job_spec_rejects_unsafe_or_cross_tenant_serialized_context(
    mutate,
    message: str,
) -> None:
    context = RequestContext(
        request_id="request-001",
        trace_id=TRACE_ID,
        tenant=TenantContext(tenant_id=TENANT_ID, slug="worker-test"),
    ).serialize_for_worker()
    mutate(context)

    with pytest.raises(ValueError, match=message):
        JobSpec(
            task_name="employees.export",
            tenant_id=TENANT_ID,
            idempotency_key="export-request-001",
            payload={},
            timeout_seconds=120,
            max_attempts=3,
            request_context=context,
        )


def test_recording_job_queue_rejects_tenant_a_context_for_tenant_b_before_enqueue() -> None:
    queue = RecordingJobQueue()

    with pytest.raises(ValueError, match="request_context tenant_id must match"):
        JobSpec(
            task_name="employees.export",
            tenant_id=OTHER_TENANT_ID,
            idempotency_key="export-request-001",
            payload={},
            timeout_seconds=120,
            max_attempts=3,
            request_context=_worker_request_context(),
        )

    assert queue.jobs == ()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"task_name": ""}, "task_name"),
        ({"tenant_id": UUID(int=0)}, "tenant_id"),
        ({"idempotency_key": " retry-key "}, "idempotency_key"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": 1.5}, "timeout_seconds"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"max_attempts": True}, "max_attempts"),
        ({"queue": " "}, "queue"),
        ({"correlation_id": " request-001"}, "correlation_id"),
        ({"payload": ["not", "an", "object"]}, "payload"),
        ({"payload": {"invalid": float("nan")}}, "payload"),
    ],
)
def test_job_spec_fails_closed_without_required_safeguards(
    overrides: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "task_name": "employees.export",
        "tenant_id": TENANT_ID,
        "idempotency_key": "export-request-001",
        "payload": {"employee_id": "20000000-0000-4000-8000-000000000001"},
        "timeout_seconds": 120,
        "max_attempts": 3,
        "queue": "exports",
        "correlation_id": "request-001",
    }
    values.update(overrides)

    with pytest.raises(ValueError, match=message):
        JobSpec(**values)  # type: ignore[arg-type]


def _valid_job() -> JobSpec:
    return JobSpec(
        task_name="employees.export",
        tenant_id=TENANT_ID,
        idempotency_key="export-request-001",
        payload={},
        timeout_seconds=120,
        max_attempts=3,
        queue="exports",
    )


def _worker_request_context() -> dict[str, object]:
    return RequestContext(
        request_id="request-001",
        trace_id=TRACE_ID,
        tenant=TenantContext(tenant_id=TENANT_ID, slug="worker-test"),
    ).serialize_for_worker()
