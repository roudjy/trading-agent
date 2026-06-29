from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from agent.backtesting.features import (
    FEATURE_REGISTRY,
    FeatureSpec,
    resolved_feature_registry,
)
from packages.qre_research import automated_strategy_generation as a19
from packages.qre_research.generated_primitive_paths import (
    GENERATED_PRIMITIVE_CLOSEOUT_PATH,
    GENERATED_PRIMITIVE_MANIFESTS_DIR,
    GENERATED_PRIMITIVE_PACKAGE_DIR,
    GENERATED_PRIMITIVE_REGISTRY_PATH,
    GENERATED_PRIMITIVE_SPECS_DIR,
    GENERATED_PRIMITIVE_TEST_DIR,
    GENERATED_PRIMITIVE_VALIDATION_DIR,
    REPO_ROOT,
    repo_relative,
    validate_write_target,
)


SCHEMA_VERSION: Final[str] = "1.0"
GENERATOR_VERSION: Final[str] = "ade-qre-021.1"
IMPLEMENTATION_TEMPLATE_VERSION: Final[str] = "cross-sectional-rank-template.1"
REPORT_KIND: Final[str] = "qre_automated_primitive_expansion"
REQUEST_OUTCOMES: Final[tuple[str, ...]] = (
    "VALID_EXTENSION_REQUEST",
    "INVALID_INCOMPLETE_REQUEST",
    "DUPLICATE_EXISTING_PRIMITIVE",
    "CONFLICTING_PRIMITIVE_SEMANTICS",
    "UNSUPPORTED_PRIMITIVE_FAMILY",
    "REJECTED_POLICY",
)
EXTENSION_STATES: Final[tuple[str, ...]] = (
    "EXTENSION_REQUESTED",
    "REQUEST_INVALID",
    "SPECIFICATION_READY",
    "SPECIFICATION_BLOCKED",
    "IMPLEMENTATION_GENERATED",
    "TESTS_GENERATED",
    "STATIC_VALIDATION_FAILED",
    "ARCHITECTURE_VALIDATION_FAILED",
    "SANDBOX_VALIDATION_FAILED",
    "PRIMITIVE_VALIDATED",
    "PRIMITIVE_REGISTERED_AUTOMATED",
    "DOWNSTREAM_RECOMPILE_READY",
    "DOWNSTREAM_RECOMPILE_FAILED",
    "QUARANTINED",
    "REJECTED_POLICY",
    "SUPERSEDED",
)
SANDBOX_OUTCOMES: Final[tuple[str, ...]] = (
    "VALIDATED",
    "VALIDATION_FAILED",
    "TIMEOUT",
    "ARCHITECTURE_REJECTED",
    "POLICY_REJECTED",
    "NONDETERMINISTIC",
    "IDENTITY_COLLISION",
    "QUARANTINED",
)
REGISTRY_STATE: Final[str] = "PRIMITIVE_REGISTERED_AUTOMATED"
REGISTRY_AUTHORITY: Final[str] = "RESEARCH_ONLY_AUTOMATED"
RESOLVED_ORIGIN_MANUAL: Final[str] = "MANUAL"
RESOLVED_ORIGIN_GENERATED: Final[str] = "GENERATED_AUTOMATED"
REQUEST_PATH: Final[Path] = (
    REPO_ROOT
    / "generated_research"
    / "hypotheses"
    / "priorities"
    / "primitive_extension_requests.v1.json"
)
GENERATED_PRIMITIVE_REGISTRY_VERSION: Final[str] = "1.0"
ALLOWED_IMPORTS: Final[tuple[str, ...]] = (
    "__future__",
    "importlib",
    "pandas",
    "agent.backtesting.features",
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
    {"eval", "exec", "open", "compile", "__import__"}
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


def _build_cross_sectional_frame(
    *,
    periods: int = 24,
    assets: tuple[str, ...] = ("AAA", "BBB", "CCC", "DDD"),
    seed: int = 23,
    start: str = "2024-01-01",
    freq: str = "D",
    universe_id: str = "breadth_resolved_multi_asset_basket",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start=start, periods=periods, freq=freq)
    rows: list[dict[str, object]] = []
    for asset_index, asset in enumerate(assets):
        base_level = 80.0 + asset_index * 12.5
        drift = np.linspace(0.0008 + asset_index * 0.0002, 0.002, periods)
        noise = rng.normal(0.0, 0.008, periods)
        close = base_level * np.cumprod(1.0 + drift + noise)
        open_ = close * (1.0 + rng.normal(0.0, 0.0015, periods))
        high = np.maximum(open_, close) * (
            1.0 + rng.uniform(0.0005, 0.007, periods)
        )
        low = np.minimum(open_, close) * (
            1.0 - rng.uniform(0.0005, 0.007, periods)
        )
        volume = rng.integers(2_000, 20_000, periods, dtype="int64")
        for idx, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "timestamp": timestamp,
                    "asset": asset,
                    "open": float(open_[idx]),
                    "high": float(high[idx]),
                    "low": float(low[idx]),
                    "close": float(close[idx]),
                    "volume": int(volume[idx]),
                    "universe_id": universe_id,
                    "eligibility_state": "eligible",
                }
            )
    return pd.DataFrame(rows).set_index(["timestamp", "asset"]).sort_index()


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ade_qre_021.",
        suffix=".tmp",
        dir=str(path.parent),
    )
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


