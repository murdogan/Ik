from __future__ import annotations

import ast
from collections import defaultdict
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from sys import stdlib_module_names
from textwrap import dedent

import pytest

APP_ROOT = Path(__file__).resolve().parents[1] / "app"

EXPECTED_PLATFORM_PACKAGES = {
    "authorization",
    "audit",
    "config",
    "db",
    "errors",
    "events",
    "identity",
    "idempotency",
    "observability",
    "storage",
    "tenancy",
    "workers",
}
EXPECTED_MODULE_PACKAGES = {
    "core",
    "documents",
    "employees",
    "leave",
    "notifications",
    "organization",
    "reporting",
    "self_service",
}

LAYERS = {"domain", "application", "infrastructure", "presentation"}
ALLOWED_LAYER_IMPORTS = {
    "domain": {"domain"},
    "application": {"domain", "application"},
    "infrastructure": {"domain", "application", "infrastructure"},
    "presentation": {"application", "presentation"},
}
DOMAIN_FRAMEWORK_ROOTS = {
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
}
APPLICATION_FRAMEWORK_ROOTS = {
    "fastapi",
    "pydantic_settings",
    "sqlalchemy",
}
CONCRETE_PLATFORM_INTERNALS = {
    "app.platform.config",
    "app.platform.db",
    "app.platform.observability",
    "app.platform.storage",
    "app.platform.workers.fake",
}


def _module_name(path: Path, app_root: Path) -> str:
    relative_parts = path.relative_to(app_root).with_suffix("").parts
    if relative_parts[-1] == "__init__":
        relative_parts = relative_parts[:-1]
    return ".".join(("app", *relative_parts))


def _resolve_import_base(
    node: ast.ImportFrom,
    *,
    source_module: str,
    source_is_package: bool,
) -> str:
    if node.level == 0:
        return node.module or ""

    source_package = source_module if source_is_package else source_module.rpartition(".")[0]
    package_parts = source_package.split(".") if source_package else []
    parent_hops = node.level - 1
    if parent_hops > len(package_parts):
        return ""

    base_parts = package_parts[: len(package_parts) - parent_hops]
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


def _import_targets(path: Path, app_root: Path) -> set[str]:
    source_module = _module_name(path, app_root)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue

        base = _resolve_import_base(
            node,
            source_module=source_module,
            source_is_package=path.name == "__init__.py",
        )
        if base:
            targets.add(base)
        for alias in node.names:
            if alias.name != "*":
                targets.add(".".join(part for part in (base, alias.name) if part))

    return targets


def _matches_root(target: str, root: str) -> bool:
    return target == root or target.startswith(f"{root}.")


def _target_module_parts(module_name: str) -> tuple[str, str | None] | None:
    parts = module_name.split(".")
    if len(parts) < 3 or parts[:2] != ["app", "modules"]:
        return None
    layer = parts[3] if len(parts) > 3 and parts[3] in LAYERS else None
    return parts[2], layer


def _source_module_parts(path: Path, app_root: Path) -> tuple[str, str | None]:
    parts = _module_name(path, app_root).split(".")
    module = parts[2]
    layer = parts[3] if len(parts) > 3 and parts[3] in LAYERS else None
    return module, layer


