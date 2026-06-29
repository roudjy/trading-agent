from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pandas as pd

from agent.backtesting.features import FEATURE_REGISTRY
from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin
from packages.qre_research.generated_strategy_paths import (
    GENERATED_CLOSEOUT_PATH,
    GENERATED_LINEAGE_PATH,
    GENERATED_MANIFESTS_DIR,
    GENERATED_NULL_CONTROLS_PATH,
    GENERATED_PRESETS_PATH,
    GENERATED_REGISTRY_PATH,
    GENERATED_SPECS_DIR,
    GENERATED_STRATEGY_PACKAGE_DIR,
    GENERATED_STRATEGY_TEST_DIR,
    REPO_ROOT,
    repo_relative,
    validate_write_target,
)
from research.registry import STRATEGIES as MANUAL_STRATEGIES


SCHEMA_VERSION: Final[str] = "1.0"
GENERATOR_VERSION: Final[str] = "ade-qre-019.1"
TEMPLATE_VERSION: Final[str] = "thin-strategy-template.1"
REPORT_KIND: Final[str] = "qre_automated_strategy_generation"

SPEC_OUTCOMES: Final[tuple[str, ...]] = (
    "SPECIFICATION_READY",
    "BLOCKED_INCOMPLETE_THESIS",
    "BLOCKED_IDENTITY",
    "BLOCKED_UNSUPPORTED_PRIMITIVE",
    "BLOCKED_DUPLICATE",
    "BLOCKED_REJECTED_LINEAGE",
    "BLOCKED_DATA_REQUIREMENT",
    "BLOCKED_POLICY",
)
GENERATION_OUTCOMES: Final[tuple[str, ...]] = (
    "RESEARCH_REGISTERED_AUTOMATED",
    "BLOCKED_INCOMPLETE_THESIS",
    "BLOCKED_IDENTITY",
    "BLOCKED_UNSUPPORTED_PRIMITIVE",
    "BLOCKED_DATA",
    "QUARANTINED_VALIDATION",
    "QUARANTINED_ARCHITECTURE",
    "REJECTED_DUPLICATE",
    "REJECTED_POLICY",
)
REGISTRY_STATE: Final[str] = "RESEARCH_REGISTERED_AUTOMATED"
REGISTRY_AUTHORITY: Final[str] = "RESEARCH_ONLY_AUTOMATED"
RESOLVED_ORIGIN_MANUAL: Final[str] = "MANUAL"
RESOLVED_ORIGIN_GENERATED: Final[str] = "GENERATED_AUTOMATED"
READY_FOR_PREREGISTRATION: Final[str] = "READY_FOR_PREREGISTRATION"

ALLOWED_GENERATED_IMPORTS: Final[tuple[str, ...]] = (
    "__future__",
    "pandas",
    "agent.backtesting.thin_strategy",
)
ALLOWED_GENERATED_TEST_IMPORTS: Final[tuple[str, ...]] = (
    "__future__",
    "importlib",
    "pandas",
    "agent.backtesting.thin_strategy",
    "tests._harness_helpers",
)
FORBIDDEN_IMPORT_PREFIXES: Final[tuple[str, ...]] = (
    "socket",
    "urllib",
    "requests",
    "http",
    "subprocess",
    "broker",
    "automation",
    "agent.risk",
    "agent.execution",
    "live",
    "paper",
    "shadow",
)
FORBIDDEN_CALL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "eval",
        "exec",
        "open",
        "compile",
        "__import__",
    }
)
FORBIDDEN_ATTRIBUTE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "system",
        "popen",
        "run",
        "Popen",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "replace",
        "rename",
    }
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_019.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


@dataclass(frozen=True)
class StrategySpecification:
    strategy_spec_id: str
    schema_version: str
    generator_version: str
    template_version: str
    thesis_id: str
    source_hypothesis_id: str
    behavior_family: str
    mechanism: str
    expected_behavior: str
    entry_conditions: tuple[str, ...]
    exit_conditions: tuple[str, ...]
    filters: tuple[str, ...]
    allowed_direction: str
    timeframe: tuple[str, ...]
    universe_constraints: tuple[str, ...]
    required_feature_primitives: tuple[str, ...]
    parameters: dict[str, Any]
    parameter_domains: dict[str, list[Any]]
    warmup_requirements: dict[str, int]
    cost_assumptions: dict[str, Any]
    slippage_assumptions: dict[str, Any]
    research_sizing_assumptions: dict[str, Any]
    expected_signal_density_range: str
    null_control_requirements: tuple[str, ...]
    expected_failure_modes: tuple[str, ...]
    forbidden_behavior: tuple[str, ...]
    provenance: tuple[str, ...]
    deterministic_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy_spec_id": self.strategy_spec_id,
            "schema_version": self.schema_version,
            "generator_version": self.generator_version,
            "template_version": self.template_version,
            "thesis_id": self.thesis_id,
            "source_hypothesis_id": self.source_hypothesis_id,
            "behavior_family": self.behavior_family,
            "mechanism": self.mechanism,
            "expected_behavior": self.expected_behavior,
            "entry_conditions": list(self.entry_conditions),
            "exit_conditions": list(self.exit_conditions),
            "filters": list(self.filters),
            "allowed_direction": self.allowed_direction,
            "timeframe": list(self.timeframe),
            "universe_constraints": list(self.universe_constraints),
            "required_feature_primitives": list(self.required_feature_primitives),
            "parameters": dict(self.parameters),
            "parameter_domains": {key: list(value) for key, value in self.parameter_domains.items()},
            "warmup_requirements": dict(self.warmup_requirements),
            "cost_assumptions": dict(self.cost_assumptions),
            "slippage_assumptions": dict(self.slippage_assumptions),
            "research_sizing_assumptions": dict(self.research_sizing_assumptions),
            "expected_signal_density_range": self.expected_signal_density_range,
            "null_control_requirements": list(self.null_control_requirements),
            "expected_failure_modes": list(self.expected_failure_modes),
            "forbidden_behavior": list(self.forbidden_behavior),
            "provenance": list(self.provenance),
            "deterministic_hash": self.deterministic_hash,
        }


