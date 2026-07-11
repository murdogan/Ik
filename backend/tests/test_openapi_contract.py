from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.main import create_app

HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
F1A_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "f1a_openapi_contract.json"
F1B_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "f1b_openapi_contract.json"
F1D_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "f1d_openapi_contract.json"
F1E_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "f1e_openapi_contract.json"
PHASE0_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "phase0_openapi_contract.json"
F1A_ADDITIVE_OPERATIONS = {
    "GET /api/v1/platform/tenants",
    "GET /api/v1/platform/tenants/{tenant_id}",
    "GET /api/v1/tenant",
    "GET /api/v1/tenant/settings",
    "PATCH /api/v1/platform/tenants/{tenant_id}",
    "PATCH /api/v1/tenant/settings",
    "POST /api/v1/platform/tenants",
}
F1B_APPROVED_OPERATION_MIGRATIONS = {
    "GET /api/v1/platform/tenants",
    "GET /api/v1/platform/tenants/{tenant_id}",
    "GET /api/v1/tenant",
    "GET /api/v1/tenant/settings",
    "PATCH /api/v1/platform/tenants/{tenant_id}",
    "PATCH /api/v1/tenant/settings",
    "POST /api/v1/platform/tenants",
}
F1D_ADDITIVE_OPERATIONS = {
    "GET /api/v1/platform/tenants/{tenant_id}/features",
    "GET /api/v1/tenant/features",
    "PATCH /api/v1/platform/tenants/{tenant_id}/features",
}
F1D_APPROVED_OPERATION_MIGRATIONS = {
    "GET /api/v1/platform/tenants",
    "GET /api/v1/platform/tenants/{tenant_id}",
    "PATCH /api/v1/platform/tenants/{tenant_id}",
    "POST /api/v1/platform/tenants",
}
F1D_APPROVED_COMPONENT_MIGRATIONS = {
    "TenantPlatformCreate",
    "TenantPlatformRead",
    "TenantPlatformUpdate",
}
F1D_ADDITIVE_SCHEMA_COMPONENTS = {
    "DataEnvelope_TenantFeaturesRead_",
    "FeatureFlagKey",
    "TenantFeatureFlagRead",
    "TenantFeatureFlagUpdate",
    "TenantFeaturesRead",
    "TenantFeaturesUpdate",
    "TenantLimitsProvision",
    "TenantLimitsRead",
    "TenantLimitsUpdate",
}
F1E_PRINCIPAL_METADATA_MIGRATIONS = {
    "GET /api/v1/platform/tenants",
    "GET /api/v1/platform/tenants/{tenant_id}",
    "GET /api/v1/platform/tenants/{tenant_id}/features",
    "GET /api/v1/tenant",
    "GET /api/v1/tenant/features",
    "GET /api/v1/tenant/settings",
    "PATCH /api/v1/platform/tenants/{tenant_id}",
    "PATCH /api/v1/platform/tenants/{tenant_id}/features",
    "PATCH /api/v1/tenant/settings",
    "POST /api/v1/platform/tenants",
}