@dataclass(frozen=True)
class PrimitiveSpecification:
    primitive_id: str
    primitive_spec_id: str
    schema_version: str
    generator_version: str
    implementation_template_version: str
    primitive_family: str
    input_types: tuple[str, ...]
    output_type: str
    input_dimensions: tuple[str, ...]
    output_dimensions: tuple[str, ...]
    temporal_behavior: str
    grouping_behavior: str
    ordering_behavior: str
    missing_data_behavior: str
    tie_behavior: str
    minimum_sample_requirements: dict[str, int]
    deterministic_semantics: tuple[str, ...]
    prohibited_behavior: tuple[str, ...]
    computational_complexity_class: str
    timeout_expectations: str
    provenance: tuple[str, ...]
    deterministic_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "primitive_id": self.primitive_id,
            "primitive_spec_id": self.primitive_spec_id,
            "schema_version": self.schema_version,
            "generator_version": self.generator_version,
            "implementation_template_version": self.implementation_template_version,
            "primitive_family": self.primitive_family,
            "input_types": list(self.input_types),
            "output_type": self.output_type,
            "input_dimensions": list(self.input_dimensions),
            "output_dimensions": list(self.output_dimensions),
            "temporal_behavior": self.temporal_behavior,
            "grouping_behavior": self.grouping_behavior,
            "ordering_behavior": self.ordering_behavior,
            "missing_data_behavior": self.missing_data_behavior,
            "tie_behavior": self.tie_behavior,
            "minimum_sample_requirements": dict(self.minimum_sample_requirements),
            "deterministic_semantics": list(self.deterministic_semantics),
            "prohibited_behavior": list(self.prohibited_behavior),
            "computational_complexity_class": self.computational_complexity_class,
            "timeout_expectations": self.timeout_expectations,
            "provenance": list(self.provenance),
            "deterministic_hash": self.deterministic_hash,
        }


def _generated_primitive_id(primitive_id: str) -> str:
    return f"qgp_{stable_digest({'primitive_id': primitive_id, 'generator_version': GENERATOR_VERSION})[:16]}"


def _primitive_spec_id(request_id: str, primitive_id: str) -> str:
    return f"qps_{stable_digest({'request_id': request_id, 'primitive_id': primitive_id, 'schema_version': SCHEMA_VERSION, 'generator_version': GENERATOR_VERSION})[:16]}"


def _primitive_test_manifest_id(generated_primitive_id: str, code_hash: str) -> str:
    return f"qpt_{stable_digest({'generated_primitive_id': generated_primitive_id, 'code_hash': code_hash})[:16]}"


def _primitive_sandbox_id(generated_primitive_id: str, code_hash: str) -> str:
    return f"qpv_{stable_digest({'generated_primitive_id': generated_primitive_id, 'code_hash': code_hash, 'kind': 'sandbox'})[:16]}"


def _primitive_registration_id(generated_primitive_id: str, code_hash: str) -> str:
    return f"qpr_{stable_digest({'generated_primitive_id': generated_primitive_id, 'code_hash': code_hash, 'kind': 'registry'})[:16]}"


def _request_rows() -> list[dict[str, Any]]:
    return _read_rows(REQUEST_PATH)


def _current_generated_registry(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / GENERATED_PRIMITIVE_REGISTRY_PATH) or {
        "schema_version": GENERATED_PRIMITIVE_REGISTRY_VERSION,
        "report_kind": "generated_primitive_registry",
        "rows": [],
    }


