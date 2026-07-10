from uuid import UUID

import pytest
from app.core.tenancy import TenantContext as LegacyTenantContext
from app.platform.tenancy import TenantContext


def test_legacy_tenant_context_import_reexports_canonical_type() -> None:
    assert LegacyTenantContext is TenantContext


def test_tenant_context_cache_prefix_is_tenant_scoped() -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    ctx = TenantContext(tenant_id=tenant_id, slug="acme")

    assert ctx.cache_prefix() == f"tenant:{tenant_id}:"


def test_tenant_context_cache_key_keeps_same_resource_separate_by_tenant() -> None:
    first_tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    second_tenant_id = UUID("22222222-2222-4222-8222-222222222222")
    first = TenantContext(tenant_id=first_tenant_id, slug="acme")
    second = TenantContext(tenant_id=second_tenant_id, slug="acme")

    assert first.cache_key("users", "active") == f"tenant:{first_tenant_id}:users:active"
    assert second.cache_key("users", "active") == f"tenant:{second_tenant_id}:users:active"
    assert first.cache_key("users", "active") != second.cache_key("users", "active")


def test_tenant_context_cache_key_rejects_empty_parts() -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    ctx = TenantContext(tenant_id=tenant_id, slug="acme")

    with pytest.raises(ValueError, match="Cache key parts"):
        ctx.cache_key("users", " ")


def test_tenant_context_requires_non_empty_slug() -> None:
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")

    with pytest.raises(ValueError, match="Tenant slug"):
        TenantContext(tenant_id=tenant_id, slug=" ")
