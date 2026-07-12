"""Trusted principal contracts injected at the HTTP boundary.

Phase 1 defines only the narrow context required by the tenant foundation. Authentication,
sessions, roles, and actor identity remain Phase 2 concerns; callers cannot construct either
principal through request headers or payload fields.
"""

from dataclasses import dataclass
from uuid import UUID

from app.platform.request_context import AuthenticationStrength


@dataclass(frozen=True, slots=True)
class PlatformPrincipal:
    """Validated platform-realm principal, with legacy injection compatibility for tests."""

    source: str
    identity_id: UUID | None = None
    session_family_id: UUID | None = None
    authentication_strength: AuthenticationStrength = AuthenticationStrength.UNAUTHENTICATED

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Platform principal source is required")
        for field_name in ("identity_id", "session_family_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, UUID) or value.int == 0):
                raise ValueError(f"Platform principal {field_name} must be a non-zero UUID")
        if not isinstance(self.authentication_strength, AuthenticationStrength):
            raise TypeError("Platform principal authentication strength is invalid")


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    """Tenant scope authorized by a trusted upstream adapter for this foundation surface."""

    tenant_id: UUID
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID) or self.tenant_id.int == 0:
            raise ValueError("Tenant principal ID must be a non-zero UUID")
        if not self.source.strip():
            raise ValueError("Tenant principal source is required")


__all__ = ["PlatformPrincipal", "TenantPrincipal"]