def _manual_registry_index() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in MANUAL_STRATEGIES:
        name = str(row.get("name") or "").strip()
        if name:
            rows[name] = dict(row)
    return rows


def _generated_strategy_id(source_hypothesis_id: str) -> str:
    return f"qgs_{stable_digest({'source_hypothesis_id': source_hypothesis_id, 'generator_version': GENERATOR_VERSION})[:16]}"


def _spec_id(source_hypothesis_id: str) -> str:
    return f"qsp_{stable_digest({'source_hypothesis_id': source_hypothesis_id, 'schema_version': SCHEMA_VERSION, 'generator_version': GENERATOR_VERSION})[:16]}"


def _test_manifest_id(strategy_id: str, code_hash: str) -> str:
    return f"qgt_{stable_digest({'strategy_id': strategy_id, 'code_hash': code_hash})[:16]}"


def _sandbox_id(strategy_id: str, code_hash: str) -> str:
    return f"qsv_{stable_digest({'strategy_id': strategy_id, 'code_hash': code_hash, 'kind': 'sandbox'})[:16]}"


def _registration_id(strategy_id: str, code_hash: str) -> str:
    return f"qgr_{stable_digest({'strategy_id': strategy_id, 'code_hash': code_hash, 'kind': 'registry'})[:16]}"


def _null_control_id(strategy_id: str) -> str:
    return f"qnc_{stable_digest({'strategy_id': strategy_id, 'kind': 'null-control'})[:16]}"


def _lineage_id(source_hypothesis_id: str) -> str:
    return f"qgl_{stable_digest({'source_hypothesis_id': source_hypothesis_id, 'kind': 'lineage'})[:16]}"


def _portfolio_cell_id(source_hypothesis_id: str) -> str:
    return f"qpc_{stable_digest({'source_hypothesis_id': source_hypothesis_id, 'kind': 'portfolio-cell'})[:16]}"


def _load_generation_inputs(repo_root: Path) -> dict[str, Any]:
    thesis_rows = _read_rows(repo_root / "logs/qre_behavior_thesis_registry/latest.json")
    if not thesis_rows:
        thesis_rows = [
            {
                "thesis_id": row.get("thesis_id", ""),
                "behavior_family": row.get("behavior_family", ""),
                "source_hypothesis_id": row.get("source_hypothesis_id", ""),
                "status": row.get("status", ""),
                "signal_density_expectation": row.get("signal_density_expectation", ""),
                "mechanism": row.get("source_hypothesis_id", ""),
                "expected_behavior": row.get("behavior_family", ""),
                "timeframe": "1h",
            }
            for row in common.read_markdown_table_rows(
                repo_root / "docs/governance/qre_behavior_thesis_registry.md"
            )
        ]
    identity_rows = _read_rows(repo_root / "logs/qre_identity_ambiguity_resolution/latest.json")
    if not identity_rows:
        identity_rows = [
            {
                "source_hypothesis_id": row.get("source_hypothesis_id", ""),
                "resolution_state": row.get("status", ""),
                "next_action": row.get("next_action", ""),
            }
            for row in common.read_markdown_backtick_status_rows(
                repo_root / "docs/governance/qre_identity_ambiguity_resolution.md"
            )
        ]
    census_rows = _read_rows(repo_root / "logs/qre_blocked_thesis_lineage_census/latest.json")
    portfolio_rows = _read_rows(repo_root / "logs/qre_campaign_portfolio_reconstruction/latest.json")
    return {
        "thesis_by_hypothesis": {str(row.get("source_hypothesis_id") or ""): row for row in thesis_rows},
        "identity_by_hypothesis": {str(row.get("source_hypothesis_id") or ""): row for row in identity_rows},
        "census_by_hypothesis": {str(row.get("source_hypothesis_id") or ""): row for row in census_rows},
        "portfolio_by_hypothesis": {str(row.get("source_hypothesis_id") or ""): row for row in portfolio_rows},
    }


def _current_generated_registry(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / GENERATED_REGISTRY_PATH) or {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "generated_strategy_registry",
        "rows": [],
    }


def _supported_strategy_blueprint(source_hypothesis_id: str, thesis_row: dict[str, Any]) -> dict[str, Any] | None:
    if source_hypothesis_id != "atr_adaptive_trend_v0":
        return None
    return {
        "behavior_family": "trend_continuation",
        "entry_conditions": (
            "trend_anchor_delta_positive",
            "normalized_trend_move_above_entry_threshold",
        ),
        "exit_conditions": (
            "trend_anchor_delta_negative",
            "normalized_trend_move_below_exit_threshold",
        ),
        "filters": ("atr_positive",),
        "allowed_direction": "long_only",
        "timeframe": tuple(part for part in str(thesis_row.get("timeframe") or "1h").split("|") if part),
        "universe_constraints": ("single_resolved_instrument_only",),
        "required_feature_primitives": (
            "trend_anchor",
            "trend_anchor_delta",
            "atr",
            "normalized_trend_move",
        ),
        "parameters": {
            "trend_anchor_window": 50,
            "atr_window": 14,
            "entry_atr_multiple": 0.75,
            "exit_atr_multiple": 0.10,
        },
        "parameter_domains": {
            "trend_anchor_window": [50],
            "atr_window": [14],
            "entry_atr_multiple": [0.75],
            "exit_atr_multiple": [0.10],
        },
        "warmup_requirements": {
            "trend_anchor": 50,
            "trend_anchor_delta": 51,
            "atr": 14,
            "normalized_trend_move": 50,
        },
        "cost_assumptions": {"mode": "cost_class_visible_only"},
        "slippage_assumptions": {"status": "not_materialized"},
        "research_sizing_assumptions": {"mode": "unit_notional_research_only"},
        "expected_signal_density_range": str(thesis_row.get("signal_density_expectation") or "moderate"),
        "null_control_requirements": (
            "matched_frequency_null",
            "sign_flipped_signal",
            "cost_only_baseline",
        ),
        "expected_failure_modes": (
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "no_baseline_edge",
        ),
    }


