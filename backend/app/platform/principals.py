"""Trusted principal contracts injected at the HTTP boundary.

Phase 1 defines only the narrow context required by the tenant foundation. Authentication,
sessions, roles, and actor identity remain Phase 2 concerns; callers cannot construct either
principal through request headers or payload fields.
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class PlatformPrincipal:
    """Proof that an upstream, trusted adapter authorized platform tenant operations."""

    source: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Platform principal source is required")


@dataclass(frozen=True, slots=True)
class TenantPrincipal:
    """Tenant scope authorized by a trusted upstream adapter for this foundation surface."""

    tenant_id: UUID
    source: str

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("Tenant principal source is required")


__all__ = ["PlatformPrincipal", "TenantPrincipal"]