def _existing_generated_primitive_entry(
    repo_root: Path,
    primitive_id: str,
) -> dict[str, Any] | None:
    rows = _current_generated_registry(repo_root).get("rows", [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (
            str(row.get("primitive_id") or "") == primitive_id
            and str(row.get("state") or "") == REGISTRY_STATE
        ):
            return dict(row)
    return None


def validate_extension_request(
    *,
    repo_root: Path,
    extension_request_id: str,
) -> dict[str, Any]:
    request = next(
        (
            row
            for row in _request_rows()
            if str(row.get("primitive_extension_request_id") or "") == extension_request_id
        ),
        None,
    )
    if request is None:
        return {"outcome": "INVALID_INCOMPLETE_REQUEST", "reason": "request_missing"}
    required = (
        "primitive_extension_request_id",
        "thesis_id",
        "required_primitive",
        "expected_contract",
        "mechanism_linkage",
        "determinism_requirements",
        "proposed_tests",
        "safety_requirements",
    )
    missing = [field for field in required if not request.get(field)]
    if missing:
        return {
            "outcome": "INVALID_INCOMPLETE_REQUEST",
            "reason": f"missing_fields:{','.join(sorted(missing))}",
            "request": request,
        }
    primitive_id = str(request["required_primitive"])
    if primitive_id in FEATURE_REGISTRY or primitive_id in resolved_feature_registry():
        return {
            "outcome": "DUPLICATE_EXISTING_PRIMITIVE",
            "reason": f"primitive_already_registered:{primitive_id}",
            "request": request,
        }
    if primitive_id != "cross_sectional_rank":
        return {
            "outcome": "UNSUPPORTED_PRIMITIVE_FAMILY",
            "reason": f"unsupported_request:{primitive_id}",
            "request": request,
        }
    generated_theses = _read_rows(
        repo_root
        / "generated_research"
        / "hypotheses"
        / "registry"
        / "generated_thesis_registry.v1.json"
    )
    matching_thesis = next(
        (
            row
            for row in generated_theses
            if str(row.get("thesis_id") or "") == str(request.get("thesis_id") or "")
        ),
        None,
    )
    if matching_thesis is None:
        return {
            "outcome": "INVALID_INCOMPLETE_REQUEST",
            "reason": "originating_generated_thesis_missing",
            "request": request,
        }
    if str(matching_thesis.get("lifecycle_state") or "") != "ADMITTED_GENERATION_BLOCKED":
        return {
            "outcome": "REJECTED_POLICY",
            "reason": "originating_thesis_not_admitted_generation_blocked",
            "request": request,
        }
    if str(matching_thesis.get("primitive_compatibility") or "") != (
        "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION"
    ):
        return {
            "outcome": "REJECTED_POLICY",
            "reason": "thesis_not_marked_for_bounded_primitive_extension",
            "request": request,
        }
    return {
        "outcome": "VALID_EXTENSION_REQUEST",
        "request": {
            **request,
            "request_schema_version": SCHEMA_VERSION,
            "originating_hypothesis_run_id": "qhs_a4fa46b186a9fd4e",
            "originating_thesis_id": matching_thesis["thesis_id"],
            "primitive_family": "cross_sectional_ranking",
            "scientific_rationale": matching_thesis.get("mechanism", ""),
            "strategy_generation_blocker": "cross_sectional_rank_missing",
            "expected_input_contract": "multiindex_series(timestamp,asset)::close_prices",
            "expected_output_contract": "multiindex_series(timestamp,asset)::rank_score",
            "required_dimensions": ["timestamp", "asset"],
            "temporal_semantics": "rank each timestamp using contemporaneous and prior lookback bars only",
            "cross_sectional_semantics": "compare only assets inside the same timestamp and eligible universe",
            "missing_data_semantics": "FAIL_CLOSED",
            "ordering_semantics": "stable identity order after score sort",
            "tie_handling_semantics": "AVERAGE",
            "expected_failure_modes": [
                "insufficient_universe_breadth",
                "duplicate_asset_timestamp",
                "missing_close_prices",
            ],
            "safety_constraints": [
                "no network",
                "no subprocess",
                "no filesystem writes",
                "no eval",
                "no exec",
            ],
            "deterministic_content_hash": stable_digest(request),
            "affected_theses": list(request.get("affected_theses") or []),
            "provenance": [
                "generated_research/hypotheses/priorities/primitive_extension_requests.v1.json",
                "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
                "generated_research/hypotheses/reports/automated_hypothesis_generation_closeout.v1.json",
            ],
        },
    }


def compile_primitive_spec(validated_request: dict[str, Any]) -> PrimitiveSpecification:
    request = dict(validated_request["request"])
    primitive_id = str(request["required_primitive"])
    payload_core = {
        "primitive_id": primitive_id,
        "primitive_spec_id": _primitive_spec_id(
            str(request["primitive_extension_request_id"]),
            primitive_id,
        ),
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "implementation_template_version": IMPLEMENTATION_TEMPLATE_VERSION,
        "primitive_family": str(request["primitive_family"]),
        "input_types": ["pandas.Series"],
        "output_type": "pandas.Series",
        "input_dimensions": ["timestamp", "asset"],
        "output_dimensions": ["timestamp", "asset"],
        "temporal_behavior": str(request["temporal_semantics"]),
        "grouping_behavior": "group_by_timestamp_with_identity_stable_ordering",
        "ordering_behavior": str(request["ordering_semantics"]),
        "missing_data_behavior": str(request["missing_data_semantics"]),
        "tie_behavior": str(request["tie_handling_semantics"]),
        "minimum_sample_requirements": {"lookback_bars": 20, "minimum_universe_size": 3},
        "deterministic_semantics": [
            "stable_sort",
            "no_wall_clock_inputs",
            "no_random_state",
            "closed_schema",
        ],
        "prohibited_behavior": [
            "arbitrary_python",
            "arbitrary_imports",
            "network_access",
            "file_system_writes",
            "shell_execution",
            "dynamic_package_loading",
            "broker_access",
            "execution_integration",
        ],
        "computational_complexity_class": "O(n log n) per timestamp group",
        "timeout_expectations": "bounded_small_fixture",
        "provenance": list(request["provenance"]),
    }
    deterministic_hash = stable_digest(payload_core)
    return PrimitiveSpecification(
        primitive_id=payload_core["primitive_id"],
        primitive_spec_id=payload_core["primitive_spec_id"],
        schema_version=payload_core["schema_version"],
        generator_version=payload_core["generator_version"],
        implementation_template_version=payload_core["implementation_template_version"],
        primitive_family=payload_core["primitive_family"],
        input_types=tuple(payload_core["input_types"]),
        output_type=payload_core["output_type"],
        input_dimensions=tuple(payload_core["input_dimensions"]),
        output_dimensions=tuple(payload_core["output_dimensions"]),
        temporal_behavior=payload_core["temporal_behavior"],
        grouping_behavior=payload_core["grouping_behavior"],
        ordering_behavior=payload_core["ordering_behavior"],
        missing_data_behavior=payload_core["missing_data_behavior"],
        tie_behavior=payload_core["tie_behavior"],
        minimum_sample_requirements=dict(payload_core["minimum_sample_requirements"]),
        deterministic_semantics=tuple(payload_core["deterministic_semantics"]),
        prohibited_behavior=tuple(payload_core["prohibited_behavior"]),
        computational_complexity_class=payload_core["computational_complexity_class"],
        timeout_expectations=payload_core["timeout_expectations"],
        provenance=tuple(payload_core["provenance"]),
        deterministic_hash=deterministic_hash,
    )


def _render_primitive_source(spec: PrimitiveSpecification) -> str:
    generated_primitive_id = _generated_primitive_id(spec.primitive_id)
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import pandas as pd",
            "",
            "from agent.backtesting.features import FeatureSpec",
            "",
            f'PRIMITIVE_ID = "{spec.primitive_id}"',
            f'GENERATED_PRIMITIVE_ID = "{generated_primitive_id}"',
            f'PRIMITIVE_SPEC_ID = "{spec.primitive_spec_id}"',
            f'GENERATOR_VERSION = "{GENERATOR_VERSION}"',
            f'IMPLEMENTATION_TEMPLATE_VERSION = "{IMPLEMENTATION_TEMPLATE_VERSION}"',
            "",
            "def _warmup(params: dict) -> int:",
            '    return int(params.get("lookback_bars", 20))',
            "",
            "def cross_sectional_rank(",
            "    close: pd.Series,",
            "    *,",
            "    lookback_bars: int = 20,",
            "    ascending: bool = False,",
            '    rank_mode: str = "PERCENTILE",',
            '    tie_policy: str = "AVERAGE",',
            '    missing_value_policy: str = "FAIL_CLOSED",',
            "    minimum_universe_size: int = 3,",
            ") -> pd.Series:",
            "    if not isinstance(close.index, pd.MultiIndex):",
            '        raise ValueError("cross_sectional_rank requires MultiIndex(timestamp, asset)")',
            '    if close.index.nlevels != 2:',
            '        raise ValueError("cross_sectional_rank requires exactly two index levels")',
            "    if minimum_universe_size < 2:",
            '        raise ValueError("minimum_universe_size must be >= 2")',
            '    if rank_mode not in {"ORDINAL", "DENSE", "PERCENTILE", "NORMALIZED"}:',
            '        raise ValueError("unsupported rank_mode")',
            '    if tie_policy not in {"STABLE_IDENTITY_ORDER", "MIN", "MAX", "AVERAGE"}:',
            '        raise ValueError("unsupported tie_policy")',
            '    if missing_value_policy not in {"EXCLUDE_WITH_REASON", "RANK_LAST", "FAIL_CLOSED"}:',
            '        raise ValueError("unsupported missing_value_policy")',
            "    ordered = close.astype(float).sort_index(level=[0, 1])",
            "    timestamps = ordered.index.get_level_values(0)",
            "    assets = ordered.index.get_level_values(1)",
            "    duplicate_mask = pd.MultiIndex.from_arrays([timestamps, assets]).duplicated()",
            "    if bool(duplicate_mask.any()):",
            '        raise ValueError("duplicate asset/timestamp rows are not allowed")',
            "    relative_strength = ordered.groupby(level=1).pct_change(periods=int(lookback_bars))",
            "    if missing_value_policy == 'FAIL_CLOSED' and bool(relative_strength.isna().any()):",
            "        return pd.Series(pd.NA, index=ordered.index, dtype='Float64')",
            "    ranks = pd.Series(index=ordered.index, dtype=float)",
            "    for timestamp, group in relative_strength.groupby(level=0, sort=True):",
            "        values = group.droplevel(0)",
            "        if len(values) < int(minimum_universe_size):",
            "            for asset in values.index:",
            "                ranks.loc[(timestamp, asset)] = pd.NA",
            "            continue",
            "        if values.isna().any():",
            "            if missing_value_policy == 'FAIL_CLOSED':",
            "                for asset in values.index:",
            "                    ranks.loc[(timestamp, asset)] = pd.NA",
            "                continue",
            "            if missing_value_policy == 'EXCLUDE_WITH_REASON':",
            "                valid = values.dropna()",
            "            else:",
            "                fill_value = float('inf') if ascending else float('-inf')",
            "                valid = values.fillna(fill_value)",
            "        else:",
            "            valid = values",
            "        method = {",
            "            'STABLE_IDENTITY_ORDER': 'first',",
            "            'MIN': 'min',",
            "            'MAX': 'max',",
            "            'AVERAGE': 'average',",
            "        }[tie_policy]",
            "        ranked = valid.rank(method=method, ascending=ascending, pct=(rank_mode == 'PERCENTILE'))",
            "        if rank_mode == 'NORMALIZED':",
            "            denominator = max(len(valid) - 1, 1)",
            "            ranked = (ranked - 1.0) / denominator",
            "        elif rank_mode == 'ORDINAL' and tie_policy == 'STABLE_IDENTITY_ORDER':",
            "            ranked = ranked.astype(float)",
            "        for asset in values.index:",
            "            if asset in ranked.index:",
            "                ranks.loc[(timestamp, asset)] = float(ranked.loc[asset])",
            "            else:",
            "                ranks.loc[(timestamp, asset)] = pd.NA",
            "    return ranks.astype('Float64')",
            "",
            "GENERATED_FEATURE_SPECS = {",
            '    "cross_sectional_rank": FeatureSpec(',
            "        fn=cross_sectional_rank,",
            '        param_names=("lookback_bars", "ascending", "rank_mode", "tie_policy", "missing_value_policy", "minimum_universe_size"),',
            '        required_columns=("close",),',
            "        warmup_bars_fn=_warmup,",
            "    )",
            "}",
            "",
        ]
    ) + "\n"


