"""Idempotent transaction boundary for announcement writes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from app.platform.db import UnitOfWork
from app.platform.idempotency import command_fingerprint
from app.platform.request_context import RequestContext
from app.schemas.announcement import (
    AnnouncementCreate,
    AnnouncementDetailRead,
    AnnouncementUpdate,
)
from app.services.announcement_service import AnnouncementService
from app.services.command_idempotency import (
    CommandIdempotencyService,
    IdempotentCommandExecutor,
)


@dataclass(slots=True)
class AnnouncementCommandHandler:
    service: AnnouncementService
    unit_of_work: UnitOfWork
    idempotency: CommandIdempotencyService

    async def create(
        self,
        *,
        context: RequestContext,
        payload: AnnouncementCreate,
        idempotency_key: str | None,
    ) -> AnnouncementDetailRead:
        return await self._execute(
            context=context,
            command="announcements.create.v1",
            fingerprint={"payload": payload.model_dump(mode="json")},
            idempotency_key=idempotency_key,
            operation=lambda: self.service.create(request_context=context, payload=payload),
        )

    async def update(
        self,
        *,
        context: RequestContext,
        announcement_id: UUID,
        payload: AnnouncementUpdate,
        idempotency_key: str | None,
    ) -> AnnouncementDetailRead:
        return await self._execute(
            context=context,
            command="announcements.update.v1",
            fingerprint={
                "announcement_id": str(announcement_id),
                "payload": payload.model_dump(mode="json", exclude_unset=True),
            },
            idempotency_key=idempotency_key,
            operation=lambda: self.service.update(
                request_context=context,
                announcement_id=announcement_id,
                payload=payload,
            ),
        )

    async def version_action(
        self,
        *,
        context: RequestContext,
        announcement_id: UUID,
        expected_version: int,
        action: str,
        idempotency_key: str | None,
    ) -> AnnouncementDetailRead:
        operations: dict[str, Callable[[], Awaitable[AnnouncementDetailRead]]] = {
            "publish": lambda: self.service.publish(
                request_context=context,
                announcement_id=announcement_id,
                expected_version=expected_version,
            ),
            "archive": lambda: self.service.archive(
                request_context=context,
                announcement_id=announcement_id,
                expected_version=expected_version,
            ),
            "read": lambda: self.service.mark_read(
                request_context=context,
                announcement_id=announcement_id,
                expected_version=expected_version,
            ),
            "ack": lambda: self.service.acknowledge(
                request_context=context,
                announcement_id=announcement_id,
                expected_version=expected_version,
            ),
        }
        operation = operations.get(action)
        if operation is None:
            raise ValueError("Unsupported announcement action")
        return await self._execute(
            context=context,
            command=f"announcements.{action}.v1",
            fingerprint={
                "announcement_id": str(announcement_id),
                "expected_version": expected_version,
            },
            idempotency_key=idempotency_key,
            operation=operation,
        )

    async def _execute(
        self,
        *,
        context: RequestContext,
        command: str,
        fingerprint: dict[str, object],
        idempotency_key: str | None,
        operation: Callable[[], Awaitable[AnnouncementDetailRead]],
    ) -> AnnouncementDetailRead:
        if context.actor_id is None:
            raise RuntimeError("Announcement command requires an actor")
        return await IdempotentCommandExecutor(
            service=self.idempotency,
            unit_of_work=self.unit_of_work,
        ).execute(
            tenant_id=context.require_tenant().tenant_id,
            idempotency_key=idempotency_key,
            command_name=command,
            request_fingerprint=command_fingerprint(
                {
                    "actor_id": str(context.actor_id),
                    "membership_id": str(context.require_membership()),
                    **fingerprint,
                }
            ),
            operation=operation,
            serialize=lambda item: item.model_dump(mode="json"),
            deserialize=AnnouncementDetailRead.model_validate,
        )


__all__ = ["AnnouncementCommandHandler"]