def compile_strategy_spec(
    *,
    repo_root: Path,
    source_hypothesis_id: str,
) -> dict[str, Any]:
    inputs = _load_generation_inputs(repo_root)
    thesis_row = inputs["thesis_by_hypothesis"].get(source_hypothesis_id, {})
    identity_row = inputs["identity_by_hypothesis"].get(source_hypothesis_id, {})
    census_row = inputs["census_by_hypothesis"].get(source_hypothesis_id, {})

    if not thesis_row:
        return {"outcome": "BLOCKED_INCOMPLETE_THESIS", "reason": "thesis_missing"}
    if source_hypothesis_id == "trend_pullback_v1":
        return {"outcome": "BLOCKED_REJECTED_LINEAGE", "reason": "rejected_lineage_protected"}
    if str(census_row.get("lineage_status") or "") == "IDENTITY_BLOCKED":
        return {"outcome": "BLOCKED_IDENTITY", "reason": "identity_blocked_in_census"}
    resolution_state = str(identity_row.get("resolution_state") or "")
    if resolution_state in {"BLOCKED", "AMBIGUOUS", "CONFLICTING"}:
        return {"outcome": "BLOCKED_IDENTITY", "reason": "identity_resolution_blocked"}
    if resolution_state == "MISSING" and source_hypothesis_id != "atr_adaptive_trend_v0":
        return {"outcome": "BLOCKED_IDENTITY", "reason": "identity_resolution_missing"}

    if source_hypothesis_id == "regime_diagnostics_v1":
        return {"outcome": "BLOCKED_POLICY", "reason": "diagnostic_behavior_not_executable"}
    if source_hypothesis_id == "dynamic_pairs_v0":
        return {"outcome": "BLOCKED_POLICY", "reason": "disabled_branchpoint_not_executable"}
    if source_hypothesis_id == "multi_asset_trend_sleeve_v0":
        return {"outcome": "BLOCKED_POLICY", "reason": "portfolio_sleeve_execution_out_of_scope"}
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        return {"outcome": "BLOCKED_UNSUPPORTED_PRIMITIVE", "reason": "cross_sectional_primitives_not_registered"}
    if source_hypothesis_id == "volatility_compression_breakout_v0":
        return {"outcome": "BLOCKED_IDENTITY", "reason": "identity_inventory_missing"}

    blueprint = _supported_strategy_blueprint(source_hypothesis_id, thesis_row)
    if blueprint is None:
        return {"outcome": "BLOCKED_POLICY", "reason": "no_supported_blueprint"}
    for primitive in blueprint["required_feature_primitives"]:
        if primitive not in FEATURE_REGISTRY:
            return {
                "outcome": "BLOCKED_UNSUPPORTED_PRIMITIVE",
                "reason": f"primitive_not_registered:{primitive}",
            }

    spec_id = _spec_id(source_hypothesis_id)
    payload_core = {
        "strategy_spec_id": spec_id,
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "thesis_id": str(thesis_row.get("thesis_id") or ""),
        "source_hypothesis_id": source_hypothesis_id,
        "behavior_family": str(thesis_row.get("behavior_family") or blueprint["behavior_family"]),
        "mechanism": str(thesis_row.get("mechanism") or source_hypothesis_id),
        "expected_behavior": str(thesis_row.get("expected_behavior") or blueprint["behavior_family"]),
        "entry_conditions": list(blueprint["entry_conditions"]),
        "exit_conditions": list(blueprint["exit_conditions"]),
        "filters": list(blueprint["filters"]),
        "allowed_direction": blueprint["allowed_direction"],
        "timeframe": list(blueprint["timeframe"]),
        "universe_constraints": list(blueprint["universe_constraints"]),
        "required_feature_primitives": list(blueprint["required_feature_primitives"]),
        "parameters": dict(blueprint["parameters"]),
        "parameter_domains": {key: list(value) for key, value in blueprint["parameter_domains"].items()},
        "warmup_requirements": dict(blueprint["warmup_requirements"]),
        "cost_assumptions": dict(blueprint["cost_assumptions"]),
        "slippage_assumptions": dict(blueprint["slippage_assumptions"]),
        "research_sizing_assumptions": dict(blueprint["research_sizing_assumptions"]),
        "expected_signal_density_range": blueprint["expected_signal_density_range"],
        "null_control_requirements": list(blueprint["null_control_requirements"]),
        "expected_failure_modes": list(blueprint["expected_failure_modes"]),
        "forbidden_behavior": [
            "arbitrary_python",
            "arbitrary_imports",
            "shell_commands",
            "network_access",
            "file_system_writes",
            "eval",
            "exec",
            "broker_access",
            "live_execution",
            "real_capital_sizing",
            "nondeterministic_strategy_construction",
        ],
        "provenance": [
            "logs/qre_behavior_thesis_registry/latest.json",
            "logs/qre_identity_ambiguity_resolution/latest.json",
            "logs/qre_blocked_thesis_lineage_census/latest.json",
        ],
    }
    deterministic_hash = stable_digest(payload_core)
    spec = StrategySpecification(
        strategy_spec_id=spec_id,
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        template_version=TEMPLATE_VERSION,
        thesis_id=payload_core["thesis_id"],
        source_hypothesis_id=source_hypothesis_id,
        behavior_family=payload_core["behavior_family"],
        mechanism=payload_core["mechanism"],
        expected_behavior=payload_core["expected_behavior"],
        entry_conditions=tuple(payload_core["entry_conditions"]),
        exit_conditions=tuple(payload_core["exit_conditions"]),
        filters=tuple(payload_core["filters"]),
        allowed_direction=payload_core["allowed_direction"],
        timeframe=tuple(payload_core["timeframe"]),
        universe_constraints=tuple(payload_core["universe_constraints"]),
        required_feature_primitives=tuple(payload_core["required_feature_primitives"]),
        parameters=payload_core["parameters"],
        parameter_domains=payload_core["parameter_domains"],
        warmup_requirements=payload_core["warmup_requirements"],
        cost_assumptions=payload_core["cost_assumptions"],
        slippage_assumptions=payload_core["slippage_assumptions"],
        research_sizing_assumptions=payload_core["research_sizing_assumptions"],
        expected_signal_density_range=payload_core["expected_signal_density_range"],
        null_control_requirements=tuple(payload_core["null_control_requirements"]),
        expected_failure_modes=tuple(payload_core["expected_failure_modes"]),
        forbidden_behavior=tuple(payload_core["forbidden_behavior"]),
        provenance=tuple(payload_core["provenance"]),
        deterministic_hash=deterministic_hash,
    )
    return {"outcome": "SPECIFICATION_READY", "specification": spec}


