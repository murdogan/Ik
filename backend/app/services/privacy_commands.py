"""Atomic and optionally idempotent command boundary for privacy mutations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.models.privacy import PrivacyConsentAction
from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.schemas.privacy import (
    ConsentPurposeStateRead,
    EmployeePrivacyNoticeRead,
    PrivacyNoticeAcknowledge,
    PrivacyNoticeCreate,
    PrivacyNoticeDetailRead,
    PrivacyNoticePublish,
    PrivacyNoticeUpdate,
    RetentionDryRunRead,
    RetentionDryRunRequest,
    RetentionPolicyCreate,
    RetentionPolicyRead,
    RetentionPolicyUpdate,
)
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)
from app.services.privacy_service import PrivacyService

_ResponseT = TypeVar("_ResponseT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class _AcknowledgementCommandResult:
    id: UUID
    response: EmployeePrivacyNoticeRead


@dataclass(slots=True)
class PrivacyCommandHandler:
    service: PrivacyService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService

    async def create_notice(
        self,
        *,
        context: RequestContext,
        payload: PrivacyNoticeCreate,
        idempotency_key: str | None,
    ) -> PrivacyNoticeDetailRead:
        return await self._execute_model(
            context=context,
            command="privacy.notices.create.v1",
            fingerprint={"payload": payload.model_dump(mode="json")},
            idempotency_key=idempotency_key,
            operation=lambda: self.service.create_notice(
                request_context=context,
                payload=payload,
            ),
            response_model=PrivacyNoticeDetailRead,
        )

    async def update_notice(
        self,
        *,
        context: RequestContext,
        notice_id: UUID,
        payload: PrivacyNoticeUpdate,
        idempotency_key: str | None,
    ) -> PrivacyNoticeDetailRead:
        return await self._execute_model(
            context=context,
            command="privacy.notices.update.v1",
            fingerprint={
                "notice_id": str(notice_id),
                "payload": payload.model_dump(mode="json", exclude_unset=True),
            },
            idempotency_key=idempotency_key,
            operation=lambda: self.service.update_notice(
                request_context=context,
                notice_id=notice_id,
                payload=payload,
            ),
            response_model=PrivacyNoticeDetailRead,
        )

    async def publish_notice(
        self,
        *,
        context: RequestContext,
        notice_id: UUID,
        payload: PrivacyNoticePublish,
        idempotency_key: str | None,
    ) -> PrivacyNoticeDetailRead:
        return await self._execute_model(
            context=context,
            command="privacy.notices.publish.v1",
            fingerprint={
                "notice_id": str(notice_id),
                "payload": payload.model_dump(mode="json"),
            },
            idempotency_key=idempotency_key,
            operation=lambda: self.service.publish_notice(
                request_context=context,
                notice_id=notice_id,
                expected_revision=payload.expected_revision,
            ),
            response_model=PrivacyNoticeDetailRead,
        )

    async def acknowledge_notice(
        self,
        *,
        context: RequestContext,
        payload: PrivacyNoticeAcknowledge,
        idempotency_key: str | None,
    ) -> EmployeePrivacyNoticeRead:
        async def operation() -> _AcknowledgementCommandResult:
            response = await self.service.acknowledge_notice(
                request_context=context,
                payload=payload,
            )
            return _AcknowledgementCommandResult(id=payload.notice_id, response=response)

        def deserialize(value: dict[str, object]) -> _AcknowledgementCommandResult:
            response = EmployeePrivacyNoticeRead.model_validate(value)
            if response.notice is None:
                raise RuntimeError("Acknowledgement replay is missing its notice")
            return _AcknowledgementCommandResult(id=response.notice.id, response=response)

        result = await IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        ).execute(
            tenant_id=context.require_tenant().tenant_id,
            idempotency_key=idempotency_key,
            command_name="privacy.notices.acknowledge.v1",
            request_fingerprint=_command_fingerprint(
                context,
                {"payload": payload.model_dump(mode="json")},
            ),
            operation=operation,
            serialize=lambda item: item.response.model_dump(mode="json"),
            deserialize=deserialize,
        )
        return result.response

    async def transition_consent(
        self,
        *,
        context: RequestContext,
        purpose_id: UUID,
        action: PrivacyConsentAction,
        idempotency_key: str | None,
    ) -> ConsentPurposeStateRead:
        return await self._execute_model(
            context=context,
            command=f"privacy.consents.{action.value}.v1",
            fingerprint={
                "purpose_id": str(purpose_id),
                "action": action.value,
                "payload": {},
            },
            idempotency_key=idempotency_key,
            operation=lambda: self.service.transition_consent(
                request_context=context,
                purpose_id=purpose_id,
                action=action,
            ),
            response_model=ConsentPurposeStateRead,
        )

    async def create_retention_policy(
        self,
        *,
        context: RequestContext,
        payload: RetentionPolicyCreate,
        idempotency_key: str | None,
    ) -> RetentionPolicyRead:
        return await self._execute_model(
            context=context,
            command="privacy.retention_policies.create.v1",
            fingerprint={"payload": payload.model_dump(mode="json")},
            idempotency_key=idempotency_key,
            operation=lambda: self.service.create_retention_policy(
                request_context=context,
                payload=payload,
            ),
            response_model=RetentionPolicyRead,
        )

    async def update_retention_policy(
        self,
        *,
        context: RequestContext,
        policy_id: UUID,
        payload: RetentionPolicyUpdate,
        idempotency_key: str | None,
    ) -> RetentionPolicyRead:
        return await self._execute_model(
            context=context,
            command="privacy.retention_policies.update.v1",
            fingerprint={
                "policy_id": str(policy_id),
                "payload": payload.model_dump(mode="json", exclude_unset=True),
            },
            idempotency_key=idempotency_key,
            operation=lambda: self.service.update_retention_policy(
                request_context=context,
                policy_id=policy_id,
                payload=payload,
            ),
            response_model=RetentionPolicyRead,
        )

    async def retention_dry_run(
        self,
        *,
        context: RequestContext,
        payload: RetentionDryRunRequest,
    ) -> RetentionDryRunRead:
        return await self.unit_of_work.execute(
            lambda: self.service.retention_dry_run(
                request_context=context,
                payload=payload,
            )
        )

    async def _execute_model(
        self,
        *,
        context: RequestContext,
        command: str,
        fingerprint: dict[str, object],
        idempotency_key: str | None,
        operation: Callable[[], Awaitable[_ResponseT]],
        response_model: type[_ResponseT],
    ) -> _ResponseT:
        return await IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        ).execute(
            tenant_id=context.require_tenant().tenant_id,
            idempotency_key=idempotency_key,
            command_name=command,
            request_fingerprint=_command_fingerprint(context, fingerprint),
            operation=operation,
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=response_model.model_validate,
        )


def _command_fingerprint(context: RequestContext, payload: dict[str, object]) -> str:
    if context.actor_id is None:
        raise RuntimeError("Privacy commands require an authenticated actor")
    return command_fingerprint(
        {
            "actor_id": str(context.actor_id),
            "membership_id": str(context.require_membership()),
            **payload,
        }
    )


__all__ = ["PrivacyCommandHandler"]