def test_f1e_openapi_contract_matches_review_snapshot() -> None:
    snapshot = json.loads(F1E_SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert snapshot["format_version"] == 1
    assert snapshot["checkpoint"] == "F1E Phase 1 security gate and review checkpoint"
    assert snapshot["comparison_base"] == "54a3678"
    assert snapshot["contract"]["operation_count"] == 24
    current = build_openapi_contract_manifest(create_app().openapi())

    # The snapshot remains a historical Phase-1 compatibility checkpoint. F2 adds operations,
    # schemas, tags, and a bearer scheme; project only the frozen Phase-1 surface instead of
    # manufacturing a broad duplicate snapshot before the planned F2F reconciliation.
    assert {
        operation: current["operations"].get(operation)
        for operation in snapshot["contract"]["operations"]
    } == snapshot["contract"]["operations"]
    for group_name, components in snapshot["contract"]["components"].items():
        assert {
            component: current["components"].get(group_name, {}).get(component)
            for component in components
        } == components


def test_f1e_contract_preserves_every_phase0_operation_and_component() -> None:
    phase0 = _load_contract(PHASE0_SNAPSHOT_PATH)
    current = build_openapi_contract_manifest(create_app().openapi())

    assert {
        operation: current["operations"].get(operation)
        for operation in phase0["operations"]
    } == phase0["operations"]
    for group_name, components in phase0["components"].items():
        assert {
            component: current["components"].get(group_name, {}).get(component)
            for component in components
        } == components


def test_historical_f1a_is_the_approved_additive_phase0_contract() -> None:
    phase0 = _load_contract(PHASE0_SNAPSHOT_PATH)
    f1a = _load_contract(F1A_SNAPSHOT_PATH)

    assert set(f1a["operations"]) == set(phase0["operations"]) | F1A_ADDITIVE_OPERATIONS
    assert {
        operation: f1a["operations"].get(operation)
        for operation in phase0["operations"]
    } == phase0["operations"]
    for group_name, components in phase0["components"].items():
        assert {
            component: f1a["components"].get(group_name, {}).get(component)
            for component in components
        } == components


def test_historical_f1b_delta_from_f1a_is_the_approved_contract_migration() -> None:
    f1a = _load_contract(F1A_SNAPSHOT_PATH)
    f1b = _load_contract(F1B_SNAPSHOT_PATH)

    assert set(f1b["operations"]) == set(f1a["operations"])
    assert {
        operation
        for operation, digest in f1b["operations"].items()
        if digest != f1a["operations"][operation]
    } == F1B_APPROVED_OPERATION_MIGRATIONS

    for group_name, historical_components in f1a["components"].items():
        assert {
            component: f1b["components"].get(group_name, {}).get(component)
            for component in historical_components
        } == historical_components


def test_f1d_delta_from_f1b_is_additive_features_and_approved_limits_migration() -> None:
    f1b = _load_contract(F1B_SNAPSHOT_PATH)
    f1d = _load_contract(F1D_SNAPSHOT_PATH)

    assert set(f1d["operations"]) - set(f1b["operations"]) == F1D_ADDITIVE_OPERATIONS
    assert set(f1b["operations"]) - set(f1d["operations"]) == set()
    assert {
        operation
        for operation, digest in f1b["operations"].items()
        if digest != f1d["operations"][operation]
    } == F1D_APPROVED_OPERATION_MIGRATIONS

    f1b_schemas = f1b["components"]["schemas"]
    f1d_schemas = f1d["components"]["schemas"]
    assert set(f1d_schemas) - set(f1b_schemas) == F1D_ADDITIVE_SCHEMA_COMPONENTS
    assert set(f1b_schemas) - set(f1d_schemas) == set()
    assert {
        component
        for component, digest in f1b_schemas.items()
        if digest != f1d_schemas[component]
    } == F1D_APPROVED_COMPONENT_MIGRATIONS
    assert f1d["top_level_sha256"] != f1b["top_level_sha256"]


def test_f1e_delta_from_f1d_is_only_required_principal_metadata() -> None:
    f1d = _load_contract(F1D_SNAPSHOT_PATH)
    f1e = _load_contract(F1E_SNAPSHOT_PATH)

    assert set(f1e["operations"]) == set(f1d["operations"])
    assert {
        operation
        for operation, digest in f1e["operations"].items()
        if digest != f1d["operations"][operation]
    } == F1E_PRINCIPAL_METADATA_MIGRATIONS
    assert f1e["components"] == f1d["components"]
    assert f1e["top_level_sha256"] == f1d["top_level_sha256"]


def build_openapi_contract_manifest(openapi: dict[str, Any]) -> dict[str, Any]:
    operations = {
        f"{method.upper()} {path}": _digest(operation)
        for path, path_item in sorted(openapi["paths"].items())
        for method, operation in sorted(path_item.items())
        if method in HTTP_METHODS
    }
    component_groups = {
        group_name: {
            component_name: _digest(component)
            for component_name, component in sorted(group.items())
        }
        for group_name, group in sorted(openapi.get("components", {}).items())
    }
    top_level = {
        key: value for key, value in openapi.items() if key not in {"components", "paths"}
    }

    return {
        "operation_count": len(operations),
        "operations": operations,
        "components": component_groups,
        "top_level_sha256": _digest(top_level),
    }


def _load_contract(path: Path) -> dict[str, Any]:
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert snapshot["format_version"] == 1
    return snapshot["contract"]


def _digest(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()