def _render_strategy_source(spec: StrategySpecification) -> str:
    strategy_id = _generated_strategy_id(spec.source_hypothesis_id)
    module_name = f"generated_{strategy_id}"
    return "\n".join(
        [
            'from __future__ import annotations',
            "",
            "import pandas as pd",
            "",
            "from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin",
            "",
            f'STRATEGY_ID = "{strategy_id}"',
            f'STRATEGY_SPEC_ID = "{spec.strategy_spec_id}"',
            f'GENERATOR_VERSION = "{GENERATOR_VERSION}"',
            f'TEMPLATE_VERSION = "{TEMPLATE_VERSION}"',
            "",
            "FEATURE_REQUIREMENTS = [",
            '    FeatureRequirement(name="trend_anchor", params={"window": 50}, alias="trend_anchor"),',
            '    FeatureRequirement(name="trend_anchor_delta", params={"window": 50}, alias="trend_anchor_delta"),',
            '    FeatureRequirement(name="normalized_trend_move", params={"trend_anchor_window": 50, "atr_window": 14}, alias="normalized_trend_move"),',
            "]",
            "",
            "def _raw(df: pd.DataFrame, features: dict[str, pd.Series]) -> pd.Series:",
            '    anchor_delta = features["trend_anchor_delta"]',
            '    normalized_move = features["normalized_trend_move"]',
            "    signal = pd.Series(0, index=df.index, dtype=int)",
            "    active = False",
            "    for idx in range(len(signal)):",
            "        if bool(anchor_delta.iloc[idx] > 0) and bool(normalized_move.iloc[idx] >= 0.75):",
            "            active = True",
            "        elif bool(anchor_delta.iloc[idx] < 0) or bool(normalized_move.iloc[idx] <= 0.10):",
            "            active = False",
            "        signal.iloc[idx] = 1 if active else 0",
            "    return signal",
            "",
            "generated_strategy = declare_thin(",
            "    _raw,",
            "    feature_requirements=FEATURE_REQUIREMENTS,",
            '    sizing_spec={"mode": "unit_notional_research_only"},',
            ")",
            "",
        ]
    ) + "\n"


def _render_test_source(spec: StrategySpecification, strategy_module_relpath: str) -> str:
    strategy_id = _generated_strategy_id(spec.source_hypothesis_id)
    module_path = strategy_module_relpath.removesuffix(".py").replace("/", ".")
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import importlib",
            "import pandas as pd",
            "",
            "from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy",
            "from tests._harness_helpers import build_ohlcv_frame",
            "",
            f"MODULE_NAME = \"{module_path}\"",
            f"EXPECTED_STRATEGY_ID = \"{strategy_id}\"",
            f"EXPECTED_SPEC_ID = \"{spec.strategy_spec_id}\"",
            "",
            "def _load_module():",
            "    return importlib.import_module(MODULE_NAME)",
            "",
            "def test_generated_strategy_imports_and_declares_thin_contract() -> None:",
            "    module = _load_module()",
            "    assert module.STRATEGY_ID == EXPECTED_STRATEGY_ID",
            "    assert module.STRATEGY_SPEC_ID == EXPECTED_SPEC_ID",
            "    assert is_thin_strategy(module.generated_strategy)",
            "",
            "def test_generated_strategy_is_deterministic() -> None:",
            "    module = _load_module()",
            "    frame = build_ohlcv_frame(length=96, seed=19)",
            "    features = build_features_for(module.generated_strategy._feature_requirements, frame)",
            "    first = module.generated_strategy(frame, features)",
            "    second = module.generated_strategy(frame, features)",
            "    pd.testing.assert_series_equal(first, second)",
            "    assert set(first.dropna().unique()) <= {0, 1}",
            "",
            "def test_generated_strategy_handles_empty_signal_path() -> None:",
            "    module = _load_module()",
            "    frame = build_ohlcv_frame(length=24, seed=7)",
            '    frame["close"] = frame["close"].iloc[0]',
            "    features = build_features_for(module.generated_strategy._feature_requirements, frame)",
            "    result = module.generated_strategy(frame, features)",
            "    assert result.index.equals(frame.index)",
            "    assert set(result.dropna().unique()) <= {0, 1}",
            "",
        ]
    ) + "\n"


