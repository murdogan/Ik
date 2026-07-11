from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.main import create_app

HTTP_METHODS = {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "f1a_openapi_contract.json"
PHASE0_SNAPSHOT_PATH = Path(__file__).parent / "contracts" / "phase0_openapi_contract.json"


def test_f1a_openapi_contract_matches_review_snapshot() -> None:
    snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

    assert snapshot["format_version"] == 1
    assert snapshot["contract"] == build_openapi_contract_manifest(create_app().openapi())


def test_f1a_contract_preserves_every_phase0_operation_and_component() -> None:
    phase0 = json.loads(PHASE0_SNAPSHOT_PATH.read_text(encoding="utf-8"))["contract"]
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


def _digest(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()
