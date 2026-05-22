from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_QRE,
    ImportEdge,
    evaluate_edges,
)
from reporting.control_plane_qre_adapter_contract import (
    CONTRACT_NAME,
    CONTRACT_VERSION,
    FORBIDDEN_CAPABILITIES,
    READ_ONLY_METHODS,
    AdapterContractDescription,
    ControlPlaneQREReadAdapter,
    ReadModelContract,
    describe_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "reporting" / "control_plane_qre_adapter_contract.py"

FORBIDDEN_IMPORT_PREFIXES = (
    "agent.execution",
    "agent.risk",
    "automation.live_gate",
    "broker",
    "dashboard",
    "execution",
    "flask",
    "live",
    "paper",
    "research",
    "risk",
    "shadow",
)
MUTATION_VERBS = (
    "append",
    "approve",
    "create",
    "delete",
    "dispatch",
    "enqueue",
    "execute",
    "mutate",
    "order",
    "post",
    "put",
    "save",
    "spawn",
    "trade",
    "update",
    "write",
)


class _StubReadAdapter:
    def list_read_models(self) -> tuple[ReadModelContract, ...]:
        return (
            ReadModelContract(
                name="campaign_registry",
                schema_version="1.0",
                description="Existing campaign registry read model.",
            ),
        )

    def read_json(self, read_model: str) -> dict[str, object]:
        return {"schema_version": "1.0", "read_model": read_model}

    def describe_contract(self) -> AdapterContractDescription:
        return describe_contract()


def test_adapter_contract_is_runtime_checkable_and_read_only() -> None:
    adapter = _StubReadAdapter()

    assert isinstance(adapter, ControlPlaneQREReadAdapter)
    assert adapter.list_read_models()[0].name == "campaign_registry"
    assert adapter.read_json("campaign_registry") == {
        "schema_version": "1.0",
        "read_model": "campaign_registry",
    }
    assert adapter.describe_contract() == describe_contract()


def test_adapter_contract_metadata_is_stable_and_frozen() -> None:
    description = describe_contract()
    read_model = ReadModelContract(
        name="run_state",
        schema_version="1.0",
        description="Existing QRE run-state read model.",
    )

    assert description == AdapterContractDescription(
        name=CONTRACT_NAME,
        version=CONTRACT_VERSION,
        read_only_methods=READ_ONLY_METHODS,
        forbidden_capabilities=FORBIDDEN_CAPABILITIES,
    )
    assert description.read_only_methods == (
        "list_read_models",
        "read_json",
        "describe_contract",
    )
    assert "write" in description.forbidden_capabilities
    assert read_model.schema_version == "1.0"
    with pytest.raises(FrozenInstanceError):
        read_model.name = "mutated"  # type: ignore[misc]


def test_adapter_contract_is_stdlib_only_and_has_no_domain_imports() -> None:
    tree = ast.parse(CONTRACT_PATH.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    violations = [
        module
        for module in imported_modules
        if any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    ]

    assert violations == []
    assert sorted(imported_modules) == [
        "__future__",
        "dataclasses",
        "typing",
    ]


def test_adapter_contract_exposes_no_mutation_or_route_surface() -> None:
    tree = ast.parse(CONTRACT_PATH.read_text(encoding="utf-8"))
    public_functions = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    route_decorators = [
        decorator
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "route"
    ]

    assert sorted(public_functions) == [
        "describe_contract",
        "describe_contract",
        "list_read_models",
        "read_json",
    ]
    assert route_decorators == []
    assert not any(
        verb in function_name.lower()
        for verb in MUTATION_VERBS
        for function_name in public_functions
    )


def test_adapter_path_import_is_allowed_for_future_control_plane_code() -> None:
    edge = ImportEdge(
        source_module="dashboard.api_future_read_model",
        target_module="reporting.control_plane_qre_adapter_contract",
        source_path="dashboard/api_future_read_model.py",
        source_domain=DOMAIN_CONTROL_PLANE,
        target_domain=DOMAIN_ADE,
        target_root="reporting",
        line=4,
        import_kind="from",
    )

    report = evaluate_edges((edge,))

    assert report.forbidden_edges == ()
    assert [(finding.rule, finding.source_module) for finding in report.legacy_edges] == [
        ("mixed-domain", "dashboard.api_future_read_model")
    ]


def test_direct_control_plane_qre_import_remains_forbidden() -> None:
    edge = ImportEdge(
        source_module="dashboard.api_future_read_model",
        target_module="research.future_read_model",
        source_path="dashboard/api_future_read_model.py",
        source_domain=DOMAIN_CONTROL_PLANE,
        target_domain=DOMAIN_QRE,
        target_root="research",
        line=4,
        import_kind="from",
    )

    report = evaluate_edges((edge,))

    assert [
        (finding.rule, finding.source_module, finding.target_module)
        for finding in report.forbidden_edges
    ] == [
        (
            "control-plane-to-qre",
            "dashboard.api_future_read_model",
            "research.future_read_model",
        )
    ]
    assert report.legacy_edges == ()
