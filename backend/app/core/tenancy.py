from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TenantContext:
    tenant_id: UUID
    slug: str

    def cache_prefix(self) -> str:
        return f"tenant:{self.tenant_id}:"
