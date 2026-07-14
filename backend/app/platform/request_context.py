"""Immutable request metadata shared across HTTP and worker boundaries.

The context deliberately contains opaque identifiers only.  Authentication credentials,
principal sources, tenant slugs, support reasons, and other free text do not belong here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from re import compile as compile_regex
from types import MappingProxyType
from typing import TypedDict
from uuid import UUID

from app.platform.tenancy import TenantContext

MAX_REQUEST_ID_LENGTH = 128
_REQUEST_ID_PATTERN = compile_regex(
    rf"[A-Za-z0-9](?:[A-Za-z0-9._-]{{0,{MAX_REQUEST_ID_LENGTH - 2}}}[A-Za-z0-9])?"
)
_TRACE_ID_PATTERN = compile_regex(r"[0-9a-f]{32}")


class AuthenticationStrength(StrEnum):
    """Authentication assurance attached by a trusted boundary.

    Phase 1 creates unauthenticated contexts.  The remaining values are typed placeholders for
    the Phase 2 authentication adapter; they do not grant authorization by themselves.
    """

    UNAUTHENTICATED = "unauthenticated"
    SINGLE_FACTOR = "single_factor"
    MULTI_FACTOR = "multi_factor"
    STEP_UP = "step_up"


@dataclass(frozen=True, slots=True)
class SupportSessionMetadata:
    """Opaque support-session identifiers safe to carry through application code.

    Ticket references, reasons, requested scopes, and principal source strings are intentionally
    excluded.  Those values belong to a future authorized support-session record and audit policy.
    """

    support_session_id: UUID
    operator_actor_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_non_zero_uuid("support_session_id", self.support_session_id)
        if self.operator_actor_id is not None:
            _require_non_zero_uuid("operator_actor_id", self.operator_actor_id)


class WorkerRequestContext(TypedDict):
    """Fixed, JSON-safe allowlist for propagating a request context to a worker."""

    request_id: str
    trace_id: str
    tenant_id: str
    actor_id: str | None
    membership_id: str | None
    session_id: str | None
    authentication_strength: str
    support_session_id: str | None
    support_operator_actor_id: str | None


class _Unchanged:
    __slots__ = ()


_UNCHANGED = _Unchanged()


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Deeply immutable request-scoped operational context.

    Correlation identifiers are fixed for the lifetime of the object graph.  ``derive`` only
    enriches tenant, actor/membership/session, authentication-strength, and support-session
    placeholders and always returns a new validated instance.
    """

    request_id: str
    trace_id: str
    tenant: TenantContext | None = None
    actor_id: UUID | None = None
    membership_id: UUID | None = None
    session_id: UUID | None = None
    authentication_strength: AuthenticationStrength = AuthenticationStrength.UNAUTHENTICATED
    support_session: SupportSessionMetadata | None = None

    def __post_init__(self) -> None:
        if not is_valid_request_id(self.request_id):
            raise ValueError("request_id must be a safe opaque request identifier")
        if not is_valid_trace_id(self.trace_id):
            raise ValueError("trace_id must be a canonical non-zero 32-character lowercase hex ID")
        if self.tenant is not None:
            if not isinstance(self.tenant, TenantContext):
                raise TypeError("tenant must be a TenantContext or None")
            _require_non_zero_uuid("tenant.tenant_id", self.tenant.tenant_id)
        if self.actor_id is not None:
            _require_non_zero_uuid("actor_id", self.actor_id)
        if self.membership_id is not None:
            _require_non_zero_uuid("membership_id", self.membership_id)
        if self.session_id is not None:
            _require_non_zero_uuid("session_id", self.session_id)
        if not isinstance(self.authentication_strength, AuthenticationStrength):
            raise TypeError("authentication_strength must be an AuthenticationStrength")
        if self.support_session is not None and not isinstance(
            self.support_session, SupportSessionMetadata
        ):
            raise TypeError("support_session must be SupportSessionMetadata or None")

    def derive(
        self,
        *,
        tenant: TenantContext | None | _Unchanged = _UNCHANGED,
        actor_id: UUID | None | _Unchanged = _UNCHANGED,
        membership_id: UUID | None | _Unchanged = _UNCHANGED,
        session_id: UUID | None | _Unchanged = _UNCHANGED,
        authentication_strength: AuthenticationStrength | _Unchanged = _UNCHANGED,
        support_session: SupportSessionMetadata | None | _Unchanged = _UNCHANGED,
    ) -> RequestContext:
        """Return a validated enrichment while preserving correlation identifiers."""

        changes: dict[str, object] = {}
        if tenant is not _UNCHANGED:
            changes["tenant"] = tenant
        if actor_id is not _UNCHANGED:
            changes["actor_id"] = actor_id
        if membership_id is not _UNCHANGED:
            changes["membership_id"] = membership_id
        if session_id is not _UNCHANGED:
            changes["session_id"] = session_id
        if authentication_strength is not _UNCHANGED:
            changes["authentication_strength"] = authentication_strength
        if support_session is not _UNCHANGED:
            changes["support_session"] = support_session
        return replace(self, **changes)

    def safe_error_metadata(self) -> Mapping[str, str]:
        """Return the only correlation fields suitable for a public error body."""

        return MappingProxyType(
            {
                "request_id": self.request_id,
                "trace_id": self.trace_id,
            }
        )

    def safe_log_metadata(self) -> Mapping[str, str]:
        """Return allowlisted opaque fields for structured operational logs."""

        metadata = {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "authentication_strength": self.authentication_strength.value,
        }
        if self.tenant is not None:
            metadata["tenant_id"] = str(self.tenant.tenant_id)
        if self.support_session is not None:
            metadata["support_session_id"] = str(
                self.support_session.support_session_id
            )
        return MappingProxyType(metadata)

    def require_tenant(self) -> TenantContext:
        """Return trusted tenant scope or fail closed at an application boundary."""

        if self.tenant is None:
            raise RuntimeError("A tenant-scoped RequestContext is required")
        return self.tenant

    def require_membership(self) -> UUID:
        """Return the authenticated tenant membership or fail closed."""

        if self.membership_id is None:
            raise RuntimeError("An authenticated membership is required")
        return self.membership_id

    def serialize_for_worker(self) -> WorkerRequestContext:
        """Serialize the safe propagation allowlist; tenantless work fails closed."""

        tenant = self.require_tenant()

        support_session_id: str | None = None
        support_operator_actor_id: str | None = None
        if self.support_session is not None:
            support_session_id = str(self.support_session.support_session_id)
            if self.support_session.operator_actor_id is not None:
                support_operator_actor_id = str(self.support_session.operator_actor_id)

        return WorkerRequestContext(
            request_id=self.request_id,
            trace_id=self.trace_id,
            tenant_id=str(tenant.tenant_id),
            actor_id=str(self.actor_id) if self.actor_id is not None else None,
            membership_id=(
                str(self.membership_id) if self.membership_id is not None else None
            ),
            session_id=str(self.session_id) if self.session_id is not None else None,
            authentication_strength=self.authentication_strength.value,
            support_session_id=support_session_id,
            support_operator_actor_id=support_operator_actor_id,
        )

    def to_worker_context(self) -> WorkerRequestContext:
        """Compatibility spelling for adapters that treat the payload as a DTO."""

        return self.serialize_for_worker()


def _require_non_zero_uuid(field_name: str, value: object) -> None:
    if not isinstance(value, UUID) or value.int == 0:
        raise ValueError(f"{field_name} must be a non-zero UUID")


def is_valid_request_id(value: object) -> bool:
    """Return whether ``value`` is a bounded, log-safe opaque request token."""

    return (
        isinstance(value, str)
        and value.count(".") < 2
        and _REQUEST_ID_PATTERN.fullmatch(value) is not None
    )


def is_valid_trace_id(value: object) -> bool:
    """Return whether ``value`` is a canonical W3C-style trace identifier."""

    return (
        isinstance(value, str)
        and value != "0" * 32
        and _TRACE_ID_PATTERN.fullmatch(value) is not None
    )


__all__ = [
    "AuthenticationStrength",
    "MAX_REQUEST_ID_LENGTH",
    "RequestContext",
    "SupportSessionMetadata",
    "WorkerRequestContext",
    "is_valid_request_id",
    "is_valid_trace_id",
]