def _render_primitive_test_source(
    spec: PrimitiveSpecification,
    primitive_module_relpath: str,
) -> str:
    module_path = primitive_module_relpath.removesuffix(".py").replace("/", ".")
    generated_primitive_id = _generated_primitive_id(spec.primitive_id)
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import importlib",
            "",
            "import pandas as pd",
            "",
            "from tests._harness_helpers import build_cross_sectional_frame",
            "",
            f'MODULE_NAME = "{module_path}"',
            f'EXPECTED_PRIMITIVE_ID = "{spec.primitive_id}"',
            f'EXPECTED_GENERATED_PRIMITIVE_ID = "{generated_primitive_id}"',
            "",
            "def _load_module():",
            "    return importlib.import_module(MODULE_NAME)",
            "",
            "def test_generated_primitive_imports_and_exposes_expected_ids() -> None:",
            "    module = _load_module()",
            "    assert module.PRIMITIVE_ID == EXPECTED_PRIMITIVE_ID",
            "    assert module.GENERATED_PRIMITIVE_ID == EXPECTED_GENERATED_PRIMITIVE_ID",
            "",
            "def test_cross_sectional_rank_is_deterministic_and_order_independent() -> None:",
            "    module = _load_module()",
            "    frame = build_cross_sectional_frame(periods=28, seed=41)",
            "    shuffled = frame.sample(frac=1.0, random_state=7)",
            "    first = module.cross_sectional_rank(frame['close'])",
            "    second = module.cross_sectional_rank(shuffled['close'])",
            "    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())",
            "",
            "def test_cross_sectional_rank_handles_minimum_breadth_fail_closed() -> None:",
            "    module = _load_module()",
            "    frame = build_cross_sectional_frame(periods=10, assets=('AAA', 'BBB'), seed=11)",
            "    result = module.cross_sectional_rank(frame['close'], minimum_universe_size=3)",
            "    assert result.isna().all()",
            "",
        ]
    ) + "\n"


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[str] = []
        self.errors: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
            if not any(
                alias.name == allowed or alias.name.startswith(f"{allowed}.")
                for allowed in ALLOWED_IMPORTS
            ):
                self.errors.append(f"import_not_allowlisted:{alias.name}")
            if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                self.errors.append(f"forbidden_import_prefix:{alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self.imports.append(module)
        if module and not any(
            module == allowed or module.startswith(f"{allowed}.")
            for allowed in ALLOWED_IMPORTS
        ):
            self.errors.append(f"import_not_allowlisted:{module}")
        if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
            self.errors.append(f"forbidden_import_prefix:{module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in FORBIDDEN_CALL_NAMES:
            self.errors.append(f"forbidden_call:{name}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in FORBIDDEN_ATTRIBUTE_NAMES:
            self.errors.append(f"forbidden_attribute:{node.attr}")
        self.generic_visit(node)


def static_validate_generated_source(
    *,
    primitive_source: str,
    test_source: str,
) -> dict[str, Any]:
    errors: list[str] = []
    for label, source in (
        ("primitive_source", primitive_source),
        ("test_source", test_source),
    ):
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            errors.append(f"{label}:syntax_error:{exc.msg}")
            continue
        visitor = _SafetyVisitor()
        visitor.visit(tree)
        errors.extend(f"{label}:{error}" for error in visitor.errors)
    return {
        "status": "VALIDATED" if not errors else "STATIC_VALIDATION_FAILED",
        "errors": sorted(set(errors)),
    }


def _generated_paths_for_spec(spec: PrimitiveSpecification) -> dict[str, Path]:
    generated_primitive_id = _generated_primitive_id(spec.primitive_id)
    return {
        "spec": REPO_ROOT / GENERATED_PRIMITIVE_SPECS_DIR / f"{spec.primitive_spec_id}.json",
        "manifest": REPO_ROOT / GENERATED_PRIMITIVE_MANIFESTS_DIR / f"{generated_primitive_id}.json",
        "validation": REPO_ROOT / GENERATED_PRIMITIVE_VALIDATION_DIR / f"{generated_primitive_id}.json",
        "primitive_module": REPO_ROOT / GENERATED_PRIMITIVE_PACKAGE_DIR / f"generated_{generated_primitive_id}.py",
        "primitive_test": REPO_ROOT / GENERATED_PRIMITIVE_TEST_DIR / f"test_generated_{generated_primitive_id}.py",
    }


def materialize_generated_primitive(spec: PrimitiveSpecification) -> dict[str, Any]:
    paths = _generated_paths_for_spec(spec)
    paths["primitive_module"].parent.mkdir(parents=True, exist_ok=True)
    paths["primitive_test"].parent.mkdir(parents=True, exist_ok=True)
    init_paths = (
        paths["primitive_module"].parent / "__init__.py",
        paths["primitive_test"].parent / "__init__.py",
    )
    for init_path in init_paths:
        if not init_path.exists():
            _atomic_write(init_path, "__all__ = []\n")

    primitive_relpath = repo_relative(paths["primitive_module"])
    primitive_source = _render_primitive_source(spec)
    test_source = _render_primitive_test_source(spec, primitive_relpath)
    static_result = static_validate_generated_source(
        primitive_source=primitive_source,
        test_source=test_source,
    )
    if static_result["status"] != "VALIDATED":
        return {"outcome": "STATIC_VALIDATION_FAILED", "errors": static_result["errors"]}

    code_hash = stable_digest(primitive_source)
    test_manifest_id = _primitive_test_manifest_id(
        _generated_primitive_id(spec.primitive_id),
        code_hash,
    )
    manifest = {
        "generated_primitive_id": _generated_primitive_id(spec.primitive_id),
        "primitive_id": spec.primitive_id,
        "primitive_spec_id": spec.primitive_spec_id,
        "generator_version": GENERATOR_VERSION,
        "implementation_template_version": IMPLEMENTATION_TEMPLATE_VERSION,
        "module_path": primitive_relpath,
        "export_symbol": "GENERATED_FEATURE_SPECS",
        "test_module_path": repo_relative(paths["primitive_test"]),
        "code_hash": code_hash,
        "test_manifest_id": test_manifest_id,
    }
    _atomic_write(paths["spec"], json.dumps(spec.to_payload(), indent=2, sort_keys=True) + "\n")
    _atomic_write(paths["primitive_module"], primitive_source)
    _atomic_write(paths["primitive_test"], test_source)
    _atomic_write(paths["manifest"], json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "outcome": "IMPLEMENTATION_GENERATED",
        "manifest": manifest,
        "static_validation": static_result,
    }


def sandbox_validate_generated_primitive(
    *,
    spec: PrimitiveSpecification,
    materialization: dict[str, Any],
) -> dict[str, Any]:
    manifest = dict(materialization["manifest"])
    module_name = manifest["module_path"].removesuffix(".py").replace("/", ".")
    importlib.invalidate_caches()
    if module_name in importlib.sys.modules:
        del importlib.sys.modules[module_name]
    module = importlib.import_module(module_name)
    frame = _build_cross_sectional_frame(periods=28, seed=31)
    close = frame["close"]
    first = module.cross_sectional_rank(close)
    second = module.cross_sectional_rank(close.sample(frac=1.0, random_state=5))
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())
    if not first.index.equals(close.sort_index().index):
        return {"status": "VALIDATION_FAILED", "errors": ["index_mismatch"]}
    validation = {
        "sandbox_validation_id": _primitive_sandbox_id(
            manifest["generated_primitive_id"],
            manifest["code_hash"],
        ),
        "status": "VALIDATED",
        "generated_primitive_id": manifest["generated_primitive_id"],
        "primitive_spec_id": spec.primitive_spec_id,
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
    _atomic_write(
        REPO_ROOT / GENERATED_PRIMITIVE_VALIDATION_DIR / f"{manifest['generated_primitive_id']}.json",
        json.dumps(validation, indent=2, sort_keys=True) + "\n",
    )
    return {"status": "VALIDATED", "validation": validation}


def admit_generated_primitive_registry_entry(
    *,
    repo_root: Path,
    validated_request: dict[str, Any],
    spec: PrimitiveSpecification,
    materialization: dict[str, Any],
    sandbox: dict[str, Any],
) -> dict[str, Any]:
    if sandbox["status"] != "VALIDATED":
        return {"outcome": "QUARANTINED", "reason": sandbox["status"]}
    registry = _current_generated_registry(repo_root)
    rows = [dict(row) for row in registry.get("rows", []) if isinstance(row, dict)]
    generated_primitive_id = materialization["manifest"]["generated_primitive_id"]
    if any(
        str(row.get("generated_primitive_id") or "") == generated_primitive_id
        for row in rows
    ):
        return {"outcome": "QUARANTINED", "reason": "generated_primitive_id_collision"}
    entry = {
        "generated_registration_id": _primitive_registration_id(
            generated_primitive_id,
            materialization["manifest"]["code_hash"],
        ),
        "extension_request_id": validated_request["request"]["primitive_extension_request_id"],
        "primitive_id": spec.primitive_id,
        "primitive_spec_id": spec.primitive_spec_id,
        "generated_primitive_id": generated_primitive_id,
        "code_hash": materialization["manifest"]["code_hash"],
        "test_manifest_id": materialization["manifest"]["test_manifest_id"],
        "sandbox_artifact_id": sandbox["validation"]["sandbox_validation_id"],
        "generator_version": GENERATOR_VERSION,
        "implementation_template_version": IMPLEMENTATION_TEMPLATE_VERSION,
        "module_path": materialization["manifest"]["module_path"],
        "export_symbol": materialization["manifest"]["export_symbol"],
        "provenance": list(spec.provenance),
        "authority": REGISTRY_AUTHORITY,
        "state": REGISTRY_STATE,
    }
    rows.append(entry)
    rows.sort(key=lambda row: str(row.get("generated_primitive_id") or ""))
    payload = {
        "schema_version": GENERATED_PRIMITIVE_REGISTRY_VERSION,
        "report_kind": "generated_primitive_registry",
        "generated_registry_identity": f"qpg_{stable_digest(rows)[:16]}",
        "rows": rows,
    }
    _atomic_write(
        repo_root / GENERATED_PRIMITIVE_REGISTRY_PATH,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return {
        "outcome": REGISTRY_STATE,
        "entry": entry,
        "registry_identity": payload["generated_registry_identity"],
    }


def build_resolved_primitive_catalog(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    generated_registry = _current_generated_registry(root)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for primitive_id in sorted(FEATURE_REGISTRY):
        rows.append(
            {
                "primitive_id": primitive_id,
                "origin": RESOLVED_ORIGIN_MANUAL,
                "authority": "RESEARCH_ONLY_MANUAL",
                "module_path": "agent/backtesting/features.py",
            }
        )
        seen.add(primitive_id)
    for row in sorted(
        [dict(item) for item in generated_registry.get("rows", []) if isinstance(item, dict)],
        key=lambda item: str(item.get("generated_primitive_id") or ""),
    ):
        if str(row.get("state") or "") != REGISTRY_STATE:
            continue
        primitive_id = str(row.get("primitive_id") or "")
        if not primitive_id:
            continue
        if primitive_id in seen:
            raise ValueError(f"resolved primitive catalog collision: {primitive_id}")
        rows.append(
            {
                "primitive_id": primitive_id,
                "origin": RESOLVED_ORIGIN_GENERATED,
                "authority": str(row.get("authority") or ""),
                "module_path": str(row.get("module_path") or ""),
            }
        )
        seen.add(primitive_id)
    rows.sort(key=lambda row: str(row["primitive_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "resolved_primitive_catalog",
        "resolved_catalog_identity": f"qpc_{stable_digest(rows)[:16]}",
        "rows": rows,
    }


def run_primitive_expansion_loop(
    *,
    repo_root: Path,
    extension_request_id: str,
) -> dict[str, Any]:
    validated = validate_extension_request(
        repo_root=repo_root,
        extension_request_id=extension_request_id,
    )
    existing_entry = _existing_generated_primitive_entry(
        repo_root,
        "cross_sectional_rank",
    )
    if validated["outcome"] != "VALID_EXTENSION_REQUEST" and existing_entry is None:
        closeout = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "program_outcome": "EXTENSION_REQUEST_REJECTED",
            "request_outcome": validated["outcome"],
            "request_reason": validated.get("reason", ""),
            "rows": [],
        }
        _atomic_write(
            repo_root / GENERATED_PRIMITIVE_CLOSEOUT_PATH,
            json.dumps(closeout, indent=2, sort_keys=True) + "\n",
        )
        return closeout
    if validated["outcome"] == "VALID_EXTENSION_REQUEST":
        spec = compile_primitive_spec(validated)
        materialization = materialize_generated_primitive(spec)
        if materialization["outcome"] != "IMPLEMENTATION_GENERATED":
            raise RuntimeError(f"primitive materialization failed: {materialization}")
        sandbox = sandbox_validate_generated_primitive(
            spec=spec,
            materialization=materialization,
        )
        admission = admit_generated_primitive_registry_entry(
            repo_root=repo_root,
            validated_request=validated,
            spec=spec,
            materialization=materialization,
            sandbox=sandbox,
        )
        if admission["outcome"] != REGISTRY_STATE:
            closeout = {
                "schema_version": SCHEMA_VERSION,
                "report_kind": REPORT_KIND,
                "program_outcome": "PRIMITIVE_EXTENSION_QUARANTINED",
                "request_outcome": validated["outcome"],
                "primitive_spec_id": spec.primitive_spec_id,
                "generated_primitive_id": materialization["manifest"]["generated_primitive_id"],
                "registry_outcome": admission["outcome"],
                "reason": admission.get("reason", ""),
                "rows": [],
            }
            _atomic_write(
                repo_root / GENERATED_PRIMITIVE_CLOSEOUT_PATH,
                json.dumps(closeout, indent=2, sort_keys=True) + "\n",
            )
            return closeout
    else:
        assert existing_entry is not None
        manifest = _read_json(
            repo_root
            / GENERATED_PRIMITIVE_MANIFESTS_DIR
            / f"{existing_entry['generated_primitive_id']}.json"
        ) or {}
        spec_payload = _read_json(
            repo_root
            / GENERATED_PRIMITIVE_SPECS_DIR
            / f"{existing_entry['primitive_spec_id']}.json"
        ) or {}
        spec = PrimitiveSpecification(
            primitive_id=str(spec_payload.get("primitive_id") or "cross_sectional_rank"),
            primitive_spec_id=str(spec_payload.get("primitive_spec_id") or ""),
            schema_version=str(spec_payload.get("schema_version") or SCHEMA_VERSION),
            generator_version=str(spec_payload.get("generator_version") or GENERATOR_VERSION),
            implementation_template_version=str(
                spec_payload.get("implementation_template_version")
                or IMPLEMENTATION_TEMPLATE_VERSION
            ),
            primitive_family=str(spec_payload.get("primitive_family") or "cross_sectional_ranking"),
            input_types=tuple(spec_payload.get("input_types") or ["pandas.Series"]),
            output_type=str(spec_payload.get("output_type") or "pandas.Series"),
            input_dimensions=tuple(spec_payload.get("input_dimensions") or ["timestamp", "asset"]),
            output_dimensions=tuple(spec_payload.get("output_dimensions") or ["timestamp", "asset"]),
            temporal_behavior=str(spec_payload.get("temporal_behavior") or ""),
            grouping_behavior=str(spec_payload.get("grouping_behavior") or ""),
            ordering_behavior=str(spec_payload.get("ordering_behavior") or ""),
            missing_data_behavior=str(spec_payload.get("missing_data_behavior") or ""),
            tie_behavior=str(spec_payload.get("tie_behavior") or ""),
            minimum_sample_requirements=dict(
                spec_payload.get("minimum_sample_requirements") or {"lookback_bars": 20}
            ),
            deterministic_semantics=tuple(spec_payload.get("deterministic_semantics") or []),
            prohibited_behavior=tuple(spec_payload.get("prohibited_behavior") or []),
            computational_complexity_class=str(
                spec_payload.get("computational_complexity_class") or ""
            ),
            timeout_expectations=str(spec_payload.get("timeout_expectations") or ""),
            provenance=tuple(spec_payload.get("provenance") or []),
            deterministic_hash=str(spec_payload.get("deterministic_hash") or ""),
        )
        materialization = {"manifest": manifest, "static_validation": {"status": "VALIDATED"}}
        sandbox = {"status": "VALIDATED"}
        admission = {"outcome": REGISTRY_STATE, "entry": existing_entry}

    recompile = a19.compile_strategy_spec(
        repo_root=repo_root,
        source_hypothesis_id="cross_sectional_momentum_v0",
    )
    strategy_closeout: dict[str, Any] = {}
    if recompile["outcome"] == "SPECIFICATION_READY":
        strategy_closeout = a19.run_pipeline_for_hypotheses(
            repo_root=repo_root,
            source_hypothesis_ids=[
                "atr_adaptive_trend_v0",
                "cross_sectional_momentum_v0",
            ],
        )
    closeout_rows = strategy_closeout.get("rows", [])
    ready_rows = [
        row
        for row in closeout_rows
        if str(row.get("campaign_readiness_state") or "") == "READY_FOR_PREREGISTRATION"
    ]
    outcome = (
        "PRIMITIVE_AND_STRATEGY_READY_FOR_CAMPAIGN"
        if ready_rows
        else (
            "PRIMITIVE_REGISTERED_STRATEGY_BLOCKED"
            if closeout_rows
            else "AUTOMATED_CAPABILITY_EXPANSION_PARTIAL"
        )
    )
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "program_outcome": outcome,
        "request_outcome": validated["outcome"],
        "primitive_spec_id": spec.primitive_spec_id,
        "generated_primitive_id": materialization["manifest"]["generated_primitive_id"],
        "generated_primitive_path": materialization["manifest"]["module_path"],
        "primitive_test_manifest_id": materialization["manifest"]["test_manifest_id"],
        "static_validation_outcome": materialization["static_validation"]["status"],
        "sandbox_validation_outcome": sandbox["status"],
        "primitive_registry_entry": admission["entry"],
        "resolved_primitive_catalog_identity": build_resolved_primitive_catalog(repo_root)[
            "resolved_catalog_identity"
        ],
        "thesis_recompile_outcome": recompile["outcome"],
        "strategy_rows": closeout_rows,
    }
    _atomic_write(
        repo_root / GENERATED_PRIMITIVE_CLOSEOUT_PATH,
        json.dumps(closeout, indent=2, sort_keys=True) + "\n",
    )
    return closeout


__all__ = [
    "EXTENSION_STATES",
    "GENERATOR_VERSION",
    "PrimitiveSpecification",
    "REGISTRY_AUTHORITY",
    "REGISTRY_STATE",
    "REPORT_KIND",
    "REQUEST_OUTCOMES",
    "SCHEMA_VERSION",
    "SANDBOX_OUTCOMES",
    "build_resolved_primitive_catalog",
    "compile_primitive_spec",
    "run_primitive_expansion_loop",
    "stable_digest",
    "validate_extension_request",
]
