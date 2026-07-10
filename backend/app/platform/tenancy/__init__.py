"""Tenant context primitives shared across request and application boundaries."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    slug: str

    def __post_init__(self) -> None:
        if not self.slug.strip():
            raise ValueError("Tenant slug is required")

    def cache_prefix(self) -> str:
        return f"tenant:{self.tenant_id}:"

    def cache_key(self, *parts: str) -> str:
        if not parts:
            raise ValueError("Cache key parts are required")

        clean_parts: list[str] = []
        for part in parts:
            clean_part = part.strip()
            if not clean_part:
                raise ValueError("Cache key parts must be non-empty")
            if ":" in clean_part:
                raise ValueError("Cache key parts must not contain ':'")
            clean_parts.append(clean_part)

        return f"{self.cache_prefix()}{':'.join(clean_parts)}"


__all__ = ["TenantContext"]