def _boundary_violations(app_root: Path) -> list[str]:
    violations: set[str] = set()
    module_dependencies: dict[str, set[str]] = defaultdict(set)
    target_files = sorted((app_root / "platform").rglob("*.py"))
    target_files.extend(sorted((app_root / "modules").rglob("*.py")))

    for path in target_files:
        source = _module_name(path, app_root)
        imports = _import_targets(path, app_root)

        if source == "app.platform":
            for target in imports:
                if not _matches_root(target, "__future__"):
                    violations.add(
                        f"{source}: platform package root cannot import runtime dependency {target}"
                    )
            continue

        if source.startswith("app.platform."):
            for target in imports:
                if target == "app.platform":
                    violations.add(
                        f"{source}: platform code cannot import aggregate root {target}"
                    )
                elif _matches_root(target, "app.modules"):
                    violations.add(f"{source}: platform cannot import product module {target}")
                elif _matches_root(target, "app") and not _matches_root(
                    target, "app.platform"
                ):
                    violations.add(f"{source}: target package cannot import legacy path {target}")
            continue

        if source == "app.modules":
            for target in imports:
                if not _matches_root(target, "__future__"):
                    violations.add(
                        f"{source}: modules package root cannot import runtime dependency {target}"
                    )
            continue

        source_module, source_layer = _source_module_parts(path, app_root)
        if source_layer is None:
            if path.name != "__init__.py":
                violations.add(
                    f"{source}: module code must live in an explicit architecture layer"
                )
            for target in imports:
                if not _matches_root(target, "__future__"):
                    violations.add(
                        f"{source}: module package marker cannot import runtime dependency {target}"
                    )
            continue

        for target in imports:
            if target in {"app.modules", "app.platform"}:
                violations.add(f"{source}: layered code cannot import aggregate root {target}")
            if (
                _matches_root(target, "app")
                and not _matches_root(target, "app.modules")
                and not _matches_root(target, "app.platform")
            ):
                violations.add(f"{source}: target package cannot import legacy path {target}")

            root = target.split(".", maxsplit=1)[0]
            if source_layer == "domain" and root in DOMAIN_FRAMEWORK_ROOTS:
                violations.add(f"{source}: domain cannot import framework {target}")
            if (
                source_layer == "domain"
                and root != "app"
                and root not in stdlib_module_names
            ):
                violations.add(f"{source}: domain cannot import third-party dependency {target}")
            if source_layer == "application" and root in APPLICATION_FRAMEWORK_ROOTS:
                violations.add(f"{source}: application cannot import framework {target}")
            if (
                source_layer == "application"
                and root not in {"app", "pydantic"}
                and root not in stdlib_module_names
            ):
                violations.add(
                    f"{source}: application cannot import external adapter dependency {target}"
                )
            if source_layer == "domain" and _matches_root(target, "app.platform"):
                violations.add(f"{source}: domain cannot import platform concern {target}")
            if source_layer in {"application", "presentation"} and any(
                _matches_root(target, internal) for internal in CONCRETE_PLATFORM_INTERNALS
            ):
                violations.add(
                    f"{source}: {source_layer} cannot import concrete platform internal {target}"
                )
            if (
                source_layer == "presentation"
                and root not in {"app", "fastapi", "pydantic", "starlette"}
                and root not in stdlib_module_names
            ):
                violations.add(
                    f"{source}: presentation cannot import persistence/provider dependency "
                    f"{target}"
                )

            target_parts = _target_module_parts(target)
            if target_parts is None:
                continue
            target_module, target_layer = target_parts
            if target_module != source_module:
                module_dependencies[source_module].add(target_module)
                if source_layer != "application" or target_layer != "application":
                    violations.add(
                        f"{source}: cross-module imports must connect application contracts, "
                        f"not {target}"
                    )
                continue
            if target_layer is None:
                violations.add(
                    f"{source}: layered code cannot import module package root {target}"
                )
                continue
            if (
                source_layer is not None
                and target_layer is not None
                and target_layer not in ALLOWED_LAYER_IMPORTS[source_layer]
            ):
                violations.add(
                    f"{source}: {source_layer} cannot import {target_layer} layer {target}"
                )

    try:
        TopologicalSorter(module_dependencies).prepare()
    except CycleError as exc:
        cycle = " -> ".join(exc.args[1])
        violations.add(f"module dependency cycle: {cycle}")

    return sorted(violations)


def _application_cycle(app_root: Path) -> str | None:
    python_files = sorted(app_root.rglob("*.py"))
    known_modules = {_module_name(path, app_root) for path in python_files}
    graph: dict[str, set[str]] = {module: set() for module in known_modules}

    for path in python_files:
        source = _module_name(path, app_root)
        for target in _import_targets(path, app_root):
            parts = target.split(".")
            dependency = next(
                (
                    ".".join(parts[:length])
                    for length in range(len(parts), 0, -1)
                    if ".".join(parts[:length]) in known_modules
                ),
                None,
            )
            if dependency is not None and dependency != source:
                graph[source].add(dependency)

    try:
        TopologicalSorter(graph).prepare()
    except CycleError as exc:
        return " -> ".join(exc.args[1])
    return None


def _write_module(app_root: Path, relative_path: str, source: str) -> None:
    path = app_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")


def test_target_packages_follow_import_boundaries() -> None:
    assert _boundary_violations(APP_ROOT) == []


def test_target_package_skeleton_exists() -> None:
    expected_packages = {
        *(
            APP_ROOT / "platform" / package / "__init__.py"
            for package in EXPECTED_PLATFORM_PACKAGES
        ),
        *(APP_ROOT / "modules" / package / "__init__.py" for package in EXPECTED_MODULE_PACKAGES),
        APP_ROOT / "platform" / "__init__.py",
        APP_ROOT / "modules" / "__init__.py",
    }

    assert {path for path in expected_packages if not path.is_file()} == set()


def test_application_import_graph_is_acyclic() -> None:
    assert _application_cycle(APP_ROOT) is None