def _generated_paths_for_spec(spec: StrategySpecification) -> dict[str, Path]:
    strategy_id = _generated_strategy_id(spec.source_hypothesis_id)
    return {
        "spec": REPO_ROOT / GENERATED_SPECS_DIR / f"{spec.strategy_spec_id}.json",
        "manifest": REPO_ROOT / GENERATED_MANIFESTS_DIR / f"{strategy_id}.json",
        "validation": REPO_ROOT / GENERATED_MANIFESTS_DIR.parent / "validation" / f"{strategy_id}.json",
        "strategy_module": REPO_ROOT / GENERATED_STRATEGY_PACKAGE_DIR / f"generated_{strategy_id}.py",
        "strategy_test": REPO_ROOT / GENERATED_STRATEGY_TEST_DIR / f"test_generated_{strategy_id}.py",
    }


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self, *, allowed_imports: tuple[str, ...]) -> None:
        self.allowed_imports = allowed_imports
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name not in self.allowed_imports:
                self.errors.append(f"import_not_allowlisted:{alias.name}")
            if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                self.errors.append(f"import_forbidden:{alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module not in self.allowed_imports:
            self.errors.append(f"import_from_not_allowlisted:{module}")
        if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
            self.errors.append(f"import_from_forbidden:{module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALL_NAMES:
            self.errors.append(f"forbidden_call:{node.func.id}")
        if isinstance(node.func, ast.Attribute) and node.func.attr in FORBIDDEN_ATTRIBUTE_NAMES:
            self.errors.append(f"forbidden_attribute_call:{node.func.attr}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in {"socket", "request", "Session"}:
            self.errors.append(f"forbidden_attribute:{node.attr}")
        self.generic_visit(node)


def static_validate_generated_source(
    *,
    strategy_source: str,
    strategy_test_source: str,
) -> dict[str, Any]:
    errors: list[str] = []
    for label, source, allowed_imports in (
        ("strategy", strategy_source, ALLOWED_GENERATED_IMPORTS),
        ("test", strategy_test_source, ALLOWED_GENERATED_TEST_IMPORTS),
    ):
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return {"status": "QUARANTINED_ARCHITECTURE", "errors": [f"{label}_syntax_error:{exc.lineno}"]}
        visitor = _SafetyVisitor(allowed_imports=allowed_imports)
        visitor.visit(tree)
        errors.extend(f"{label}:{item}" for item in visitor.errors)
    if errors:
        return {"status": "QUARANTINED_ARCHITECTURE", "errors": sorted(errors)}
    return {"status": "PASSED", "errors": []}


def _ensure_package_init() -> None:
    init_path = REPO_ROOT / GENERATED_STRATEGY_PACKAGE_DIR / "__init__.py"
    if not init_path.is_file():
        _atomic_write(init_path, '"""Generated ADE-QRE-019 research-only strategies."""\n')


def materialize_generated_strategy(spec: StrategySpecification) -> dict[str, Any]:
    _ensure_package_init()
    paths = _generated_paths_for_spec(spec)
    strategy_source = _render_strategy_source(spec)
    strategy_relpath = repo_relative(paths["strategy_module"])
    strategy_test_source = _render_test_source(spec, strategy_relpath)
    safety = static_validate_generated_source(
        strategy_source=strategy_source,
        strategy_test_source=strategy_test_source,
    )
    if safety["status"] != "PASSED":
        return {"outcome": "QUARANTINED_ARCHITECTURE", "errors": safety["errors"]}

    code_hash = stable_digest(strategy_source)
    test_hash = stable_digest(strategy_test_source)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "strategy_spec_id": spec.strategy_spec_id,
        "generated_strategy_id": _generated_strategy_id(spec.source_hypothesis_id),
        "module_path": strategy_relpath,
        "factory_symbol": "generated_strategy",
        "test_module_path": repo_relative(paths["strategy_test"]),
        "code_hash": code_hash,
        "test_manifest_id": _test_manifest_id(_generated_strategy_id(spec.source_hypothesis_id), code_hash),
        "test_hash": test_hash,
        "provenance": list(spec.provenance),
    }
    _atomic_write(paths["spec"], json.dumps(spec.to_payload(), indent=2, sort_keys=True) + "\n")
    _atomic_write(paths["strategy_module"], strategy_source)
    _atomic_write(paths["strategy_test"], strategy_test_source)
    _atomic_write(paths["manifest"], json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "outcome": "CODE_GENERATED",
        "code_hash": code_hash,
        "test_hash": test_hash,
        "manifest": manifest,
        "paths": {key: repo_relative(path) for key, path in paths.items()},
    }


def sandbox_validate_generated_strategy(
    *,
    spec: StrategySpecification,
    materialization: dict[str, Any],
) -> dict[str, Any]:
    manifest = dict(materialization["manifest"])
    module_name = manifest["module_path"].removesuffix(".py").replace("/", ".")
    test_path = REPO_ROOT / manifest["test_module_path"]
    strategy_id = manifest["generated_strategy_id"]

    importlib.invalidate_caches()
    if module_name in importlib.sys.modules:
        del importlib.sys.modules[module_name]
    module = importlib.import_module(module_name)
    strategy = getattr(module, "generated_strategy")
    frame = pd.DataFrame(
        {
            "open": [100 + idx for idx in range(96)],
            "high": [101 + idx for idx in range(96)],
            "low": [99 + idx for idx in range(96)],
            "close": [100 + idx + (0.5 if idx % 3 else 0.0) for idx in range(96)],
            "volume": [1000 + idx for idx in range(96)],
        },
        index=pd.date_range("2024-01-01", periods=96, freq="h"),
    )
    from agent.backtesting.thin_strategy import build_features_for, validate_thin_strategy_output

    features = build_features_for(strategy._feature_requirements, frame)
    first = strategy(frame, features)
    second = strategy(frame, features)
    validate_thin_strategy_output(first, frame.index)
    if stable_digest(first.astype(int).tolist()) != stable_digest(second.astype(int).tolist()):
        return {"status": "NONDETERMINISTIC", "errors": ["strategy_output_changed_between_runs"]}

    runner_payload = {
        "sandbox_validation_id": _sandbox_id(strategy_id, manifest["code_hash"]),
        "status": "VALIDATED",
        "generated_strategy_id": strategy_id,
        "strategy_spec_id": spec.strategy_spec_id,
        "module_path": manifest["module_path"],
        "test_module_path": manifest["test_module_path"],
        "code_hash": manifest["code_hash"],
        "test_manifest_id": manifest["test_manifest_id"],
        "fixture_row_count": len(frame),
        "side_effects_detected": False,
        "deterministic_replay_match": True,
        "technical_validation_only": True,
        "fixture_evidence_not_market_evidence": True,
    }
    validation_path = REPO_ROOT / GENERATED_MANIFESTS_DIR.parent / "validation" / f"{strategy_id}.json"
    _atomic_write(validation_path, json.dumps(runner_payload, indent=2, sort_keys=True) + "\n")
    return {
        "status": "VALIDATED",
        "validation": runner_payload,
        "validation_path": repo_relative(validation_path),
        "test_path": repo_relative(test_path),
    }


def admit_generated_registry_entry(
    *,
    repo_root: Path,
    spec: StrategySpecification,
    materialization: dict[str, Any],
    sandbox: dict[str, Any],
) -> dict[str, Any]:
    if sandbox["status"] != "VALIDATED":
        return {"outcome": "QUARANTINED_VALIDATION", "reason": sandbox["status"]}
    registry = _current_generated_registry(repo_root)
    rows = [dict(row) for row in registry.get("rows", []) if isinstance(row, dict)]
    generated_strategy_id = materialization["manifest"]["generated_strategy_id"]
    if any(str(row.get("generated_strategy_id") or "") == generated_strategy_id for row in rows):
        return {"outcome": "REJECTED_DUPLICATE", "reason": "generated_strategy_id_collision"}
    if generated_strategy_id in _manual_registry_index():
        return {"outcome": "REJECTED_DUPLICATE", "reason": "manual_registry_name_collision"}

    entry = {
        "generated_registration_id": _registration_id(generated_strategy_id, materialization["manifest"]["code_hash"]),
        "thesis_id": spec.thesis_id,
        "source_hypothesis_id": spec.source_hypothesis_id,
        "strategy_spec_id": spec.strategy_spec_id,
        "generated_strategy_id": generated_strategy_id,
        "strategy_name": generated_strategy_id,
        "code_hash": materialization["manifest"]["code_hash"],
        "test_manifest_id": materialization["manifest"]["test_manifest_id"],
        "sandbox_artifact_id": sandbox["validation"]["sandbox_validation_id"],
        "sandbox_validation_path": sandbox["validation_path"],
        "generator_version": GENERATOR_VERSION,
        "template_version": TEMPLATE_VERSION,
        "module_path": materialization["manifest"]["module_path"],
        "factory_symbol": materialization["manifest"]["factory_symbol"],
        "provenance": list(spec.provenance),
        "authority": REGISTRY_AUTHORITY,
        "state": REGISTRY_STATE,
        "rejected_clone_lineage": False,
    }
    rows.append(entry)
    rows.sort(key=lambda row: str(row.get("generated_strategy_id") or ""))
    registry_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "generated_strategy_registry",
        "generated_registry_identity": f"qrg_{stable_digest(rows)[:16]}",
        "rows": rows,
    }
    _atomic_write(repo_root / GENERATED_REGISTRY_PATH, json.dumps(registry_payload, indent=2, sort_keys=True) + "\n")
    return {"outcome": REGISTRY_STATE, "entry": entry, "registry_identity": registry_payload["generated_registry_identity"]}


def build_resolved_strategy_catalog(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    generated_registry = _current_generated_registry(root)
    generated_rows = [dict(row) for row in generated_registry.get("rows", []) if isinstance(row, dict)]
    resolved_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in sorted(MANUAL_STRATEGIES, key=lambda item: str(item.get("name") or "")):
        strategy_id = str(row.get("name") or "").strip()
        if not strategy_id:
            continue
        if strategy_id in seen_ids:
            raise ValueError(f"manual registry duplicate id in resolver: {strategy_id}")
        seen_ids.add(strategy_id)
        resolved_rows.append(
            {
                "strategy_id": strategy_id,
                "origin": RESOLVED_ORIGIN_MANUAL,
                "authority": "RESEARCH_ONLY_MANUAL",
                "factory_module": "research.registry",
                "factory_symbol": str(row.get("factory").__name__),
                "strategy_family": str(row.get("strategy_family") or ""),
                "research_only": True,
            }
        )
    for row in sorted(generated_rows, key=lambda item: str(item.get("generated_strategy_id") or "")):
        if str(row.get("state") or "") != REGISTRY_STATE:
            continue
        strategy_id = str(row.get("generated_strategy_id") or "")
        if not strategy_id:
            continue
        if strategy_id in seen_ids:
            raise ValueError(f"resolver collision for generated strategy id: {strategy_id}")
        if str(row.get("authority") or "") != REGISTRY_AUTHORITY:
            raise ValueError(f"resolver authority mismatch for generated strategy id: {strategy_id}")
        seen_ids.add(strategy_id)
        resolved_rows.append(
            {
                "strategy_id": strategy_id,
                "origin": RESOLVED_ORIGIN_GENERATED,
                "authority": REGISTRY_AUTHORITY,
                "factory_module": str(row.get("module_path") or "").removesuffix(".py").replace("/", "."),
                "factory_symbol": str(row.get("factory_symbol") or ""),
                "strategy_family": str(row.get("source_hypothesis_id") or ""),
                "research_only": True,
            }
        )
    resolved_rows.sort(key=lambda row: str(row.get("strategy_id") or ""))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "resolved_strategy_catalog",
        "resolved_catalog_identity": f"qrc_{stable_digest(resolved_rows)[:16]}",
        "rows": resolved_rows,
    }


def generate_preset_entry(
    *,
    source_hypothesis_id: str,
    thesis_row: dict[str, Any],
    registry_entry: dict[str, Any],
    identity_row: dict[str, Any],
) -> dict[str, Any]:
    if source_hypothesis_id != "atr_adaptive_trend_v0":
        return {
            "source_hypothesis_id": source_hypothesis_id,
            "preset_state": "BLOCKED",
            "blocker": "preset_generation_not_supported_for_thesis",
            "next_action": "complete_remaining_lineage_and_control_gaps",
        }
    timeframes = [value for value in str(thesis_row.get("timeframe") or "").split("|") if value]
    if len(timeframes) != 1:
        return {
            "source_hypothesis_id": source_hypothesis_id,
            "preset_state": "BLOCKED",
            "blocker": "timeframe_ambiguity_prevents_preset_generation",
            "next_action": "resolve_preset_timeframe_for_generated_strategy",
        }
    instrument = str(identity_row.get("instrument_identity") or "")
    if not instrument:
        return {
            "source_hypothesis_id": source_hypothesis_id,
            "preset_state": "BLOCKED",
            "blocker": "instrument_identity_missing",
            "next_action": "resolve_identity_ambiguity_for_thesis",
        }
    preset_name = f"{source_hypothesis_id}_generated_{timeframes[0]}"
    preset_id = f"qgp_{stable_digest({'preset_name': preset_name, 'strategy': registry_entry['generated_strategy_id']})[:16]}"
    return {
        "preset_id": preset_id,
        "preset_name": preset_name,
        "source_hypothesis_id": source_hypothesis_id,
        "generated_strategy_id": registry_entry["generated_strategy_id"],
        "timeframe": timeframes[0],
        "universe": [instrument],
        "parameter_values": {"trend_anchor_window": 50, "atr_window": 14, "entry_atr_multiple": 0.75, "exit_atr_multiple": 0.10},
        "cost_assumptions": {"mode": "cost_class_visible_only"},
        "slippage_assumptions": {"status": "not_materialized"},
        "preset_state": "GENERATED",
        "next_action": "evaluate_campaign_readiness_from_generated_preset",
    }


def _mechanism_null_controls(source_hypothesis_id: str) -> list[str]:
    mapping = {
        "atr_adaptive_trend_v0": ["matched_frequency_null", "sign_flipped_signal", "cost_only_baseline"],
        "volatility_compression_breakout_v0": ["shuffled_signal_timing", "matched_frequency_null"],
        "cross_sectional_momentum_v0": ["permuted_cross_sectional_ranking"],
        "dynamic_pairs_v0": ["pair_selection_placebo"],
    }
    return mapping.get(source_hypothesis_id, ["matched_frequency_null"])


def _portfolio_status(
    *,
    source_hypothesis_id: str,
    preset_entry: dict[str, Any] | None,
    identity_row: dict[str, Any],
) -> tuple[str, list[str], str]:
    resolution = str(identity_row.get("resolution_state") or "")
    if resolution in {"BLOCKED", "MISSING", "AMBIGUOUS", "CONFLICTING"}:
        return ("BLOCKED", ["identity_not_resolved"], "resolve_identity_ambiguity_for_thesis")
    if preset_entry is None or str(preset_entry.get("preset_state") or "") != "GENERATED":
        return ("BLOCKED", ["generated_preset_missing"], "resolve_preset_timeframe_for_generated_strategy")
    return ("READY_WITH_LIMITATIONS", ["oos_evidence_not_materialized", "null_controls_not_executed"], "complete_remaining_lineage_and_control_gaps")


def run_pipeline_for_hypotheses(
    *,
    repo_root: Path,
    source_hypothesis_ids: list[str],
) -> dict[str, Any]:
    inputs = _load_generation_inputs(repo_root)
    registry_entries: list[dict[str, Any]] = []
    preset_rows: list[dict[str, Any]] = []
    null_control_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    closeout_rows: list[dict[str, Any]] = []
    for source_hypothesis_id in sorted(source_hypothesis_ids):
        thesis_row = inputs["thesis_by_hypothesis"].get(source_hypothesis_id, {})
        identity_row = inputs["identity_by_hypothesis"].get(source_hypothesis_id, {})
        compile_result = compile_strategy_spec(repo_root=repo_root, source_hypothesis_id=source_hypothesis_id)
        outcome = compile_result["outcome"]
        if outcome != "SPECIFICATION_READY":
            final_outcome = {
                "BLOCKED_POLICY": "REJECTED_POLICY",
                "BLOCKED_DUPLICATE": "REJECTED_DUPLICATE",
                "BLOCKED_REJECTED_LINEAGE": "REJECTED_POLICY",
                "BLOCKED_DATA_REQUIREMENT": "BLOCKED_DATA",
            }.get(outcome, outcome)
            closeout_rows.append(
                {
                    "source_hypothesis_id": source_hypothesis_id,
                    "final_generation_outcome": final_outcome,
                    "reason": compile_result["reason"],
                }
            )
            continue

        spec: StrategySpecification = compile_result["specification"]
        materialization = materialize_generated_strategy(spec)
        if materialization["outcome"] != "CODE_GENERATED":
            closeout_rows.append(
                {
                    "source_hypothesis_id": source_hypothesis_id,
                    "final_generation_outcome": materialization["outcome"],
                    "reason": ",".join(materialization.get("errors", [])),
                }
            )
            continue
        sandbox = sandbox_validate_generated_strategy(spec=spec, materialization=materialization)
        if sandbox["status"] != "VALIDATED":
            closeout_rows.append(
                {
                    "source_hypothesis_id": source_hypothesis_id,
                    "final_generation_outcome": "QUARANTINED_VALIDATION",
                    "reason": sandbox["status"],
                }
            )
            continue
        admission = admit_generated_registry_entry(
            repo_root=repo_root,
            spec=spec,
            materialization=materialization,
            sandbox=sandbox,
        )
        if admission["outcome"] != REGISTRY_STATE:
            final_outcome = admission["outcome"]
            if final_outcome == "REJECTED_DUPLICATE":
                mapped = "REJECTED_DUPLICATE"
            else:
                mapped = "QUARANTINED_VALIDATION"
            closeout_rows.append(
                {
                    "source_hypothesis_id": source_hypothesis_id,
                    "final_generation_outcome": mapped,
                    "reason": admission["reason"],
                }
            )
            continue
        registry_entry = dict(admission["entry"])
        registry_entries.append(registry_entry)
        preset_entry = generate_preset_entry(
            source_hypothesis_id=source_hypothesis_id,
            thesis_row=thesis_row,
            registry_entry=registry_entry,
            identity_row=identity_row,
        )
        if preset_entry.get("preset_state") == "GENERATED":
            preset_rows.append(preset_entry)
        null_control_rows.append(
            {
                "null_control_spec_id": _null_control_id(registry_entry["generated_strategy_id"]),
                "source_hypothesis_id": source_hypothesis_id,
                "generated_strategy_id": registry_entry["generated_strategy_id"],
                "required_controls": _mechanism_null_controls(source_hypothesis_id),
                "execution_readiness": False,
                "implementation_readiness": True,
                "state": "SPECIFIED_NOT_EXECUTED",
                "deterministic_seed": stable_digest({"generated_strategy_id": registry_entry["generated_strategy_id"], "kind": "null"})[:16],
            }
        )
        inclusion_status, blockers, next_action = _portfolio_status(
            source_hypothesis_id=source_hypothesis_id,
            preset_entry=preset_entry if preset_entry.get("preset_state") == "GENERATED" else None,
            identity_row=identity_row,
        )
        lineage_rows.append(
            {
                "generated_lineage_id": _lineage_id(source_hypothesis_id),
                "source_hypothesis_id": source_hypothesis_id,
                "thesis_id": spec.thesis_id,
                "strategy_spec_id": spec.strategy_spec_id,
                "generated_strategy_id": registry_entry["generated_strategy_id"],
                "generated_registration_id": registry_entry["generated_registration_id"],
                "preset_id": preset_entry.get("preset_id", ""),
                "null_control_spec_id": _null_control_id(registry_entry["generated_strategy_id"]),
                "portfolio_cell_id": _portfolio_cell_id(source_hypothesis_id),
                "campaign_specification_identity": f"qgc_{stable_digest({'source_hypothesis_id': source_hypothesis_id, 'strategy': registry_entry['generated_strategy_id']})[:16]}",
                "campaign_readiness_state": inclusion_status,
                "blockers": blockers,
                "next_action": next_action,
            }
        )
        closeout_rows.append(
            {
                "source_hypothesis_id": source_hypothesis_id,
                "final_generation_outcome": "RESEARCH_REGISTERED_AUTOMATED",
                "generated_strategy_id": registry_entry["generated_strategy_id"],
                "preset_generated": preset_entry.get("preset_state") == "GENERATED",
                "campaign_readiness_state": inclusion_status,
                "blockers": blockers,
            }
        )

    preset_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "generated_research_presets",
        "generated_preset_identity": f"qgp_{stable_digest(preset_rows)[:16]}",
        "rows": sorted(preset_rows, key=lambda row: str(row.get("preset_name") or "")),
    }
    null_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "generated_null_controls",
        "generated_null_control_identity": f"qgn_{stable_digest(null_control_rows)[:16]}",
        "rows": sorted(null_control_rows, key=lambda row: str(row.get("source_hypothesis_id") or "")),
    }
    lineage_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "generated_campaign_lineage",
        "generated_lineage_identity": f"qgl_{stable_digest(lineage_rows)[:16]}",
        "rows": sorted(lineage_rows, key=lambda row: str(row.get("source_hypothesis_id") or "")),
    }
    closeout_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_automated_generation_closeout",
        "module_version": GENERATOR_VERSION,
        "resolved_catalog_identity": build_resolved_strategy_catalog(repo_root)["resolved_catalog_identity"],
        "rows": sorted(closeout_rows, key=lambda row: str(row.get("source_hypothesis_id") or "")),
        "summary": {
            "thesis_count": len(source_hypothesis_ids),
            "registered_count": sum(1 for row in closeout_rows if row.get("final_generation_outcome") == "RESEARCH_REGISTERED_AUTOMATED"),
            "blocked_count": sum(1 for row in closeout_rows if row.get("final_generation_outcome") != "RESEARCH_REGISTERED_AUTOMATED"),
        },
    }
    _atomic_write(repo_root / GENERATED_PRESETS_PATH, json.dumps(preset_payload, indent=2, sort_keys=True) + "\n")
    _atomic_write(repo_root / GENERATED_NULL_CONTROLS_PATH, json.dumps(null_payload, indent=2, sort_keys=True) + "\n")
    _atomic_write(repo_root / GENERATED_LINEAGE_PATH, json.dumps(lineage_payload, indent=2, sort_keys=True) + "\n")
    _atomic_write(repo_root / GENERATED_CLOSEOUT_PATH, json.dumps(closeout_payload, indent=2, sort_keys=True) + "\n")
    return closeout_payload


__all__ = [
    "GENERATOR_VERSION",
    "READY_FOR_PREREGISTRATION",
    "REGISTRY_AUTHORITY",
    "REGISTRY_STATE",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "StrategySpecification",
    "build_resolved_strategy_catalog",
    "compile_strategy_spec",
    "materialize_generated_strategy",
    "run_pipeline_for_hypotheses",
    "sandbox_validate_generated_strategy",
    "stable_digest",
    "static_validate_generated_source",
]
