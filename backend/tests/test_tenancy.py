from uuid import UUID

from app.core.tenancy import TenantContext


def test_tenant_context_cache_prefix_is_tenant_scoped() -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    ctx = TenantContext(tenant_id=tenant_id, slug="acme")

    assert ctx.cache_prefix() == f"tenant:{tenant_id}:"