def test_application_services_do_not_complete_transactions() -> None:
    transaction_completion_calls: list[str] = []
    for path in sorted((APP_ROOT / "services").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr in {"commit", "rollback"}:
                transaction_completion_calls.append(
                    f"{path.relative_to(APP_ROOT)}:{node.lineno}:{node.func.attr}"
                )

    assert transaction_completion_calls == []


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_violation"),
    [
        (
            "modules/employees/domain/rules.py",
            "from sqlalchemy import select",
            "domain cannot import framework sqlalchemy",
        ),
        (
            "modules/employees/domain/rules.py",
            "import httpx",
            "domain cannot import third-party dependency httpx",
        ),
        (
            "modules/employees/application/commands.py",
            "from app.modules.employees.presentation.routes import router",
            "application cannot import presentation layer",
        ),
        (
            "modules/employees/presentation/routes.py",
            "from app.modules.employees.infrastructure.repository import EmployeeRepository",
            "presentation cannot import infrastructure layer",
        ),
        (
            "modules/employees/presentation/routes.py",
            "from sqlalchemy import select",
            "presentation cannot import persistence/provider dependency sqlalchemy",
        ),
        (
            "modules/employees/presentation/routes.py",
            "from app.platform.db import session",
            "presentation cannot import concrete platform internal",
        ),
        (
            "modules/employees/application/commands.py",
            "from app.platform.db import session",
            "application cannot import concrete platform internal",
        ),
        (
            "modules/employees/application/commands.py",
            "import httpx",
            "application cannot import external adapter dependency httpx",
        ),
        (
            "modules/employees/infrastructure/repository.py",
            "from app.modules.leave.infrastructure.models import LeaveRequest",
            "cross-module imports must connect application contracts",
        ),
        (
            "modules/employees/domain/rules.py",
            "from app.modules.leave.application.queries import LeaveReader",
            "cross-module imports must connect application contracts",
        ),
        (
            "modules/employees/domain/rules.py",
            "from app.modules.employees import SHARED_POLICY",
            "layered code cannot import module package root",
        ),
        (
            "modules/employees/domain/rules.py",
            "import app.modules",
            "layered code cannot import aggregate root app.modules",
        ),
        (
            "modules/employees/application/commands.py",
            "from app.platform import db",
            "layered code cannot import aggregate root app.platform",
        ),
        (
            "modules/employees/helpers.py",
            "from dataclasses import dataclass",
            "module code must live in an explicit architecture layer",
        ),
        (
            "modules/employees/__init__.py",
            "from sqlalchemy import select",
            "module package marker cannot import runtime dependency",
        ),
        (
            "modules/employees/application/commands.py",
            "from app.models.employee import Employee",
            "target package cannot import legacy path",
        ),
        (
            "modules/employees/application/commands.py",
            "from app.main import app",
            "target package cannot import legacy path app.main",
        ),
        (
            "platform/audit/recorder.py",
            "from app.modules.employees.application.commands import CreateEmployee",
            "platform cannot import product module",
        ),
        (
            "platform/audit/recorder.py",
            "from app.main import app",
            "target package cannot import legacy path app.main",
        ),
        (
            "platform/__init__.py",
            "from app.platform.db import session",
            "platform package root cannot import runtime dependency",
        ),
    ],
)
def test_boundary_checker_rejects_forbidden_dependencies(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected_violation: str,
) -> None:
    app_root = tmp_path / "app"
    _write_module(app_root, relative_path, source)

    assert any(
        expected_violation in violation for violation in _boundary_violations(app_root)
    )


def test_boundary_checker_resolves_forbidden_relative_imports(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_module(
        app_root,
        "modules/employees/domain/rules.py",
        "from ..infrastructure import repository",
    )

    assert any(
        "domain cannot import infrastructure layer" in violation
        for violation in _boundary_violations(app_root)
    )


def test_boundary_checker_allows_documented_dependency_direction(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_module(
        app_root,
        "modules/employees/domain/rules.py",
        "from dataclasses import dataclass",
    )
    _write_module(
        app_root,
        "modules/employees/application/commands.py",
        """
        from pydantic import BaseModel

        from app.modules.employees.domain.rules import EmployeeRule
        from app.platform.workers import JobQueue
        """,
    )
    _write_module(
        app_root,
        "modules/employees/infrastructure/repository.py",
        """
        from sqlalchemy import select

        from app.modules.employees.application.commands import CreateEmployee
        from app.platform.db import session
        """,
    )
    _write_module(
        app_root,
        "modules/employees/presentation/routes.py",
        """
        from fastapi import APIRouter

        from app.modules.employees.application.commands import CreateEmployee
        from app.platform.errors import ApiError
        """,
    )
    _write_module(
        app_root,
        "modules/reporting/application/queries.py",
        "from app.modules.employees.application.commands import EmployeeReader",
    )

    assert _boundary_violations(app_root) == []


def test_boundary_checker_rejects_module_dependency_cycles(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_module(
        app_root,
        "modules/employees/application/commands.py",
        "from app.modules.leave.application.commands import LeaveReader",
    )
    _write_module(
        app_root,
        "modules/leave/application/commands.py",
        "from app.modules.employees.application.commands import EmployeeReader",
    )

    assert any(
        violation.startswith("module dependency cycle:")
        for violation in _boundary_violations(app_root)
    )


def test_cycle_checker_rejects_python_module_cycle(tmp_path: Path) -> None:
    app_root = tmp_path / "app"
    _write_module(app_root, "platform/errors/contract.py", "from . import mapper")
    _write_module(app_root, "platform/errors/mapper.py", "from . import contract")

    assert _application_cycle(app_root) is not None
