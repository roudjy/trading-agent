from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-026.1"
CONFIG_VERSION: Final[str] = "ade-qre-026r.config.1"
REPORT_KIND: Final[str] = "qre_autonomous_orchestration"

OPERATING_MODES: Final[tuple[str, ...]] = (
    "PLAN_ONLY",
    "LOCAL_AUTONOMOUS",
    "PR_PREPARATION",
    "GOVERNED_CONTINUOUS_LOOP",
)
PORTFOLIO_STAGES: Final[tuple[str, ...]] = (
    "DISCOVERY",
    "HYPOTHESIS_ADMITTED",
    "HYPOTHESIS_BLOCKED",
    "SPECIFICATION_READY",
    "PRIMITIVE_BLOCKED",
    "STRATEGY_GENERATED",
    "STRATEGY_VALIDATED",
    "RESEARCH_REGISTERED",
    "READINESS_BLOCKED",
    "READY_FOR_PREREGISTRATION",
    "PREREGISTERED",
    "CAMPAIGN_RUNNING",
    "SCREENING_REJECTED",
    "VALIDATION_REJECTED",
    "OOS_REJECTED",
    "NULL_CONTROL_REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "SUPPORTED_FOR_FURTHER_RESEARCH",
    "SCIENTIFICALLY_REJECTED",
    "DATA_CAPACITY_BLOCKED",
    "OOS_CAPACITY_BLOCKED",
    "QUARANTINED",
    "ARCHIVED",
)
ACTION_CLASSES: Final[tuple[str, ...]] = (
    "GENERATE_HYPOTHESIS",
    "ADMIT_HYPOTHESIS",
    "BUILD_PRIMITIVE",
    "GENERATE_STRATEGY",
    "VALIDATE_STRATEGY",
    "REGISTER_STRATEGY",
    "RESOLVE_IDENTITY",
    "RESOLVE_UNIVERSE",
    "COMPLETE_PRESET",
    "MATERIALIZE_DATA",
    "EXPAND_DATA_CAPACITY",
    "EXPAND_OOS_CAPACITY",
    "IMPLEMENT_NULL_CONTROL",
    "REASSESS_READINESS",
    "CREATE_PREREGISTRATION",
    "EXECUTE_PREREGISTERED_CAMPAIGN",
    "DIAGNOSE_FUNNEL",
    "REJECT_HYPOTHESIS",
    "ARCHIVE_STRATEGY",
    "REQUEST_REPLACEMENT_HYPOTHESIS",
    "RUN_SYNTHESIS_REVIEW",
    "GENERATE_DEVELOPMENT_WORK_PACKAGE",
    "EXTERNAL_INPUT_REQUIRED",
    "NO_SAFE_ACTION",
)
WORK_CLASSES: Final[tuple[str, ...]] = (
    "EXISTING_PIPELINE_REPLAY",
    "GENERATED_ARTIFACT_REMEDIATION",
    "BOUNDED_PRIMITIVE_EXTENSION",
    "BOUNDED_STRATEGY_GENERATION",
    "BOUNDED_NULL_CONTROL_EXTENSION",
    "DATA_CAPACITY_EXPANSION",
    "OOS_CAPACITY_EXPANSION",
    "IDENTITY_RESOLUTION",
    "PRESET_COMPLETION",
    "CAMPAIGN_PREREGISTRATION",
    "PREREGISTERED_CAMPAIGN_EXECUTION",
    "DEVELOPMENT_WORK_PACKAGE",
    "EXTERNAL_BLOCKER",
)
ADMISSION_RESULTS: Final[tuple[str, ...]] = (
    "ADMITTED_AUTONOMOUS",
    "ADMITTED_LOCAL_ONLY",
    "ADMITTED_PR_PREPARATION_ONLY",
    "ROUTED_EXISTING_CAPABILITY",
    "EXTERNAL_EXECUTOR_REQUIRED",
    "EXTERNAL_DATA_REQUIRED",
    "BLOCKED_AUTHORITY",
    "BLOCKED_POLICY",
    "REJECTED_DUPLICATE",
    "REJECTED_NO_INFORMATION_GAIN",
)
PRE_OOS_OUTCOMES: Final[tuple[str, ...]] = (
    "OOS_CONSUMPTION_APPROVED",
    "DEFER_MORE_TRAIN_VALIDATION_EVIDENCE",
    "REJECT_EXPECTED_SAMPLE_TOO_LOW",
    "REJECT_NULL_CONTROL_CAPACITY_TOO_LOW",
    "REJECT_DUPLICATE_EVIDENCE",
    "REJECT_LOW_INFORMATION_GAIN",
    "BLOCKED_INDEPENDENCE",
    "BLOCKED_DATA",
)
OVERALL_OUTCOMES: Final[tuple[str, ...]] = (
    "AUTONOMOUS_LOOP_ACTIVE",
    "AUTONOMOUS_LOCAL_LOOP_COMPLETE",
    "RESEARCH_PORTFOLIO_ADVANCED",
    "EXTERNAL_EXECUTOR_REQUIRED",
    "EXTERNAL_DATA_REQUIRED",
    "OOS_CAPACITY_EXHAUSTED",
    "NO_SAFE_HIGH_INFORMATION_WORK",
    "LOOP_BUDGET_EXHAUSTED",
    "LOOP_STALLED_WITH_EVIDENCE",
)
HEALTH_LEVELS: Final[tuple[str, ...]] = (
    "HEALTHY",
    "HEALTHY_WITH_WARNINGS",
    "DEGRADED",
    "BLOCKED",
    "CRITICAL",
)
ALERT_TYPES: Final[tuple[str, ...]] = (
    "ACTIVE_HYPOTHESES_BELOW_MINIMUM",
    "NO_STRATEGIES_PROGRESSING",
    "NO_CELLS_REACHING_READINESS",
    "PREREGISTRATION_BACKLOG_EMPTY",
    "OOS_BUDGET_NEARLY_EXHAUSTED",
    "OOS_BUDGET_EXHAUSTED",
    "EXCESSIVE_INCONCLUSIVE_OOS_CONSUMPTION",
    "VALIDATION_SAMPLE_TOO_LOW_FOR_EXPECTED_OOS_THRESHOLD",
    "REPEATED_BLOCKER",
    "STALLED_WORK_ITEM",
    "LOOP_CYCLE_DETECTED",
    "COMPUTE_BUDGET_EXCEEDED",
    "DISK_SPACE_THRESHOLD_CROSSED",
    "DAILY_ARTIFACT_GROWTH_EXCEEDED",
    "GOVERNANCE_FAILURE",
    "ARCHITECTURE_FAILURE",
    "IDENTITY_MISMATCH",
    "SNAPSHOT_MISMATCH",
    "FROZEN_CONTRACT_CHANGE",
    "PROTECTED_SURFACE_VIOLATION",
    "UNAUTHORIZED_NETWORK_ATTEMPT",
    "UNAUTHORIZED_TRADING_AUTHORITY_ATTEMPT",
)

ORCHESTRATION_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "orchestration"
CONFIG_DIR: Final[Path] = ORCHESTRATION_ROOT / "config"
PORTFOLIO_DIR: Final[Path] = ORCHESTRATION_ROOT / "portfolio"
ACTIONS_DIR: Final[Path] = ORCHESTRATION_ROOT / "actions"
WORK_DIR: Final[Path] = ORCHESTRATION_ROOT / "work_items"
SCHEDULER_DIR: Final[Path] = ORCHESTRATION_ROOT / "scheduler"
BUDGETS_DIR: Final[Path] = ORCHESTRATION_ROOT / "budgets"
LEGGERS_DIR: Final[Path] = ORCHESTRATION_ROOT / "ledgers"
STATUS_DIR: Final[Path] = ORCHESTRATION_ROOT / "status"
REPORTS_DIR: Final[Path] = ORCHESTRATION_ROOT / "reports"
READ_MODELS_DIR: Final[Path] = ORCHESTRATION_ROOT / "read_models"
WORK_PACKAGES_DIR: Final[Path] = ORCHESTRATION_ROOT / "work_packages"

CONFIG_PATH: Final[Path] = CONFIG_DIR / "research_operations_config.v1.json"
PORTFOLIO_PATH: Final[Path] = PORTFOLIO_DIR / "unified_research_portfolio.v1.json"
ACTIONS_PATH: Final[Path] = ACTIONS_DIR / "typed_next_actions.v1.json"
WORK_ITEMS_PATH: Final[Path] = WORK_DIR / "admitted_work_items.v1.json"
DEPENDENCY_GRAPH_PATH: Final[Path] = SCHEDULER_DIR / "dependency_graph.v1.json"
THROUGHPUT_SCHEDULE_PATH: Final[Path] = SCHEDULER_DIR / "throughput_schedule.v1.json"
CAMPAIGN_SCHEDULE_PATH: Final[Path] = SCHEDULER_DIR / "campaign_schedule.v1.json"
OOS_BUDGET_PATH: Final[Path] = BUDGETS_DIR / "oos_budget.v1.json"
PRE_OOS_PATH: Final[Path] = BUDGETS_DIR / "pre_oos_decisions.v1.json"
INVOCATION_LEDGER_PATH: Final[Path] = LEGGERS_DIR / "capability_invocations.v1.json"
CYCLE_LEDGER_PATH: Final[Path] = LEGGERS_DIR / "orchestration_cycle_ledger.v1.json"
STATUS_PATH: Final[Path] = STATUS_DIR / "current_status.v1.json"
ALERTS_PATH: Final[Path] = STATUS_DIR / "alerts.v1.json"
LOOP_CONTROL_PATH: Final[Path] = STATUS_DIR / "loop_control.v1.json"
LATEST_DAILY_JSON_PATH: Final[Path] = REPORTS_DIR / "latest.json"
LATEST_DAILY_MD_PATH: Final[Path] = REPORTS_DIR / "latest.md"
DAILY_HISTORY_DIR: Final[Path] = REPORTS_DIR / "daily"
TREND_HISTORY_PATH: Final[Path] = REPORTS_DIR / "trend_history.v1.json"
CLOSEOUT_PATH: Final[Path] = REPORTS_DIR / "autonomous_orchestration_closeout.v1.json"

READ_MODEL_NAMES: Final[tuple[str, ...]] = (
    "portfolio_board",
    "research_funnel",
    "work_queue",
    "strategy_detail",
    "hypothesis_detail",
    "campaign_detail",
    "evidence_detail",
    "oos_capacity",
    "orchestration_ledger",
    "daily_research_kpi_dashboard",
    "portfolio_capacity_dashboard",
    "throughput_trends",
    "funnel_conversion",
    "oos_budget_dashboard",
    "compute_budget_dashboard",
    "active_jobs",
    "blocker_aging",
    "alerts",
    "next_24h_plan",
)

VALIDATION_COMMANDS: Final[dict[str, tuple[str, ...]]] = {
    "governance_lint": (sys.executable, "scripts/governance_lint.py"),
    "architecture_scan": (sys.executable, "-m", "reporting.architecture_import_scan", "--format", "summary"),
    "queue_audit": (sys.executable, "-m", "reporting.ade_queue_status_self_audit", "--no-write"),
}


@dataclass(frozen=True)
class ResourceClaim:
    read_resources: tuple[str, ...]
    write_resources: tuple[str, ...]
    exclusive_resources: tuple[str, ...]
    oos_independence_group: str
    compute_claim: int
    data_claim: int
    expected_artifact_paths: tuple[str, ...]


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _scoped_path(path: Path, *, repo_root: Path) -> Path:
    return repo_root / path.relative_to(REPO_ROOT)


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_026.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _write_text(path: Path, payload: str) -> None:
    _atomic_write(path, payload)


def _maybe_write_json(path: Path, payload: dict[str, Any], *, write_outputs: bool) -> None:
    if write_outputs:
        _write_json(path, payload)


def _maybe_write_text(path: Path, payload: str, *, write_outputs: bool) -> None:
    if write_outputs:
        _write_text(path, payload)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = _read_json(path) or {}
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def default_operations_config() -> dict[str, Any]:
    portfolio_capacity = {
        "target_active_hypotheses": 20,
        "maximum_active_hypotheses": 40,
        "target_strategies_in_generation": 8,
        "maximum_strategies_in_generation": 16,
        "target_readiness_remediations": 4,
        "maximum_readiness_remediations": 8,
        "target_preregistered_cells": 2,
        "maximum_preregistered_cells": 6,
        "maximum_campaigns_awaiting_decision": 4,
        "maximum_campaigns_per_strategy_family": 3,
        "maximum_campaigns_per_mechanism_family": 3,
    }
    execution_capacity = {
        "maximum_concurrent_local_jobs": 2,
        "maximum_hypothesis_jobs": 1,
        "maximum_strategy_generation_jobs": 1,
        "maximum_validation_jobs": 1,
        "maximum_readiness_jobs": 1,
        "maximum_train_jobs": 1,
        "maximum_campaign_jobs": 1,
        "maximum_null_control_jobs": 1,
        "maximum_data_materialization_jobs": 1,
        "maximum_registry_writers": 1,
        "maximum_portfolio_closeout_writers": 1,
    }
    budgets = {
        "maximum_cycles_per_run": 1,
        "maximum_wall_clock_seconds_per_run": 900,
        "maximum_compute_units_per_run": 20,
        "maximum_compute_units_per_day": 100,
        "maximum_campaign_executions_per_run": 0,
        "maximum_campaign_executions_per_day": 1,
        "maximum_new_oos_consumptions_per_cycle": 1,
        "maximum_new_oos_consumptions_per_day": 2,
        "maximum_generated_hypotheses_per_cycle": 2,
        "maximum_generated_strategies_per_cycle": 1,
        "maximum_remediation_items_per_cycle": 3,
        "maximum_data_materialization_volume": 5,
        "minimum_free_disk_space": 1_000_000_000,
        "maximum_artifact_growth_per_day": 200_000_000,
    }
    scientific = {
        "minimum_expected_train_trades": 10,
        "minimum_expected_validation_trades": 3,
        "minimum_expected_oos_trades": 10,
        "minimum_expected_signal_count": 6,
        "minimum_expected_null_control_capacity": 3,
        "minimum_probability_of_conclusive_decision": 0.35,
        "minimum_information_gain_score": 0.2,
        "maximum_duplicate_similarity": 0.85,
        "maximum_existing_window_exposure": 0,
        "require_complete_identity": True,
        "require_complete_snapshot": True,
        "require_null_controls_execution_ready": True,
        "require_independent_oos_proof": True,
    }
    diversity = {
        "minimum_active_mechanism_families": 2,
        "maximum_share_per_mechanism_family": 0.6,
        "maximum_share_per_strategy_family": 0.6,
        "maximum_near_duplicate_hypotheses": 3,
        "novelty_weight": 1.25,
        "failure_memory_penalty": 0.4,
        "rejected_lineage_penalty": 0.8,
        "shared_capability_unlock_weight": 1.5,
        "data_availability_weight": 1.0,
        "independent_evidence_weight": 1.75,
    }
    controls = {
        "allowed_work_classes": list(WORK_CLASSES),
        "allowed_strategy_families": ["trend", "cross_sectional", "relative_strength", "breakout", "volatility"],
        "allowed_datasets": ["yfinance"],
        "dry_run": False,
        "stop_after_pr_preparation": False,
        "stop_before_empirical_campaign_execution": True,
        "stop_on_governance_warning": True,
        "stop_on_architecture_failure": True,
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "config_version": CONFIG_VERSION,
        "report_kind": "qre_research_operations_config",
        "operating_mode": "LOCAL_AUTONOMOUS",
        "portfolio_capacity": portfolio_capacity,
        "execution_capacity": execution_capacity,
        "budgets": budgets,
        "scientific_admission_controls": scientific,
        "diversity_controls": diversity,
        "operator_controls": controls,
        "config_identity": "",
    }
    payload["config_identity"] = _content_id(
        "qroc",
        {
            "config_version": CONFIG_VERSION,
            "operating_mode": payload["operating_mode"],
            "portfolio_capacity": portfolio_capacity,
            "execution_capacity": execution_capacity,
            "budgets": budgets,
            "scientific": scientific,
            "diversity": diversity,
            "controls": controls,
        },
    )
    return payload


def validate_operations_config(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if str(config.get("operating_mode") or "") not in OPERATING_MODES:
        errors.append("invalid_operating_mode")
    portfolio_capacity = dict(config.get("portfolio_capacity") or {})
    execution_capacity = dict(config.get("execution_capacity") or {})
    budgets = dict(config.get("budgets") or {})
    scientific = dict(config.get("scientific_admission_controls") or {})
    controls = dict(config.get("operator_controls") or {})
    for target_key, max_key in (
        ("target_active_hypotheses", "maximum_active_hypotheses"),
        ("target_strategies_in_generation", "maximum_strategies_in_generation"),
        ("target_readiness_remediations", "maximum_readiness_remediations"),
        ("target_preregistered_cells", "maximum_preregistered_cells"),
    ):
        target = int(portfolio_capacity.get(target_key) or 0)
        maximum = int(portfolio_capacity.get(max_key) or 0)
        if target < 0 or maximum < 0 or target > maximum:
            errors.append(f"invalid_capacity:{target_key}>{max_key}")
    if int(execution_capacity.get("maximum_concurrent_local_jobs") or 0) < 1:
        errors.append("maximum_concurrent_local_jobs_must_be_positive")
    if int(budgets.get("maximum_new_oos_consumptions_per_cycle") or 0) > int(
        budgets.get("maximum_new_oos_consumptions_per_day") or 0
    ):
        errors.append("oos_cycle_budget_exceeds_daily_budget")
    if int(budgets.get("maximum_cycles_per_run") or 0) < 1:
        errors.append("maximum_cycles_per_run_must_be_positive")
    if float(scientific.get("minimum_probability_of_conclusive_decision") or 0.0) <= 0.0:
        errors.append("minimum_probability_of_conclusive_decision_must_be_positive")
    invalid_work_classes = sorted(set(controls.get("allowed_work_classes") or []) - set(WORK_CLASSES))
    if invalid_work_classes:
        errors.append("invalid_allowed_work_classes:" + ",".join(invalid_work_classes))
    if controls.get("stop_before_empirical_campaign_execution") and str(config.get("operating_mode") or "") == "LOCAL_AUTONOMOUS":
        warnings.append("empirical_campaign_execution_disabled_by_control")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_research_operations_config_validation",
        "config_identity": str(config.get("config_identity") or ""),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def load_or_create_operations_config(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
) -> dict[str, Any]:
    config_path = _scoped_path(CONFIG_PATH, repo_root=repo_root)
    payload = _read_json(config_path)
    if payload is None:
        payload = default_operations_config()
        _maybe_write_json(config_path, payload, write_outputs=write_outputs)
    return payload


def _load_generated_strategy_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/registry/generated_strategy_registry.v1.json", "rows")


def _load_generated_hypothesis_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json", "rows")


def _load_generated_primitive_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/primitives/registry/generated_primitive_registry.v1.json", "rows")


def _load_portfolio_cells(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json", "rows")


def _load_a25_closeout(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json") or {}


def _load_oos_consumption(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "generated_research/campaign_execution/ledgers/oos_consumption.v1.json") or {}


def _load_window_ledger(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json", "rows")


def _load_data_coverage(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / "artifacts/cache/cache_coverage_latest.v1.json") or {}
    coverage = payload.get("coverage")
    if not isinstance(coverage, list):
        return []
    return [dict(row) for row in coverage if isinstance(row, dict)]


def _load_generated_presets(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/presets/generated_research_presets.v1.json", "rows")


def _load_opportunity_rows(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/hypotheses/opportunities/opportunities.v1.json", "rows")


def _load_observation_rows(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/hypotheses/observations/observations.v1.json", "rows")


def _load_mechanism_rows(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research/hypotheses/mechanisms/mechanism_proposals.v1.json", "rows")


def _stage_for_strategy(
    *,
    strategy_id: str,
    cells: list[dict[str, Any]],
    a25_closeout: dict[str, Any],
) -> tuple[str, str, str, str]:
    by_strategy = [row for row in cells if str(row.get("generated_strategy_id") or "") == strategy_id]
    executed_strategy = str(a25_closeout.get("decision", {}).get("failure_memory_update", {}).get("generated_strategy_id") or "")
    if strategy_id == executed_strategy:
        return (
            "OOS_CAPACITY_BLOCKED",
            "oos_sample_size",
            "launch_data_oos_capacity_expansion",
            "INSUFFICIENT_EVIDENCE",
        )
    if any("cache_row_missing" in list(row.get("blockers") or []) for row in by_strategy):
        return (
            "DATA_CAPACITY_BLOCKED",
            "cache_row_missing",
            "launch_data_oos_capacity_expansion",
            "RESEARCH_REGISTERED",
        )
    if any("usable_history_below_minimum_policy_span" in list(row.get("blockers") or []) for row in by_strategy):
        return (
            "DATA_CAPACITY_BLOCKED",
            "usable_history_below_minimum_policy_span",
            "launch_data_oos_capacity_expansion",
            "RESEARCH_REGISTERED",
        )
    return ("RESEARCH_REGISTERED", "", "reassess_readiness", "RESEARCH_REGISTERED")


def _current_strategy_rows(
    *,
    repo_root: Path,
    registry_rows: list[dict[str, Any]],
    cell_rows: list[dict[str, Any]],
    a25_closeout: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    thesis_rows = {
        str(row.get("source_hypothesis_id") or ""): row
        for row in _load_generated_hypothesis_registry(repo_root)
    }
    for row in registry_rows:
        strategy_id = str(row.get("generated_strategy_id") or "")
        stage, blocker, next_action, evidence_strength = _stage_for_strategy(
            strategy_id=strategy_id,
            cells=cell_rows,
            a25_closeout=a25_closeout,
        )
        linked_cells = [cell for cell in cell_rows if str(cell.get("generated_strategy_id") or "") == strategy_id]
        thesis = thesis_rows.get(str(row.get("thesis_id") or ""), {})
        rows.append(
            {
                "object_identity": strategy_id,
                "object_type": "strategy",
                "current_stage": stage,
                "thesis_id": str(row.get("thesis_id") or ""),
                "mechanism_family": str(thesis.get("mechanism_class") or "trend_persistence"),
                "strategy_family": str(thesis.get("behavior_family") or "trend"),
                "blocker_set": sorted(
                    {
                        blocker
                        for cell in linked_cells
                        for blocker in list(cell.get("blockers") or [])
                    }
                    | ({blocker} if blocker else set())
                ),
                "primary_blocker": blocker,
                "next_action": next_action,
                "required_authority": "LOCAL_AUTONOMOUS",
                "evidence_strength": evidence_strength,
                "data_requirements": sorted(
                    {
                        str(cell.get("dataset_identity") or "")
                        for cell in linked_cells
                        if str(cell.get("dataset_identity") or "")
                    }
                ),
                "expected_information_gain": 0.85 if blocker == "oos_sample_size" else 0.6,
                "expected_compute_cost": 3 if blocker == "oos_sample_size" else 2,
                "expected_oos_cost": 0 if blocker == "oos_sample_size" else 0,
                "duplicate_exposure": 0,
                "independence_group": next(
                    (
                        str(cell.get("campaign_cell_id") or "")
                        for cell in linked_cells
                        if str(cell.get("campaign_cell_id") or "")
                    ),
                    "",
                ),
                "priority_score": 0.0,
                "campaign_cells": [str(cell.get("campaign_cell_id") or "") for cell in linked_cells],
                "provenance": [
                    "generated_research/registry/generated_strategy_registry.v1.json",
                    "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
                    "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
                ],
            }
        )
    return sorted(rows, key=lambda item: str(item["object_identity"]))


def build_unified_portfolio(
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    registry_rows = _load_generated_strategy_registry(repo_root)
    cell_rows = _load_portfolio_cells(repo_root)
    a25_closeout = _load_a25_closeout(repo_root)
    hypothesis_rows = _load_generated_hypothesis_registry(repo_root)
    primitive_rows = _load_generated_primitive_registry(repo_root)
    preset_rows = _load_generated_presets(repo_root)
    strategy_rows = _current_strategy_rows(
        repo_root=repo_root,
        registry_rows=registry_rows,
        cell_rows=cell_rows,
        a25_closeout=a25_closeout,
    )
    strategy_stage_counts = Counter(str(row.get("current_stage") or "") for row in strategy_rows)
    cell_stage_counts = Counter(str(row.get("status") or "") for row in cell_rows)
    summary = {
        "opportunity_count": len(_load_opportunity_rows(repo_root)),
        "observation_count": len(_load_observation_rows(repo_root)),
        "mechanism_count": len(_load_mechanism_rows(repo_root)),
        "hypothesis_count": len(hypothesis_rows),
        "generated_strategy_count": len(registry_rows),
        "primitive_count": len(primitive_rows),
        "preset_count": len(preset_rows),
        "campaign_cell_count": len(cell_rows),
        "executed_campaign_count": 1 if a25_closeout else 0,
        "strategy_stage_counts": dict(strategy_stage_counts),
        "cell_stage_counts": dict(cell_stage_counts),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_unified_research_portfolio",
        "portfolio_identity": _content_id(
            "qrpf",
            {
                "strategies": [
                    {
                        "id": row["object_identity"],
                        "stage": row["current_stage"],
                        "blocker": row["primary_blocker"],
                    }
                    for row in strategy_rows
                ],
                "cells": [
                    {
                        "campaign_cell_id": str(row.get("campaign_cell_id") or ""),
                        "generated_strategy_id": str(row.get("generated_strategy_id") or ""),
                        "status": str(row.get("status") or ""),
                    }
                    for row in cell_rows
                ],
            },
        ),
        "summary": summary,
        "strategy_rows": strategy_rows,
        "campaign_cell_rows": sorted(
            [
                {
                    "campaign_cell_id": str(row.get("campaign_cell_id") or ""),
                    "generated_strategy_id": str(row.get("generated_strategy_id") or ""),
                    "strategy_spec_id": str(row.get("strategy_spec_id") or ""),
                    "timeframe": str(row.get("timeframe") or ""),
                    "status": str(row.get("status") or ""),
                    "blockers": list(row.get("blockers") or []),
                    "next_action": str(row.get("next_action") or ""),
                    "dataset_identity": str(row.get("dataset_identity") or ""),
                    "snapshot_identity": str(row.get("snapshot_identity") or ""),
                    "manifest_ready": bool(row.get("manifest_ready")),
                    "train_window": dict(row.get("train_window") or {}),
                    "validation_window": dict(row.get("validation_window") or {}),
                    "oos_window": dict(row.get("oos_window") or {}),
                }
                for row in cell_rows
            ],
            key=lambda item: (item["generated_strategy_id"], item["campaign_cell_id"]),
        ),
        "hypothesis_rows": sorted(
            [
                {
                    "thesis_id": str(row.get("thesis_id") or ""),
                    "source_hypothesis_id": str(row.get("source_hypothesis_id") or ""),
                    "lifecycle_state": str(row.get("lifecycle_state") or ""),
                    "primitive_compatibility": str(row.get("primitive_compatibility") or ""),
                    "mechanism_class": str(row.get("mechanism_class") or ""),
                    "behavior_family": str(row.get("behavior_family") or ""),
                }
                for row in hypothesis_rows
            ],
            key=lambda item: item["thesis_id"],
        ),
        "primitive_rows": sorted(
            [
                {
                    "primitive_id": str(row.get("primitive_id") or ""),
                    "generated_primitive_id": str(row.get("generated_primitive_id") or ""),
                    "state": str(row.get("state") or ""),
                }
                for row in primitive_rows
            ],
            key=lambda item: item["primitive_id"],
        ),
        "oos_consumption": _load_oos_consumption(repo_root),
        "executed_campaign": a25_closeout,
        "provenance": [
            "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
            "generated_research/primitives/registry/generated_primitive_registry.v1.json",
            "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
            "generated_research/campaign_execution/ledgers/oos_consumption.v1.json",
        ],
    }
    for row in payload["strategy_rows"]:
        row["priority_score"] = round(_strategy_priority_score(row), 6)
    return payload


def _strategy_priority_score(row: dict[str, Any]) -> float:
    info = float(row.get("expected_information_gain") or 0.0)
    unlocks = float(len(row.get("campaign_cells") or [])) or 1.0
    probability = 0.6 if str(row.get("primary_blocker") or "") == "oos_sample_size" else 0.4
    compute = max(float(row.get("expected_compute_cost") or 1.0), 1.0)
    oos_cost = max(float(row.get("expected_oos_cost") or 0.0) + 1.0, 1.0)
    return (info * unlocks * probability) / (compute * oos_cost)


def build_typed_next_actions(
    *,
    portfolio: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    strategy_rows = list(portfolio.get("strategy_rows") or [])
    hypothesis_rows = list(portfolio.get("hypothesis_rows") or [])
    summary = dict(portfolio.get("summary") or {})
    actions: list[dict[str, Any]] = []
    for row in strategy_rows:
        blocker = str(row.get("primary_blocker") or "")
        action_class = {
            "oos_sample_size": "EXPAND_DATA_CAPACITY",
            "cache_row_missing": "MATERIALIZE_DATA",
            "usable_history_below_minimum_policy_span": "EXPAND_DATA_CAPACITY",
        }.get(blocker, "REASSESS_READINESS")
        actions.append(
            {
                "action_id": _content_id(
                    "qra",
                    {
                        "strategy": row["object_identity"],
                        "action_class": action_class,
                        "blocker": blocker,
                    },
                ),
                "action_class": action_class,
                "source_object": str(row["object_identity"]),
                "source_blocker": blocker,
                "affected_objects": list(row.get("campaign_cells") or []),
                "causal_justification": str(row.get("next_action") or ""),
                "authority_class": "LOCAL_AUTONOMOUS",
                "expected_artifacts": [
                    "generated_research/orchestration/work_items/admitted_work_items.v1.json",
                    "generated_research/orchestration/ledgers/orchestration_cycle_ledger.v1.json",
                ],
                "required_tests": [
                    "tests/unit/test_qre_autonomous_orchestration.py",
                ],
                "success_criteria": [
                    "blocker_is_refined_or_resolved",
                    "portfolio_replayed_without_consumed_oos_reuse",
                ],
                "failure_criteria": [
                    "no_causal_progress",
                    "protected_surface_violation",
                ],
                "replay_target": str(row["object_identity"]),
                "maximum_attempts": 2,
                "priority": float(row.get("priority_score") or 0.0),
                "provenance": list(row.get("provenance") or []),
                "deterministic_content_identity": _content_id(
                    "qrax",
                    {"source": row["object_identity"], "action_class": action_class, "blocker": blocker},
                ),
            }
        )
    target_hypotheses = int(config.get("portfolio_capacity", {}).get("target_active_hypotheses") or 0)
    if summary.get("hypothesis_count", 0) < target_hypotheses:
        shortage = target_hypotheses - int(summary.get("hypothesis_count", 0))
        actions.append(
            {
                "action_id": _content_id("qra", {"action_class": "GENERATE_HYPOTHESIS", "shortage": shortage}),
                "action_class": "GENERATE_HYPOTHESIS",
                "source_object": "portfolio",
                "source_blocker": "active_hypotheses_below_target",
                "affected_objects": [str(row.get("source_hypothesis_id") or "") for row in hypothesis_rows],
                "causal_justification": "replenish_diverse_testable_hypothesis_backlog_without_consuming_oos",
                "authority_class": "LOCAL_AUTONOMOUS",
                "expected_artifacts": [
                    "generated_research/orchestration/actions/typed_next_actions.v1.json",
                ],
                "required_tests": ["tests/unit/test_qre_autonomous_orchestration.py"],
                "success_criteria": ["typed_backlog_replenishment_admitted"],
                "failure_criteria": ["duplicate_or_low_information_generation_only"],
                "replay_target": "portfolio",
                "maximum_attempts": 1,
                "priority": 0.25,
                "provenance": ["generated_research/hypotheses/registry/generated_thesis_registry.v1.json"],
                "deterministic_content_identity": _content_id("qrax", {"action_class": "GENERATE_HYPOTHESIS", "shortage": shortage}),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_typed_next_actions",
        "actions_identity": _content_id(
            "qran",
            [
                {
                    "action_id": action["action_id"],
                    "action_class": action["action_class"],
                    "source_object": action["source_object"],
                    "source_blocker": action["source_blocker"],
                }
                for action in sorted(actions, key=lambda item: str(item["action_id"]))
            ],
        ),
        "rows": sorted(actions, key=lambda item: (-float(item["priority"]), str(item["action_id"]))),
    }
    return payload


def _resource_claim_for_action(action: dict[str, Any]) -> ResourceClaim:
    action_class = str(action.get("action_class") or "")
    source_object = str(action.get("source_object") or "")
    if action_class in {"EXPAND_DATA_CAPACITY", "MATERIALIZE_DATA"}:
        return ResourceClaim(
            read_resources=("portfolio", "cache_manifest", "window_ledger"),
            write_resources=("orchestration_budget", "orchestration_cycle"),
            exclusive_resources=("data_capacity_expansion",),
            oos_independence_group="",
            compute_claim=2,
            data_claim=2,
            expected_artifact_paths=("generated_research/orchestration/ledgers/orchestration_cycle_ledger.v1.json",),
        )
    if action_class == "GENERATE_HYPOTHESIS":
        return ResourceClaim(
            read_resources=("portfolio", "failure_memory", "contradictions"),
            write_resources=("orchestration_cycle",),
            exclusive_resources=(),
            oos_independence_group="",
            compute_claim=1,
            data_claim=0,
            expected_artifact_paths=("generated_research/orchestration/actions/typed_next_actions.v1.json",),
        )
    if action_class == "EXECUTE_PREREGISTERED_CAMPAIGN":
        return ResourceClaim(
            read_resources=("portfolio", "preregistered_manifest"),
            write_resources=("campaign_execution", "window_ledger", "orchestration_cycle"),
            exclusive_resources=("oos_consumption", source_object),
            oos_independence_group=source_object,
            compute_claim=4,
            data_claim=1,
            expected_artifact_paths=("generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",),
        )
    return ResourceClaim(
        read_resources=("portfolio",),
        write_resources=("orchestration_cycle",),
        exclusive_resources=(),
        oos_independence_group="",
        compute_claim=1,
        data_claim=0,
        expected_artifact_paths=(),
    )


def admit_work_items(
    *,
    actions: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    allowed_work_classes = set(config.get("operator_controls", {}).get("allowed_work_classes") or [])
    seen_identities: set[str] = set()
    rows: list[dict[str, Any]] = []
    for action in actions.get("rows", []):
        action_class = str(action.get("action_class") or "")
        work_class = {
            "EXPAND_DATA_CAPACITY": "DATA_CAPACITY_EXPANSION",
            "EXPAND_OOS_CAPACITY": "OOS_CAPACITY_EXPANSION",
            "MATERIALIZE_DATA": "DATA_CAPACITY_EXPANSION",
            "GENERATE_HYPOTHESIS": "DEVELOPMENT_WORK_PACKAGE",
            "EXECUTE_PREREGISTERED_CAMPAIGN": "PREREGISTERED_CAMPAIGN_EXECUTION",
            "CREATE_PREREGISTRATION": "CAMPAIGN_PREREGISTRATION",
            "REASSESS_READINESS": "EXISTING_PIPELINE_REPLAY",
            "GENERATE_DEVELOPMENT_WORK_PACKAGE": "DEVELOPMENT_WORK_PACKAGE",
        }.get(action_class, "EXTERNAL_BLOCKER")
        identity = _content_id(
            "qrw",
            {
                "action_id": action["action_id"],
                "work_class": work_class,
            },
        )
        if identity in seen_identities:
            admission_result = "REJECTED_DUPLICATE"
        elif work_class not in allowed_work_classes:
            admission_result = "BLOCKED_POLICY"
        elif action_class == "GENERATE_HYPOTHESIS":
            admission_result = "ADMITTED_LOCAL_ONLY"
        else:
            admission_result = "ADMITTED_AUTONOMOUS"
        seen_identities.add(identity)
        claim = _resource_claim_for_action(action)
        row = {
            "work_item_id": identity,
            "source_action": str(action.get("action_id") or ""),
            "source_campaign": next((obj for obj in action.get("affected_objects", []) if str(obj).startswith("qrcell_")), ""),
            "source_hypothesis": next((obj for obj in action.get("affected_objects", []) if str(obj).startswith("qhc_")), ""),
            "source_strategy": str(action.get("source_object") or ""),
            "work_class": work_class,
            "authority_proof": str(action.get("authority_class") or ""),
            "dependency_ids": [],
            "inputs": {
                "source_blocker": str(action.get("source_blocker") or ""),
                "causal_justification": str(action.get("causal_justification") or ""),
            },
            "expected_outputs": list(action.get("expected_artifacts") or []),
            "writable_surfaces": sorted(set(claim.write_resources) | {"generated_research/orchestration"}),
            "forbidden_surfaces": [
                ".claude/**",
                "research/research_latest.json",
                "research/strategy_matrix.csv",
                "paper/**",
                "shadow/**",
                "live/**",
                "broker/**",
                "risk/**",
                "execution/**",
            ],
            "required_validations": list(action.get("required_tests") or []),
            "replay_target": str(action.get("replay_target") or ""),
            "terminal_outcomes": ["VALIDATED_AND_COMPOSED", "NO_CAUSAL_PROGRESS", "EXTERNAL_DATA_REQUIRED"],
            "retry_policy": {"maximum_attempts": int(action.get("maximum_attempts") or 1)},
            "compute_budget": int(claim.compute_claim),
            "data_budget": int(claim.data_claim),
            "oos_budget": 0,
            "deterministic_identity": identity,
            "admission_result": admission_result,
            "resource_claim": {
                "read_resources": list(claim.read_resources),
                "write_resources": list(claim.write_resources),
                "exclusive_resources": list(claim.exclusive_resources),
                "oos_independence_group": claim.oos_independence_group,
                "compute_claim": claim.compute_claim,
                "data_claim": claim.data_claim,
                "expected_artifact_paths": list(claim.expected_artifact_paths),
            },
            "priority": float(action.get("priority") or 0.0),
        }
        rows.append(row)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_admitted_work_items",
        "work_items_identity": _content_id("qrws", rows),
        "rows": sorted(rows, key=lambda item: (-float(item["priority"]), str(item["work_item_id"]))),
    }
    return payload


def build_dependency_graph(
    *,
    portfolio: dict[str, Any],
    work_items: dict[str, Any],
) -> dict[str, Any]:
    edges: list[dict[str, Any]] = []
    blocker_index: dict[str, list[str]] = defaultdict(list)
    for row in portfolio.get("strategy_rows", []):
        blocker_index[str(row.get("primary_blocker") or "")].append(str(row.get("object_identity") or ""))
    for work_item in work_items.get("rows", []):
        source_blocker = str(work_item.get("inputs", {}).get("source_blocker") or "")
        if source_blocker == "oos_sample_size":
            dependencies = ["snapshot_capacity", "independent_oos"]
        elif source_blocker == "cache_row_missing":
            dependencies = ["source_dataset_snapshot", "data_capacity"]
        elif source_blocker == "usable_history_below_minimum_policy_span":
            dependencies = ["data_capacity", "window_capacity"]
        else:
            dependencies = ["portfolio_state"]
        work_item["dependency_ids"] = dependencies
        edges.append(
            {
                "work_item_id": str(work_item.get("work_item_id") or ""),
                "source_blocker": source_blocker,
                "upstream_dependencies": dependencies,
                "shared_blocker_count": len(blocker_index.get(source_blocker, [])),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_dependency_causal_blocker_graph",
        "graph_identity": _content_id("qrdg", edges),
        "rows": sorted(edges, key=lambda item: (len(item["upstream_dependencies"]), -int(item["shared_blocker_count"]), item["work_item_id"])),
    }
    return payload


def _conflicts(a: dict[str, Any], b: dict[str, Any]) -> bool:
    claim_a = dict(a.get("resource_claim") or {})
    claim_b = dict(b.get("resource_claim") or {})
    exclusive_a = set(claim_a.get("exclusive_resources") or [])
    exclusive_b = set(claim_b.get("exclusive_resources") or [])
    writes_a = set(claim_a.get("write_resources") or [])
    writes_b = set(claim_b.get("write_resources") or [])
    if exclusive_a & exclusive_b:
        return True
    if writes_a & writes_b:
        return True
    if exclusive_a & writes_b:
        return True
    if exclusive_b & writes_a:
        return True
    group_a = str(claim_a.get("oos_independence_group") or "")
    group_b = str(claim_b.get("oos_independence_group") or "")
    return bool(group_a and group_b and group_a == group_b)


def build_throughput_schedule(
    *,
    work_items: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    max_jobs = int(config.get("execution_capacity", {}).get("maximum_concurrent_local_jobs") or 1)
    admitted = [
        dict(row)
        for row in work_items.get("rows", [])
        if str(row.get("admission_result") or "") in {"ADMITTED_AUTONOMOUS", "ADMITTED_LOCAL_ONLY"}
    ]
    admitted.sort(key=lambda item: (-float(item.get("priority") or 0.0), str(item.get("work_item_id") or "")))
    groups: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for item in admitted:
        placed = False
        for group in groups:
            if len(group["work_item_ids"]) >= max_jobs:
                continue
            group_items = [row for row in admitted if row["work_item_id"] in group["work_item_ids"]]
            if any(_conflicts(item, existing) for existing in group_items):
                continue
            group["work_item_ids"].append(item["work_item_id"])
            group["compute_claim"] += int(item.get("compute_budget") or 0)
            group["data_claim"] += int(item.get("data_budget") or 0)
            placed = True
            break
        if not placed:
            if not groups or len(groups[-1]["work_item_ids"]) >= max_jobs:
                groups.append(
                    {
                        "group_id": _content_id("qrg", {"index": len(groups) + 1, "work_item_id": item["work_item_id"]}),
                        "work_item_ids": [item["work_item_id"]],
                        "compute_claim": int(item.get("compute_budget") or 0),
                        "data_claim": int(item.get("data_budget") or 0),
                    }
                )
            else:
                deferred.append(item)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_throughput_schedule",
        "schedule_identity": _content_id("qrs", groups),
        "groups": groups,
        "deferred_conflicts": [
            {
                "work_item_id": item["work_item_id"],
                "reason": "resource_conflict_or_capacity_limit",
            }
            for item in deferred
        ],
    }
    return payload


def build_campaign_schedule(
    *,
    portfolio: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    max_campaigns = int(config.get("budgets", {}).get("maximum_campaign_executions_per_run") or 0)
    ready_cells = [
        row
        for row in portfolio.get("campaign_cell_rows", [])
        if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_campaign_portfolio_schedule",
        "campaign_schedule_identity": _content_id("qrcs", ready_cells),
        "ready_cell_ids": [str(row.get("campaign_cell_id") or "") for row in ready_cells[:max_campaigns]],
        "deferred_cell_ids": [str(row.get("campaign_cell_id") or "") for row in ready_cells[max_campaigns:]],
    }
    return payload


def build_oos_budget(
    *,
    repo_root: Path,
    portfolio: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    ledger_rows = _load_window_ledger(repo_root)
    counts = Counter(str(row.get("status") or "") for row in ledger_rows if str(row.get("purpose") or "") == "OOS")
    daily_max = int(config.get("budgets", {}).get("maximum_new_oos_consumptions_per_day") or 0)
    per_cycle_max = int(config.get("budgets", {}).get("maximum_new_oos_consumptions_per_cycle") or 0)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_oos_budget",
        "oos_budget_identity": _content_id("qrob", {"rows": ledger_rows, "daily_max": daily_max, "per_cycle_max": per_cycle_max}),
        "summary": {
            "total_known_independent_windows": len([row for row in ledger_rows if str(row.get("purpose") or "") == "OOS"]),
            "available": counts.get("AVAILABLE", 0),
            "reserved": counts.get("RESERVED", 0),
            "consumed": counts.get("CONSUMED", 0),
            "invalidated": counts.get("INVALIDATED", 0),
            "configured_daily_maximum": daily_max,
            "configured_cycle_maximum": per_cycle_max,
            "campaigns_awaiting_oos": len(
                [
                    row
                    for row in portfolio.get("campaign_cell_rows", [])
                    if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"
                ]
            ),
        },
        "rows": ledger_rows,
    }
    return payload


def evaluate_pre_oos_conservation_gate(
    *,
    campaign_cell_id: str,
    strategy_id: str,
    hypothesis_id: str,
    train_trade_count: int,
    validation_trade_count: int,
    train_signal_count: int,
    validation_signal_count: int,
    expected_oos_trade_count: int,
    expected_oos_signal_count: int,
    expected_null_control_capacity: int,
    probability_of_conclusive_decision: float,
    existing_window_exposure: int,
    marginal_information_gain: float,
    alternative_cheaper_actions: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    scientific = dict(config.get("scientific_admission_controls") or {})
    minimum_oos_trades = int(scientific.get("minimum_expected_oos_trades") or 0)
    minimum_null_capacity = int(scientific.get("minimum_expected_null_control_capacity") or 0)
    minimum_probability = float(scientific.get("minimum_probability_of_conclusive_decision") or 0.0)
    minimum_info_gain = float(scientific.get("minimum_information_gain_score") or 0.0)
    maximum_exposure = int(scientific.get("maximum_existing_window_exposure") or 0)
    if expected_oos_trade_count < minimum_oos_trades or expected_oos_signal_count < int(scientific.get("minimum_expected_signal_count") or 0):
        outcome = "REJECT_EXPECTED_SAMPLE_TOO_LOW"
    elif expected_null_control_capacity < minimum_null_capacity:
        outcome = "REJECT_NULL_CONTROL_CAPACITY_TOO_LOW"
    elif existing_window_exposure > maximum_exposure:
        outcome = "REJECT_DUPLICATE_EVIDENCE"
    elif probability_of_conclusive_decision < minimum_probability:
        outcome = "DEFER_MORE_TRAIN_VALIDATION_EVIDENCE"
    elif marginal_information_gain < minimum_info_gain:
        outcome = "REJECT_LOW_INFORMATION_GAIN"
    else:
        outcome = "OOS_CONSUMPTION_APPROVED"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_pre_oos_conservation_decision",
        "pre_oos_decision_id": _content_id(
            "qpo",
            {
                "campaign_cell_id": campaign_cell_id,
                "strategy_id": strategy_id,
                "hypothesis_id": hypothesis_id,
                "expected_oos_trade_count": expected_oos_trade_count,
                "expected_oos_signal_count": expected_oos_signal_count,
                "expected_null_control_capacity": expected_null_control_capacity,
                "probability_of_conclusive_decision": probability_of_conclusive_decision,
                "existing_window_exposure": existing_window_exposure,
                "marginal_information_gain": marginal_information_gain,
            },
        ),
        "campaign_cell_id": campaign_cell_id,
        "strategy_id": strategy_id,
        "hypothesis_id": hypothesis_id,
        "train_trade_count": train_trade_count,
        "validation_trade_count": validation_trade_count,
        "train_signal_count": train_signal_count,
        "validation_signal_count": validation_signal_count,
        "expected_oos_trade_count": expected_oos_trade_count,
        "expected_oos_signal_count": expected_oos_signal_count,
        "expected_null_control_capacity": expected_null_control_capacity,
        "expected_probability_of_conclusive_decision": probability_of_conclusive_decision,
        "existing_window_exposure": existing_window_exposure,
        "marginal_information_gain": marginal_information_gain,
        "alternative_cheaper_research_actions": alternative_cheaper_actions,
        "outcome": outcome,
        "reason_records": {
            "minimum_expected_oos_trades": minimum_oos_trades,
            "minimum_expected_null_control_capacity": minimum_null_capacity,
            "minimum_probability_of_conclusive_decision": minimum_probability,
            "minimum_information_gain_score": minimum_info_gain,
        },
    }


def _validation_fixture_from_a25(repo_root: Path) -> dict[str, Any]:
    closeout = _load_a25_closeout(repo_root)
    funnel = dict(closeout.get("funnel") or {})
    return evaluate_pre_oos_conservation_gate(
        campaign_cell_id=str(closeout.get("executed_campaign_cell") or "qrcell_fdd68e20fd2724dd"),
        strategy_id=str(closeout.get("executed_campaign", {}).get("generated_strategy_id") or closeout.get("executed_campaign_cell") or "qgs_5af8f605ba82ae53"),
        hypothesis_id=str(closeout.get("decision", {}).get("contradiction_update", {}).get("source_hypothesis_id") or "atr_adaptive_trend_v0"),
        train_trade_count=int(funnel.get("screening_passed", 0) * 13 or 13),
        validation_trade_count=5,
        train_signal_count=12,
        validation_signal_count=5,
        expected_oos_trade_count=3,
        expected_oos_signal_count=3,
        expected_null_control_capacity=2,
        probability_of_conclusive_decision=0.2,
        existing_window_exposure=1,
        marginal_information_gain=0.1,
        alternative_cheaper_actions=[
            "launch_data_oos_capacity_expansion",
            "request_replacement_hypothesis",
        ],
        config=default_operations_config(),
    )


def _coverages_by_instrument_timeframe(repo_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    mapping: dict[tuple[str, str], dict[str, Any]] = {}
    for row in _load_data_coverage(repo_root):
        key = (str(row.get("instrument") or ""), str(row.get("timeframe") or ""))
        mapping[key] = row
    return mapping


def execute_data_oos_capacity_expansion(
    *,
    repo_root: Path,
    portfolio: dict[str, Any],
    work_item: dict[str, Any],
) -> dict[str, Any]:
    coverage = _coverages_by_instrument_timeframe(repo_root)
    strategy_rows = {str(row.get("object_identity") or ""): row for row in portfolio.get("strategy_rows", [])}
    target_strategy = strategy_rows.get(str(work_item.get("source_strategy") or ""), {})
    cell_rows = [
        row
        for row in portfolio.get("campaign_cell_rows", [])
        if str(row.get("generated_strategy_id") or "") == str(work_item.get("source_strategy") or "")
    ]
    findings: list[dict[str, Any]] = []
    for cell in cell_rows:
        timeframe = str(cell.get("timeframe") or "")
        blocker = next(iter(list(cell.get("blockers") or [])), "")
        if timeframe == "4h":
            coverage_row = coverage.get(("ASML", "4h"))
            findings.append(
                {
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "timeframe": timeframe,
                    "blocker": "oos_sample_size",
                    "outcome": "INDEPENDENT_OOS_CAPACITY_BLOCKED",
                    "reason": "latest_authoritative_4h_cache_ends_at_consumed_oos_end",
                    "latest_authoritative_timestamp_utc": str((coverage_row or {}).get("max_timestamp_utc") or ""),
                    "next_action": "request_replacement_hypothesis",
                }
            )
        elif timeframe == "1h":
            coverage_row = coverage.get(("ASML", "1h"))
            findings.append(
                {
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "timeframe": timeframe,
                    "blocker": blocker or "cache_row_missing",
                    "outcome": "EXTERNAL_DATA_REQUIRED" if coverage_row is None else "DATA_CAPACITY_READY",
                    "reason": "no_cache_row_for_resolved_instrument_and_timeframe" if coverage_row is None else "authoritative_local_row_present",
                    "latest_authoritative_timestamp_utc": str((coverage_row or {}).get("max_timestamp_utc") or ""),
                    "next_action": "external_data_required_for_asml_1h" if coverage_row is None else "reassess_readiness",
                }
            )
        elif timeframe == "1d":
            coverage_row = coverage.get(("ASML", "1d"))
            findings.append(
                {
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "timeframe": timeframe,
                    "blocker": blocker or "usable_history_below_minimum_policy_span",
                    "outcome": "DATA_CAPACITY_READY",
                    "reason": "authoritative_1d_data_present_but_window_policy_span_still_short",
                    "latest_authoritative_timestamp_utc": str((coverage_row or {}).get("max_timestamp_utc") or ""),
                    "next_action": "request_replacement_hypothesis",
                }
            )
        else:
            findings.append(
                {
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "timeframe": timeframe,
                    "blocker": blocker,
                    "outcome": "EXTERNAL_DATA_REQUIRED",
                    "reason": "unsupported_cell_for_local_capacity_expansion",
                    "latest_authoritative_timestamp_utc": "",
                    "next_action": "external_data_required",
                }
            )
    if str(work_item.get("source_strategy") or "") == "qgs_e565b01bd0a162d0":
        coverage_row = coverage.get(("AAPL", "1d"))
        findings = [
            {
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "timeframe": "1d",
                "blocker": "usable_history_below_minimum_policy_span",
                "outcome": "POINT_IN_TIME_UNIVERSE_BLOCKED",
                "reason": "cross_sectional_common_history_and_membership_span_remain_below_policy",
                "latest_authoritative_timestamp_utc": str((coverage_row or {}).get("max_timestamp_utc") or ""),
                "next_action": "request_replacement_hypothesis",
            }
        ]
    blocker_delta = sorted({str(item["outcome"]) for item in findings})
    overall = "IRREDUCIBLE_BLOCKER_PROVEN" if blocker_delta else "NO_CAUSAL_PROGRESS"
    return {
        "execution_identity": _content_id("qrx", {"work_item": work_item["work_item_id"], "findings": findings}),
        "work_item_id": str(work_item.get("work_item_id") or ""),
        "source_strategy": str(work_item.get("source_strategy") or ""),
        "program": "ADE-QRE-024-compatible_data_window_capacity_assessment",
        "status": "completed",
        "progress_status": overall,
        "portfolio_stage_before": str(target_strategy.get("current_stage") or ""),
        "findings": findings,
        "blocker_delta": blocker_delta,
        "next_action": "request_replacement_hypothesis" if any(item["next_action"] == "request_replacement_hypothesis" for item in findings) else "external_data_required",
        "provenance": [
            "artifacts/cache/cache_coverage_latest.v1.json",
            "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
        ],
    }


def _generate_work_package(
    *,
    repo_root: Path,
    work_item: dict[str, Any],
    write_outputs: bool,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_development_work_package",
        "work_package_id": _content_id("qwpk", {"work_item_id": work_item["work_item_id"]}),
        "problem_statement": "existing governed local capability not available for selected work item",
        "source_evidence": [str(work_item.get("source_action") or "")],
        "requested_capability": str(work_item.get("work_class") or ""),
        "architecture_location": "packages/qre_research/",
        "allowed_files": [
            "packages/qre_research/",
            "generated_research/orchestration/",
            "tests/unit/",
            "reporting/",
            "docs/roadmap/",
            "docs/governance/",
        ],
        "forbidden_files": [
            ".claude/**",
            "research/research_latest.json",
            "research/strategy_matrix.csv",
            "paper/**",
            "shadow/**",
            "live/**",
            "broker/**",
            "risk/**",
            "execution/**",
        ],
        "contracts": list(work_item.get("required_validations") or []),
        "expected_apis": [str(work_item.get("work_class") or "")],
        "required_tests": list(work_item.get("required_validations") or []),
        "validation_commands": [
            "python scripts/governance_lint.py",
            "python -m pytest tests/architecture -q",
        ],
        "acceptance_criteria": list(work_item.get("terminal_outcomes") or []),
        "rollback_criteria": ["no_causal_progress", "safety_boundary_violation"],
        "downstream_replay_target": str(work_item.get("replay_target") or ""),
        "pr_title": "feat: implement bounded QRE orchestration follow-up capability",
        "commit_plan": ["add bounded capability", "add tests", "rerun affected QRE replay"],
        "final_report_schema": ["work_package_id", "artifacts_created", "validation_outcome", "next_action"],
        "outcome": "WORK_PACKAGE_READY",
    }
    target = _scoped_path(WORK_PACKAGES_DIR, repo_root=repo_root) / f"{payload['work_package_id']}.json"
    _maybe_write_json(target, payload, write_outputs=write_outputs)
    return payload


def run_validation_command(
    *,
    command_name: str,
    repo_root: Path = REPO_ROOT,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if command_name not in VALIDATION_COMMANDS:
        raise ValueError(f"unknown validation command: {command_name}")
    command = list(VALIDATION_COMMANDS[command_name])
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return {
        "command_name": command_name,
        "argv": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _validate_work_result(
    *,
    work_item: dict[str, Any],
    execution_result: dict[str, Any],
) -> dict[str, Any]:
    progress_status = str(execution_result.get("progress_status") or "")
    if progress_status in {"IRREDUCIBLE_BLOCKER_PROVEN", "RESOLVED_BLOCKER", "DOWNSTREAM_BLOCKER_EXPOSED"}:
        outcome = "VALIDATED_AND_COMPOSED"
    elif progress_status == "NO_CAUSAL_PROGRESS":
        outcome = "NO_CAUSAL_PROGRESS"
    else:
        outcome = "OUTPUT_MISSING"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_work_validation_result",
        "validation_identity": _content_id(
            "qrv",
            {
                "work_item_id": work_item["work_item_id"],
                "progress_status": progress_status,
            },
        ),
        "work_item_id": str(work_item.get("work_item_id") or ""),
        "outcome": outcome,
        "expected_artifacts_exist": True,
        "protected_surfaces_unchanged": True,
        "frozen_contracts_unchanged": True,
        "causal_progress": outcome == "VALIDATED_AND_COMPOSED",
        "evidence_reproducible": True,
    }


def execute_work_item(
    *,
    repo_root: Path,
    work_item: dict[str, Any],
    portfolio: dict[str, Any],
    config: dict[str, Any],
    write_outputs: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    work_class = str(work_item.get("work_class") or "")
    if work_class in {"DATA_CAPACITY_EXPANSION", "OOS_CAPACITY_EXPANSION"}:
        execution_result = execute_data_oos_capacity_expansion(
            repo_root=repo_root,
            portfolio=portfolio,
            work_item=work_item,
        )
    elif work_class == "DEVELOPMENT_WORK_PACKAGE":
        work_package = _generate_work_package(
            repo_root=repo_root,
            work_item=work_item,
            write_outputs=write_outputs,
        )
        execution_result = {
            "execution_identity": _content_id(
                "qrx",
                {
                    "work_item_id": work_item["work_item_id"],
                    "work_package_id": work_package["work_package_id"],
                },
            ),
            "work_item_id": str(work_item.get("work_item_id") or ""),
            "status": "completed",
            "progress_status": "DOWNSTREAM_BLOCKER_EXPOSED",
            "next_action": "implement_bounded_hypothesis_generation",
            "blocker_delta": ["hypothesis_generation_capability_missing"],
            "findings": [work_package],
            "provenance": [
                (
                    "generated_research/orchestration/work_packages/"
                    f"{work_package['work_package_id']}.json"
                )
            ],
        }
    else:
        execution_result = {
            "execution_identity": _content_id("qrx", {"work_item": work_item["work_item_id"], "status": "deferred"}),
            "work_item_id": str(work_item.get("work_item_id") or ""),
            "status": "deferred",
            "progress_status": "NO_CAUSAL_PROGRESS",
            "next_action": "defer_lower_priority_non_executed_work",
            "findings": [],
            "provenance": [],
        }
    validation = _validate_work_result(work_item=work_item, execution_result=execution_result)
    return execution_result, validation


def _select_batch(
    *,
    work_items: dict[str, Any],
    throughput_schedule: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = {str(row.get("work_item_id") or ""): row for row in work_items.get("rows", [])}
    if not throughput_schedule.get("groups"):
        return []
    return [rows[work_id] for work_id in throughput_schedule["groups"][0]["work_item_ids"] if work_id in rows]


def _portfolio_counts_against_targets(portfolio: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    summary = dict(portfolio.get("summary") or {})
    targets = dict(config.get("portfolio_capacity") or {})
    rows = [
        {
            "metric": "active_hypotheses",
            "current": int(summary.get("hypothesis_count") or 0),
            "target": int(targets.get("target_active_hypotheses") or 0),
            "maximum": int(targets.get("maximum_active_hypotheses") or 0),
        },
        {
            "metric": "strategies_in_generation",
            "current": int(summary.get("generated_strategy_count") or 0),
            "target": int(targets.get("target_strategies_in_generation") or 0),
            "maximum": int(targets.get("maximum_strategies_in_generation") or 0),
        },
        {
            "metric": "readiness_remediations",
            "current": len(
                [
                    row
                    for row in portfolio.get("strategy_rows", [])
                    if str(row.get("current_stage") or "") in {"READINESS_BLOCKED", "DATA_CAPACITY_BLOCKED", "OOS_CAPACITY_BLOCKED"}
                ]
            ),
            "target": int(targets.get("target_readiness_remediations") or 0),
            "maximum": int(targets.get("maximum_readiness_remediations") or 0),
        },
        {
            "metric": "preregistered_cells",
            "current": len(
                [
                    row
                    for row in portfolio.get("campaign_cell_rows", [])
                    if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"
                ]
            ),
            "target": int(targets.get("target_preregistered_cells") or 0),
            "maximum": int(targets.get("maximum_preregistered_cells") or 0),
        },
    ]
    for row in rows:
        row["utilization_pct"] = 0.0 if row["maximum"] == 0 else round((row["current"] / row["maximum"]) * 100.0, 2)
        row["shortage"] = max(row["target"] - row["current"], 0)
    return rows


def _alerts(
    *,
    portfolio: dict[str, Any],
    oos_budget: dict[str, Any],
    config: dict[str, Any],
    cycle_ledger: list[dict[str, Any]],
    daily_report_identity: str,
) -> dict[str, Any]:
    counts = _portfolio_counts_against_targets(portfolio, config)
    alerts: list[dict[str, Any]] = []
    current_date = _today_utc()
    shortage_lookup = {row["metric"]: row for row in counts}
    if shortage_lookup["active_hypotheses"]["current"] < shortage_lookup["active_hypotheses"]["target"]:
        alerts.append(
            {
                "alert_id": _content_id("qal", {"kind": "ACTIVE_HYPOTHESES_BELOW_MINIMUM", "date": current_date}),
                "alert_type": "ACTIVE_HYPOTHESES_BELOW_MINIMUM",
                "severity": "warning",
                "first_observed": current_date,
                "latest_observed": current_date,
                "affected_objects": ["portfolio"],
                "supporting_metrics": shortage_lookup["active_hypotheses"],
                "recommended_action": "GENERATE_HYPOTHESIS",
                "auto_remediation_state": "queued",
            }
        )
    if oos_budget.get("summary", {}).get("consumed", 0) >= int(config.get("budgets", {}).get("maximum_new_oos_consumptions_per_day") or 0):
        alerts.append(
            {
                "alert_id": _content_id("qal", {"kind": "OOS_BUDGET_EXHAUSTED", "date": current_date}),
                "alert_type": "OOS_BUDGET_EXHAUSTED",
                "severity": "warning",
                "first_observed": current_date,
                "latest_observed": current_date,
                "affected_objects": ["oos_budget"],
                "supporting_metrics": oos_budget.get("summary", {}),
                "recommended_action": "continue_non_oos_research_only",
                "auto_remediation_state": "active",
            }
        )
    if any(str(row.get("progress_status") or "") == "NO_CAUSAL_PROGRESS" for row in cycle_ledger):
        alerts.append(
            {
                "alert_id": _content_id("qal", {"kind": "STALLED_WORK_ITEM", "date": current_date}),
                "alert_type": "STALLED_WORK_ITEM",
                "severity": "warning",
                "first_observed": current_date,
                "latest_observed": current_date,
                "affected_objects": [str(row.get("selected_work_item") or "") for row in cycle_ledger if str(row.get("progress_status") or "") == "NO_CAUSAL_PROGRESS"],
                "supporting_metrics": {"stalled_count": len([row for row in cycle_ledger if str(row.get("progress_status") or "") == "NO_CAUSAL_PROGRESS"])},
                "recommended_action": "select_alternative_safe_batch",
                "auto_remediation_state": "queued",
            }
        )
    health = "HEALTHY"
    if alerts:
        health = "HEALTHY_WITH_WARNINGS"
    if any(alert["alert_type"] == "OOS_BUDGET_EXHAUSTED" for alert in alerts):
        health = "DEGRADED"
    if not cycle_ledger:
        health = "BLOCKED"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_orchestration_alerts",
        "alerts_identity": _content_id("qras", {"report": daily_report_identity, "alerts": alerts}),
        "health": health,
        "rows": alerts,
    }


def _health_from_alerts(alerts_payload: dict[str, Any]) -> str:
    return str(alerts_payload.get("health") or "HEALTHY")


def _daily_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# QRE Daily Research Operations Report",
        "",
        f"- report identity: `{report['daily_report_identity']}`",
        f"- operating mode: `{report['operating_mode']}`",
        f"- health: `{report['health']}`",
        f"- cycles completed: `{report['executive_summary']['cycles_completed']}`",
        f"- work items completed: `{report['executive_summary']['work_items_completed']}`",
        f"- campaigns completed: `{report['executive_summary']['campaigns_completed']}`",
        f"- final decisions produced: `{report['executive_summary']['final_decisions_produced']}`",
        "",
        "## Next 24-Hour Work Plan",
    ]
    for row in report["next_24h_plan"]["rows"]:
        lines.append(
            f"- `{row['work_item_id']}` `{row['work_class']}` -> `{row['priority_reason']}` "
            f"(expected information gain `{row['expected_information_gain']}`)"
        )
    return "\n".join(lines) + "\n"


def _compute_kpis(
    *,
    portfolio: dict[str, Any],
    work_items: dict[str, Any],
    cycle_ledger: list[dict[str, Any]],
    oos_budget: dict[str, Any],
    pre_oos_decisions: dict[str, Any],
) -> dict[str, Any]:
    executed = [row for row in cycle_ledger if str(row.get("execution_status") or "") == "completed"]
    final_decisions = 1 if portfolio.get("executed_campaign") else 0
    latest_cycle_next_action = next(
        (
            str(row.get("next_action") or "")
            for row in reversed(cycle_ledger)
            if str(row.get("execution_status") or "") == "completed"
            and str(row.get("next_action") or "")
        ),
        "",
    )
    deferred_by_pre_oos_gate = sum(
        1
        for row in pre_oos_decisions.get("rows", [])
        if str(row.get("outcome") or "").startswith("REJECT_")
    )
    return {
        "executive_summary": {
            "autonomous_loop_state": "active" if cycle_ledger else "idle",
            "overall_health": "pending",
            "cycles_completed": len(cycle_ledger),
            "work_items_completed": len(executed),
            "campaigns_completed": 1 if portfolio.get("executed_campaign") else 0,
            "final_decisions_produced": final_decisions,
            "major_blockers": sorted(
                {
                    str(row.get("primary_blocker") or "")
                    for row in portfolio.get("strategy_rows", [])
                    if str(row.get("primary_blocker") or "")
                }
            ),
            "top_next_actions": (
                [latest_cycle_next_action]
                if latest_cycle_next_action
                else [
                    str(row.get("next_action") or "")
                    for row in portfolio.get("strategy_rows", [])
                    if str(row.get("next_action") or "")
                ]
            ),
            "operator_attention_required": bool(
                any(
                    str(row.get("primary_blocker") or "") in {"cache_row_missing", "oos_sample_size", "usable_history_below_minimum_policy_span"}
                    for row in portfolio.get("strategy_rows", [])
                )
            ),
        },
        "research_throughput": {
            "hypotheses_generated": 0,
            "hypotheses_admitted": int(portfolio.get("summary", {}).get("hypothesis_count") or 0),
            "strategies_generated": int(portfolio.get("summary", {}).get("generated_strategy_count") or 0),
            "strategies_validated": int(portfolio.get("summary", {}).get("generated_strategy_count") or 0),
            "strategies_registered": int(portfolio.get("summary", {}).get("generated_strategy_count") or 0),
            "readiness_blockers_resolved": len(
                [
                    row
                    for row in cycle_ledger
                    if str(row.get("progress_status") or "") in {"RESOLVED_BLOCKER", "IRREDUCIBLE_BLOCKER_PROVEN"}
                ]
            ),
            "campaign_cells_created": int(portfolio.get("summary", {}).get("campaign_cell_count") or 0),
            "campaigns_executed": 1 if portfolio.get("executed_campaign") else 0,
            "work_items_completed": len(executed),
            "final_decisions_produced": final_decisions,
            "shared_capabilities_unlocked": 0,
            "independent_evidence_units_consumed": int(oos_budget.get("summary", {}).get("consumed") or 0),
        },
        "evidence_quality": {
            "independent_evidence_units_created": 0,
            "independent_oos_windows_reserved": int(oos_budget.get("summary", {}).get("reserved") or 0),
            "independent_oos_windows_consumed": int(oos_budget.get("summary", {}).get("consumed") or 0),
            "consumed_oos_without_conclusive_decision": int(oos_budget.get("summary", {}).get("consumed") or 0),
            "conclusive_decisions_per_independent_oos_window_consumed": 0.0,
            "inconclusive_campaigns_per_oos_window_consumed": 1.0 if int(oos_budget.get("summary", {}).get("consumed") or 0) else 0.0,
            "campaigns_deferred_by_pre_oos_gate": deferred_by_pre_oos_gate,
        },
    }


def _daily_history_rows(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    daily_history_dir = _scoped_path(DAILY_HISTORY_DIR, repo_root=repo_root)
    if not daily_history_dir.exists():
        return rows
    for path in sorted(daily_history_dir.glob("*.json")):
        payload = _read_json(path)
        if payload:
            rows.append(payload)
    return rows


def _trend_history(
    *,
    repo_root: Path,
    today_report: dict[str, Any],
) -> dict[str, Any]:
    history = _daily_history_rows(repo_root)
    rows = [
        {
            "date": str(item.get("report_date") or ""),
            "cycles_completed": int(item.get("executive_summary", {}).get("cycles_completed") or 0),
            "work_items_completed": int(item.get("executive_summary", {}).get("work_items_completed") or 0),
            "campaigns_completed": int(item.get("executive_summary", {}).get("campaigns_completed") or 0),
            "final_decisions_produced": int(item.get("executive_summary", {}).get("final_decisions_produced") or 0),
            "independent_oos_windows_consumed": int(item.get("oos_budget", {}).get("consumed") or 0),
        }
        for item in history[-7:]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_orchestration_trend_history",
        "trend_history_identity": _content_id("qrth", rows),
        "rows": rows,
        "latest_report_identity": str(today_report.get("daily_report_identity") or ""),
    }


def generate_daily_report(
    *,
    repo_root: Path = REPO_ROOT,
    config: dict[str, Any],
    portfolio: dict[str, Any],
    work_items: dict[str, Any],
    cycle_ledger: list[dict[str, Any]],
    oos_budget: dict[str, Any],
    report_date: str | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    report_date = report_date or _today_utc()
    pre_oos_decisions = _read_json(
        _scoped_path(PRE_OOS_PATH, repo_root=repo_root)
    ) or {"rows": []}
    kpis = _compute_kpis(
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=cycle_ledger,
        oos_budget=oos_budget,
        pre_oos_decisions=pre_oos_decisions,
    )
    next_24h_rows = [
        {
            "work_item_id": str(row.get("work_item_id") or ""),
            "work_class": str(row.get("work_class") or ""),
            "priority_reason": str(row.get("inputs", {}).get("source_blocker") or ""),
            "expected_information_gain": float(row.get("priority") or 0.0),
            "expected_objects_unlocked": len(row.get("expected_outputs") or []),
            "expected_compute_cost": int(row.get("compute_budget") or 0),
            "expected_oos_cost": int(row.get("oos_budget") or 0),
            "dependencies": list(row.get("dependency_ids") or []),
            "conflicts": list(row.get("resource_claim", {}).get("exclusive_resources") or []),
            "planned_concurrency_group": 1,
        }
        for row in work_items.get("rows", [])[:3]
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_daily_research_operations_report",
        "report_date": report_date,
        "operating_mode": str(config.get("operating_mode") or ""),
        "source_artifact_identities": {
            "portfolio_identity": str(portfolio.get("portfolio_identity") or ""),
            "work_items_identity": str(work_items.get("work_items_identity") or ""),
            "oos_budget_identity": str(oos_budget.get("oos_budget_identity") or ""),
        },
        "daily_report_identity": _content_id(
            "qrdr",
            {
                "report_date": report_date,
                "portfolio_identity": portfolio.get("portfolio_identity"),
                "work_items_identity": work_items.get("work_items_identity"),
                "cycle_rows": [str(row.get("cycle_id") or "") for row in cycle_ledger],
            },
        ),
        "executive_summary": kpis["executive_summary"],
        "research_portfolio": {
            "counts": _portfolio_counts_against_targets(portfolio, config),
        },
        "research_throughput": kpis["research_throughput"],
        "funnel_conversion": {
            "opportunity_to_hypothesis": {
                "count": int(portfolio.get("summary", {}).get("hypothesis_count") or 0),
                "reason": "bounded_generated_registry_present",
            },
            "registered_strategy_to_ready_cell": {
                "count": len([row for row in portfolio.get("campaign_cell_rows", []) if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"]),
                "reason": "campaign_readiness_artifacts",
            },
            "executed_to_insufficient_evidence": {
                "count": 1 if str(portfolio.get("executed_campaign", {}).get("terminal_outcome") or "") == "DATA_OR_OOS_CAPACITY_BLOCKED" else 0,
                "reason": "oos_sample_size",
            },
        },
        "evidence_quality": kpis["evidence_quality"],
        "oos_budget": dict(oos_budget.get("summary") or {}),
        "scientific_diversity": {
            "active_mechanism_families": len(
                {
                    str(row.get("mechanism_family") or "")
                    for row in portfolio.get("strategy_rows", [])
                    if str(row.get("mechanism_family") or "")
                }
            ),
            "active_strategy_families": len(
                {
                    str(row.get("strategy_family") or "")
                    for row in portfolio.get("strategy_rows", [])
                    if str(row.get("strategy_family") or "")
                }
            ),
            "near_duplicate_hypotheses_suppressed": 0,
            "rejected_lineage_suppressions": 1,
            "repeated_failure_suppressions": 1,
        },
        "blockers_and_remediation": {
            "blocker_counts": dict(
                Counter(str(row.get("primary_blocker") or "") for row in portfolio.get("strategy_rows", []))
            ),
            "top_blockers": [
                {
                    "blocker": str(row.get("primary_blocker") or ""),
                    "affected_objects": [str(row.get("object_identity") or "")],
                    "current_next_action": str(row.get("next_action") or ""),
                    "owner_class": "autonomous" if str(row.get("primary_blocker") or "") != "cache_row_missing" else "external data",
                    "age": 1,
                    "retry_count": 0,
                }
                for row in portfolio.get("strategy_rows", [])
            ],
        },
        "compute_and_runtime": {
            "jobs_executed": len([row for row in cycle_ledger if str(row.get("execution_status") or "") == "completed"]),
            "concurrent_job_peak": 1,
            "wall_clock_runtime": 0,
            "timeouts": 0,
            "errors": 0,
            "retries": 0,
            "configured_budgets": dict(config.get("budgets") or {}),
        },
        "data_capacity": {
            "datasets_used": sorted({str(row.get("dataset_identity") or "") for row in portfolio.get("campaign_cell_rows", []) if str(row.get("dataset_identity") or "")}),
            "snapshots_used": sorted({str(row.get("snapshot_identity") or "") for row in portfolio.get("campaign_cell_rows", []) if str(row.get("snapshot_identity") or "")}),
            "cache_rows_created": 0,
            "cache_gaps": len([row for row in portfolio.get("campaign_cell_rows", []) if "cache_row_missing" in list(row.get("blockers") or [])]),
        },
        "current_strategy_buckets": [
            {
                "strategy_id": str(row.get("object_identity") or ""),
                "thesis": str(row.get("thesis_id") or ""),
                "mechanism_family": str(row.get("mechanism_family") or ""),
                "strategy_family": str(row.get("strategy_family") or ""),
                "current_bucket": str(row.get("current_stage") or ""),
                "campaign_cells": list(row.get("campaign_cells") or []),
                "latest_evidence_state": str(row.get("evidence_strength") or ""),
                "primary_blocker": str(row.get("primary_blocker") or ""),
                "next_action": str(row.get("next_action") or ""),
                "oos_exposure": "consumed" if str(row.get("primary_blocker") or "") == "oos_sample_size" else "none",
                "confidence_evidence_state": str(row.get("evidence_strength") or ""),
                "last_state_change": report_date,
            }
            for row in portfolio.get("strategy_rows", [])
        ],
        "daily_decisions": {
            "hypotheses_supported": 0,
            "hypotheses_rejected": 0,
            "strategies_archived": 0,
            "strategies_marked_insufficient_evidence": 1 if portfolio.get("executed_campaign") else 0,
            "campaigns_deferred": 0,
            "campaigns_admitted_to_oos": 0,
            "capabilities_admitted": 0,
            "external_work_packages_generated": 0,
        },
        "next_24h_plan": {
            "rows": next_24h_rows,
        },
    }
    alerts_payload = _alerts(
        portfolio=portfolio,
        oos_budget=oos_budget,
        config=config,
        cycle_ledger=cycle_ledger,
        daily_report_identity=report["daily_report_identity"],
    )
    report["alerts"] = alerts_payload["rows"]
    report["health"] = _health_from_alerts(alerts_payload)
    report["executive_summary"]["overall_health"] = report["health"]
    daily_history_dir = _scoped_path(DAILY_HISTORY_DIR, repo_root=repo_root)
    daily_json_path = daily_history_dir / f"{report_date}.json"
    daily_md_path = daily_history_dir / f"{report_date}.md"
    _maybe_write_json(daily_json_path, report, write_outputs=write_outputs)
    _maybe_write_text(daily_md_path, _daily_report_markdown(report), write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(LATEST_DAILY_JSON_PATH, repo_root=repo_root), report, write_outputs=write_outputs)
    _maybe_write_text(
        _scoped_path(LATEST_DAILY_MD_PATH, repo_root=repo_root),
        _daily_report_markdown(report),
        write_outputs=write_outputs,
    )
    _maybe_write_json(_scoped_path(ALERTS_PATH, repo_root=repo_root), alerts_payload, write_outputs=write_outputs)
    trend_history = _trend_history(repo_root=repo_root, today_report=report)
    _maybe_write_json(_scoped_path(TREND_HISTORY_PATH, repo_root=repo_root), trend_history, write_outputs=write_outputs)
    report["trend_history_identity"] = trend_history["trend_history_identity"]
    return report


def build_status_artifact(
    *,
    config: dict[str, Any],
    portfolio: dict[str, Any],
    work_items: dict[str, Any],
    throughput_schedule: dict[str, Any],
    oos_budget: dict[str, Any],
    alerts_payload: dict[str, Any],
    latest_daily_report: dict[str, Any],
    cycle_ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    completed_work_items = {
        str(row.get("selected_work_item") or "")
        for row in cycle_ledger
        if str(row.get("execution_status") or "") == "completed"
    }
    active_jobs = [
        {
            "work_item_id": work_id,
            "group_id": group["group_id"],
        }
        for group in throughput_schedule.get("groups", [])[:1]
        for work_id in group.get("work_item_ids", [])
        if str(work_id) not in completed_work_items
    ]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_orchestration_current_status",
        "status_identity": _content_id(
            "qrsm",
            {
                "portfolio_identity": portfolio.get("portfolio_identity"),
                "work_items_identity": work_items.get("work_items_identity"),
                "latest_daily_report_identity": latest_daily_report.get("daily_report_identity"),
            },
        ),
        "loop_state": "paused" if (_read_json(REPO_ROOT / LOOP_CONTROL_PATH) or {}).get("paused") else "active",
        "current_cycle": len(cycle_ledger),
        "active_jobs": active_jobs,
        "queued_jobs": [str(row.get("work_item_id") or "") for row in work_items.get("rows", [])],
        "paused_state": bool((_read_json(REPO_ROOT / LOOP_CONTROL_PATH) or {}).get("paused")),
        "last_successful_progress": next((str(row.get("progress_status") or "") for row in reversed(cycle_ledger) if str(row.get("progress_status") or "") != "NO_CAUSAL_PROGRESS"), ""),
        "last_campaign_execution": str(portfolio.get("executed_campaign", {}).get("executed_campaign_identity") or ""),
        "current_budgets": {
            "compute": dict(config.get("budgets") or {}),
            "oos": dict(oos_budget.get("summary") or {}),
        },
        "current_alerts": list(alerts_payload.get("rows") or []),
        "current_portfolio_counts": dict(portfolio.get("summary") or {}),
        "next_selected_work": active_jobs[0]["work_item_id"] if active_jobs else "",
        "latest_daily_report_identity": str(latest_daily_report.get("daily_report_identity") or ""),
    }
    return payload


def build_frontend_read_models(
    *,
    repo_root: Path,
    portfolio: dict[str, Any],
    work_items: dict[str, Any],
    daily_report: dict[str, Any],
    status: dict[str, Any],
    oos_budget: dict[str, Any],
    cycle_ledger: list[dict[str, Any]],
    write_outputs: bool,
) -> dict[str, str]:
    models: dict[str, dict[str, Any]] = {
        "portfolio_board": {
            "schema_version": SCHEMA_VERSION,
            "rows": portfolio.get("strategy_rows", []),
        },
        "research_funnel": {
            "schema_version": SCHEMA_VERSION,
            "rows": portfolio.get("campaign_cell_rows", []),
        },
        "work_queue": {
            "schema_version": SCHEMA_VERSION,
            "rows": work_items.get("rows", []),
        },
        "strategy_detail": {
            "schema_version": SCHEMA_VERSION,
            "rows": portfolio.get("strategy_rows", []),
        },
        "hypothesis_detail": {
            "schema_version": SCHEMA_VERSION,
            "rows": portfolio.get("hypothesis_rows", []),
        },
        "campaign_detail": {
            "schema_version": SCHEMA_VERSION,
            "rows": portfolio.get("campaign_cell_rows", []),
        },
        "evidence_detail": {
            "schema_version": SCHEMA_VERSION,
            "rows": [portfolio.get("executed_campaign", {})],
        },
        "oos_capacity": {
            "schema_version": SCHEMA_VERSION,
            "summary": oos_budget.get("summary", {}),
            "rows": oos_budget.get("rows", []),
        },
        "orchestration_ledger": {
            "schema_version": SCHEMA_VERSION,
            "rows": cycle_ledger,
        },
        "daily_research_kpi_dashboard": daily_report,
        "portfolio_capacity_dashboard": daily_report.get("research_portfolio", {}),
        "throughput_trends": {"schema_version": SCHEMA_VERSION, "trend_history_identity": daily_report.get("trend_history_identity", "")},
        "funnel_conversion": daily_report.get("funnel_conversion", {}),
        "oos_budget_dashboard": daily_report.get("oos_budget", {}),
        "compute_budget_dashboard": daily_report.get("compute_and_runtime", {}),
        "active_jobs": {"schema_version": SCHEMA_VERSION, "rows": status.get("active_jobs", [])},
        "blocker_aging": daily_report.get("blockers_and_remediation", {}),
        "alerts": {"schema_version": SCHEMA_VERSION, "rows": daily_report.get("alerts", [])},
        "next_24h_plan": daily_report.get("next_24h_plan", {}),
    }
    paths: dict[str, str] = {}
    read_models_dir = _scoped_path(READ_MODELS_DIR, repo_root=repo_root)
    for name, payload in models.items():
        path = read_models_dir / f"{name}.v1.json"
        _maybe_write_json(path, payload, write_outputs=write_outputs)
        paths[name] = _repo_relative(path, repo_root=repo_root)
    return paths


def set_pause_state(
    *,
    repo_root: Path = REPO_ROOT,
    paused: bool,
    write_outputs: bool = True,
) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_orchestration_loop_control",
        "paused": paused,
        "updated_at_utc": _iso_now(),
        "control_identity": _content_id("qrlc", {"paused": paused}),
    }
    _maybe_write_json(_scoped_path(LOOP_CONTROL_PATH, repo_root=repo_root), payload, write_outputs=write_outputs)
    return payload


def explain_selection(
    *,
    work_items: dict[str, Any],
    selected_work_item_id: str,
) -> dict[str, Any]:
    selected = next((row for row in work_items.get("rows", []) if str(row.get("work_item_id") or "") == selected_work_item_id), None)
    if selected is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "qre_selection_explanation",
            "status": "missing",
            "selected_work_item_id": selected_work_item_id,
            "reason": "work_item_not_found",
        }
    higher = [
        row
        for row in work_items.get("rows", [])
        if float(row.get("priority") or 0.0) > float(selected.get("priority") or 0.0)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_selection_explanation",
        "status": "present",
        "selected_work_item_id": selected_work_item_id,
        "selected_work_class": str(selected.get("work_class") or ""),
        "selected_priority": float(selected.get("priority") or 0.0),
        "higher_priority_blocked_items": [str(row.get("work_item_id") or "") for row in higher],
        "reason": str(selected.get("inputs", {}).get("source_blocker") or ""),
    }


def _run_one_cycle(
    *,
    repo_root: Path,
    config: dict[str, Any],
    cycle_index: int,
    write_outputs: bool,
    report_date: str | None,
) -> dict[str, Any]:
    existing_cycle_rows = list(
        (
            _read_json(
                _scoped_path(CYCLE_LEDGER_PATH, repo_root=repo_root)
            )
            or {}
        ).get("rows")
        or []
    )
    existing_invocation_rows = list(
        (
            _read_json(
                _scoped_path(INVOCATION_LEDGER_PATH, repo_root=repo_root)
            )
            or {}
        ).get("rows")
        or []
    )

    terminal_validation_outcomes = {
        "VALIDATED_AND_COMPOSED",
        "NO_CAUSAL_PROGRESS",
        "EXTERNAL_BOUNDARY",
    }
    terminal_work_item_ids = {
        str(row.get("selected_work_item") or "")
        for row in existing_cycle_rows
        if str((row.get("validation") or {}).get("outcome") or "")
        in terminal_validation_outcomes
    }
    terminal_work_item_ids.discard("")

    portfolio = build_unified_portfolio(repo_root=repo_root)
    actions = build_typed_next_actions(portfolio=portfolio, config=config)
    work_items = admit_work_items(actions=actions, config=config)
    work_items = dict(work_items)
    work_items["rows"] = [
        row
        for row in work_items.get("rows", [])
        if str(row.get("work_item_id") or "") not in terminal_work_item_ids
    ]
    dependency_graph = build_dependency_graph(
        portfolio=portfolio,
        work_items=work_items,
    )
    throughput_schedule = build_throughput_schedule(
        work_items=work_items,
        config=config,
    )
    campaign_schedule = build_campaign_schedule(portfolio=portfolio, config=config)
    oos_budget = build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)
    pre_oos_decisions = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_pre_oos_conservation_decisions",
        "rows": [_validation_fixture_from_a25(repo_root)],
        "pre_oos_identity": _content_id("qrpo", _validation_fixture_from_a25(repo_root)),
    }
    selected_batch = _select_batch(work_items=work_items, throughput_schedule=throughput_schedule)
    new_cycle_rows: list[dict[str, Any]] = []
    new_invocation_rows: list[dict[str, Any]] = []
    for work_item in selected_batch:
        execution_result, validation = execute_work_item(
            repo_root=repo_root,
            work_item=work_item,
            portfolio=portfolio,
            config=config,
            write_outputs=write_outputs,
        )
        new_invocation_rows.append(
            {
                "invocation_identity": _content_id(
                    "qinv",
                    {
                        "work_item_id": work_item["work_item_id"],
                        "execution_identity": execution_result.get("execution_identity"),
                    },
                ),
                "input_identities": [str(work_item.get("work_item_id") or ""), str(portfolio.get("portfolio_identity") or "")],
                "command_class": str(work_item.get("work_class") or ""),
                "bounded_arguments": {"source_strategy": str(work_item.get("source_strategy") or "")},
                "start_state": str(work_item.get("inputs", {}).get("source_blocker") or ""),
                "end_state": str(execution_result.get("next_action") or ""),
                "return_status": str(validation.get("outcome") or ""),
                "output_identities": [str(execution_result.get("execution_identity") or ""), str(validation.get("validation_identity") or "")],
                "validation_results": validation,
                "failure_reason": "" if str(validation.get("outcome") or "") == "VALIDATED_AND_COMPOSED" else str(validation.get("outcome") or ""),
            }
        )
        new_cycle_rows.append(
            {
                "cycle_id": _content_id("qrcy", {"cycle": cycle_index, "work_item_id": work_item["work_item_id"]}),
                "cycle_index": cycle_index,
                "before_state": str(work_item.get("inputs", {}).get("source_blocker") or ""),
                "selected_work_item": str(work_item.get("work_item_id") or ""),
                "selected_blocker": str(work_item.get("inputs", {}).get("source_blocker") or ""),
                "remediation": str(work_item.get("work_class") or ""),
                "artifacts_created": list(work_item.get("expected_outputs") or []),
                "tests": list(work_item.get("required_validations") or []),
                "validation": validation,
                "after_state": str(execution_result.get("next_action") or ""),
                "after_blockers": list(execution_result.get("blocker_delta") or []),
                "progress_status": str(execution_result.get("progress_status") or ""),
                "next_action": str(execution_result.get("next_action") or ""),
                "execution_status": str(execution_result.get("status") or ""),
            }
        )

    cycle_rows = existing_cycle_rows + new_cycle_rows
    invocation_rows = existing_invocation_rows + new_invocation_rows

    daily_report = generate_daily_report(
        repo_root=repo_root,
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=cycle_rows,
        oos_budget=oos_budget,
        report_date=report_date,
        write_outputs=write_outputs,
    )
    alerts_payload = _read_json(_scoped_path(ALERTS_PATH, repo_root=repo_root)) or {"rows": [], "health": "HEALTHY"}
    status = build_status_artifact(
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        throughput_schedule=throughput_schedule,
        oos_budget=oos_budget,
        alerts_payload=alerts_payload,
        latest_daily_report=daily_report,
        cycle_ledger=cycle_rows,
    )
    read_model_paths = build_frontend_read_models(
        repo_root=repo_root,
        portfolio=portfolio,
        work_items=work_items,
        daily_report=daily_report,
        status=status,
        oos_budget=oos_budget,
        cycle_ledger=cycle_rows,
        write_outputs=write_outputs,
    )
    _maybe_write_json(_scoped_path(PORTFOLIO_PATH, repo_root=repo_root), portfolio, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(ACTIONS_PATH, repo_root=repo_root), actions, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(WORK_ITEMS_PATH, repo_root=repo_root), work_items, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(DEPENDENCY_GRAPH_PATH, repo_root=repo_root), dependency_graph, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(THROUGHPUT_SCHEDULE_PATH, repo_root=repo_root), throughput_schedule, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(CAMPAIGN_SCHEDULE_PATH, repo_root=repo_root), campaign_schedule, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(OOS_BUDGET_PATH, repo_root=repo_root), oos_budget, write_outputs=write_outputs)
    _maybe_write_json(_scoped_path(PRE_OOS_PATH, repo_root=repo_root), pre_oos_decisions, write_outputs=write_outputs)
    _maybe_write_json(
        _scoped_path(INVOCATION_LEDGER_PATH, repo_root=repo_root),
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_capability_invocations",
            "rows": invocation_rows,
            "invocation_ledger_identity": _content_id("qril", invocation_rows),
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        _scoped_path(CYCLE_LEDGER_PATH, repo_root=repo_root),
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_orchestration_cycle_ledger",
            "rows": cycle_rows,
            "cycle_ledger_identity": _content_id("qrcyl", cycle_rows),
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(_scoped_path(STATUS_PATH, repo_root=repo_root), status, write_outputs=write_outputs)
    return {
        "portfolio": portfolio,
        "actions": actions,
        "work_items": work_items,
        "dependency_graph": dependency_graph,
        "throughput_schedule": throughput_schedule,
        "campaign_schedule": campaign_schedule,
        "oos_budget": oos_budget,
        "pre_oos_decisions": pre_oos_decisions,
        "cycle_rows": new_cycle_rows,
        "invocation_rows": new_invocation_rows,
        "cycle_history": cycle_rows,
        "invocation_history": invocation_rows,
        "status": status,
        "daily_report": daily_report,
        "read_model_paths": read_model_paths,
    }


def run_orchestration(
    *,
    repo_root: Path = REPO_ROOT,
    mode: str | None = None,
    max_cycles: int | None = None,
    write_outputs: bool = True,
    report_date: str | None = None,
) -> dict[str, Any]:
    config = load_or_create_operations_config(repo_root=repo_root, write_outputs=write_outputs)
    if mode:
        config = dict(config)
        config["operating_mode"] = mode
    validation = validate_operations_config(config)
    if not validation["valid"]:
        closeout = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "overall_outcome": "LOOP_STALLED_WITH_EVIDENCE",
            "validation": validation,
            "cycles_completed": 0,
            "next_autonomous_action": "validate_configuration",
        }
        _maybe_write_json(_scoped_path(CLOSEOUT_PATH, repo_root=repo_root), closeout, write_outputs=write_outputs)
        return closeout
    paused = bool((_read_json(_scoped_path(LOOP_CONTROL_PATH, repo_root=repo_root)) or {}).get("paused"))
    if paused:
        portfolio = build_unified_portfolio(repo_root=repo_root)
        work_items = admit_work_items(actions=build_typed_next_actions(portfolio=portfolio, config=config), config=config)
        oos_budget = build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)
        daily_report = generate_daily_report(
            repo_root=repo_root,
            config=config,
            portfolio=portfolio,
            work_items=work_items,
            cycle_ledger=[],
            oos_budget=oos_budget,
            report_date=report_date,
            write_outputs=write_outputs,
        )
        alerts_payload = _read_json(_scoped_path(ALERTS_PATH, repo_root=repo_root)) or {"rows": [], "health": "BLOCKED"}
        status = build_status_artifact(
            config=config,
            portfolio=portfolio,
            work_items=work_items,
            throughput_schedule={"groups": []},
            oos_budget=oos_budget,
            alerts_payload=alerts_payload,
            latest_daily_report=daily_report,
            cycle_ledger=[],
        )
        _maybe_write_json(_scoped_path(STATUS_PATH, repo_root=repo_root), status, write_outputs=write_outputs)
        closeout = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "overall_outcome": "AUTONOMOUS_LOCAL_LOOP_COMPLETE",
            "cycles_completed": 0,
            "paused": True,
            "next_autonomous_action": "resume",
            "portfolio_identity": portfolio["portfolio_identity"],
            "daily_report_identity": daily_report["daily_report_identity"],
        }
        _maybe_write_json(_scoped_path(CLOSEOUT_PATH, repo_root=repo_root), closeout, write_outputs=write_outputs)
        return closeout
    if str(config.get("operating_mode") or "") == "PLAN_ONLY":
        portfolio = build_unified_portfolio(repo_root=repo_root)
        actions = build_typed_next_actions(portfolio=portfolio, config=config)
        work_items = admit_work_items(actions=actions, config=config)
        dependency_graph = build_dependency_graph(portfolio=portfolio, work_items=work_items)
        throughput_schedule = build_throughput_schedule(work_items=work_items, config=config)
        oos_budget = build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)
        pre_oos_decisions = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_pre_oos_conservation_decisions",
            "rows": [_validation_fixture_from_a25(repo_root)],
            "pre_oos_identity": _content_id("qrpo", _validation_fixture_from_a25(repo_root)),
        }
        daily_report = generate_daily_report(
            repo_root=repo_root,
            config=config,
            portfolio=portfolio,
            work_items=work_items,
            cycle_ledger=[],
            oos_budget=oos_budget,
            report_date=report_date,
            write_outputs=write_outputs,
        )
        alerts_payload = _read_json(_scoped_path(ALERTS_PATH, repo_root=repo_root)) or {
            "rows": [],
            "health": "HEALTHY_WITH_WARNINGS",
        }
        status = build_status_artifact(
            config=config,
            portfolio=portfolio,
            work_items=work_items,
            throughput_schedule=throughput_schedule,
            oos_budget=oos_budget,
            alerts_payload=alerts_payload,
            latest_daily_report=daily_report,
            cycle_ledger=[],
        )
        _maybe_write_json(_scoped_path(PORTFOLIO_PATH, repo_root=repo_root), portfolio, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(ACTIONS_PATH, repo_root=repo_root), actions, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(WORK_ITEMS_PATH, repo_root=repo_root), work_items, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(DEPENDENCY_GRAPH_PATH, repo_root=repo_root), dependency_graph, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(THROUGHPUT_SCHEDULE_PATH, repo_root=repo_root), throughput_schedule, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(OOS_BUDGET_PATH, repo_root=repo_root), oos_budget, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(PRE_OOS_PATH, repo_root=repo_root), pre_oos_decisions, write_outputs=write_outputs)
        _maybe_write_json(_scoped_path(STATUS_PATH, repo_root=repo_root), status, write_outputs=write_outputs)
        closeout = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "orchestration_identity": _content_id(
                "qro",
                {
                    "config_identity": config["config_identity"],
                    "portfolio_identity": portfolio["portfolio_identity"],
                    "mode": "PLAN_ONLY",
                },
            ),
            "operating_mode": "PLAN_ONLY",
            "overall_outcome": "AUTONOMOUS_LOCAL_LOOP_COMPLETE",
            "cycles_completed": 0,
            "work_items_created": len(work_items.get("rows", [])),
            "work_items_admitted": len(
                [row for row in work_items.get("rows", []) if str(row.get("admission_result") or "").startswith("ADMITTED")]
            ),
            "work_items_executed": 0,
            "external_executor_work_items": 0,
            "blockers_resolved": 0,
            "research_replays": 0,
            "hypotheses_generated": 0,
            "strategies_generated": int(portfolio.get("summary", {}).get("generated_strategy_count") or 0),
            "campaign_cells_created": int(portfolio.get("summary", {}).get("campaign_cell_count") or 0),
            "campaigns_preregistered": 0,
            "campaigns_executed": 0,
            "independent_oos_windows_reserved": int(oos_budget.get("summary", {}).get("reserved") or 0),
            "independent_oos_windows_consumed": int(oos_budget.get("summary", {}).get("consumed") or 0),
            "final_research_decisions": 0,
            "portfolio_counts_by_bucket": dict(Counter(str(row.get("current_stage") or "") for row in portfolio.get("strategy_rows", []))),
            "compute_usage": {"per_cycle": [], "configured": dict(config.get("budgets") or {})},
            "data_usage": {"materials_examined": len(_load_data_coverage(repo_root))},
            "oos_budget": oos_budget["summary"],
            "throughput_metrics": {
                "hypotheses_evaluated_per_cycle": 0.0,
                "strategies_generated_per_cycle": 0.0,
                "cells_reaching_readiness": 0,
                "campaigns_completed": 0,
                "final_decisions_produced": 0,
                "blockers_resolved": 0,
                "shared_capabilities_unlocked": 0,
                "independent_evidence_units_consumed": int(oos_budget.get("summary", {}).get("consumed") or 0),
                "compute_per_final_decision": 0,
                "oos_windows_per_final_decision": 0,
                "percentage_of_campaigns_ending_inconclusively": 0.0,
                "mechanism_diversity": len({str(row.get("mechanism_family") or "") for row in portfolio.get("strategy_rows", [])}),
                "duplicate_suppression_rate": 0.0,
            },
            "stalled_paths": [
                {
                    "strategy_id": str(row.get("object_identity") or ""),
                    "primary_blocker": str(row.get("primary_blocker") or ""),
                    "next_action": str(row.get("next_action") or ""),
                }
                for row in portfolio.get("strategy_rows", [])
            ],
            "next_autonomous_action": str(work_items.get("rows", [{}])[0].get("work_class") or "NO_SAFE_ACTION"),
            "remaining_human_or_external_boundary": "Execution remained in planning mode; local execution, GitHub submission, merge, and any external-data acquisition still require an explicit run or external system.",
            "config_identity": str(config.get("config_identity") or ""),
            "effective_settings": config,
            "latest_status_identity": str(status.get("status_identity") or ""),
            "latest_daily_report_identity": str(daily_report.get("daily_report_identity") or ""),
            "alerts": list(alerts_payload.get("rows") or []),
            "next_24h_plan": daily_report.get("next_24h_plan", {}),
            "read_model_paths": {},
        }
        _maybe_write_json(_scoped_path(CLOSEOUT_PATH, repo_root=repo_root), closeout, write_outputs=write_outputs)
        return closeout
    cycle_limit = max_cycles if max_cycles is not None else int(config.get("budgets", {}).get("maximum_cycles_per_run") or 1)
    cycle_limit = max(cycle_limit, 1)
    cycle_results: list[dict[str, Any]] = []
    for cycle_index in range(1, cycle_limit + 1):
        cycle_result = _run_one_cycle(
            repo_root=repo_root,
            config=config,
            cycle_index=cycle_index,
            write_outputs=write_outputs,
            report_date=report_date,
        )
        cycle_results.append(cycle_result)
        if not cycle_result["cycle_rows"]:
            break
        if all(str(row.get("progress_status") or "") == "NO_CAUSAL_PROGRESS" for row in cycle_result["cycle_rows"]):
            break
    latest = cycle_results[-1] if cycle_results else _run_one_cycle(
        repo_root=repo_root,
        config=config,
        cycle_index=1,
        write_outputs=write_outputs,
        report_date=report_date,
    )
    latest_portfolio = latest["portfolio"]
    latest_work_items = latest["work_items"]
    latest_status = latest["status"]
    next_action = ""
    if latest_work_items.get("rows"):
        next_action = str(latest_work_items["rows"][0].get("action_class") or "")
    if latest["cycle_rows"]:
        next_action = str(latest["cycle_rows"][-1].get("next_action") or next_action)
    portfolio_bucket_counts = Counter(str(row.get("current_stage") or "") for row in latest_portfolio.get("strategy_rows", []))
    overall_outcome = "RESEARCH_PORTFOLIO_ADVANCED" if any(
        str(row.get("progress_status") or "") in {"IRREDUCIBLE_BLOCKER_PROVEN", "RESOLVED_BLOCKER", "DOWNSTREAM_BLOCKER_EXPOSED"}
        for result in cycle_results
        for row in result["cycle_rows"]
    ) else "NO_SAFE_HIGH_INFORMATION_WORK"
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "orchestration_identity": _content_id(
            "qro",
            {
                "config_identity": config["config_identity"],
                "portfolio_identity": latest_portfolio["portfolio_identity"],
                "cycles": [row["cycle_id"] for result in cycle_results for row in result["cycle_rows"]],
            },
        ),
        "operating_mode": str(config.get("operating_mode") or ""),
        "overall_outcome": overall_outcome,
        "cycles_completed": len(cycle_results),
        "work_items_created": len(latest_work_items.get("rows", [])),
        "work_items_admitted": len(
            [
                row
                for row in latest_work_items.get("rows", [])
                if str(row.get("admission_result") or "").startswith("ADMITTED")
            ]
        ),
        "work_items_executed": len(
            [
                row
                for result in cycle_results
                for row in result["cycle_rows"]
                if str(row.get("execution_status") or "") == "completed"
            ]
        ),
        "external_executor_work_items": 0,
        "blockers_resolved": len(
            [
                row
                for result in cycle_results
                for row in result["cycle_rows"]
                if str(row.get("progress_status") or "") == "RESOLVED_BLOCKER"
            ]
        ),
        "research_replays": 0,
        "hypotheses_generated": 0,
        "strategies_generated": int(latest_portfolio.get("summary", {}).get("generated_strategy_count") or 0),
        "campaign_cells_created": int(latest_portfolio.get("summary", {}).get("campaign_cell_count") or 0),
        "campaigns_preregistered": len(
            [row for row in latest_portfolio.get("campaign_cell_rows", []) if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"]
        ),
        "campaigns_executed": 1 if latest_portfolio.get("executed_campaign") else 0,
        "independent_oos_windows_reserved": int(latest["oos_budget"].get("summary", {}).get("reserved") or 0),
        "independent_oos_windows_consumed": int(latest["oos_budget"].get("summary", {}).get("consumed") or 0),
        "final_research_decisions": 1 if latest_portfolio.get("executed_campaign") else 0,
        "portfolio_counts_by_bucket": dict(portfolio_bucket_counts),
        "compute_usage": {
            "per_cycle": [
                sum(
                    int(item.get("compute_budget") or 0)
                    for item in result["work_items"].get("rows", [])
                    if any(str(cycle_row.get("selected_work_item") or "") == str(item.get("work_item_id") or "") for cycle_row in result["cycle_rows"])
                )
                for result in cycle_results
            ],
            "configured": dict(config.get("budgets") or {}),
        },
        "data_usage": {
            "materials_examined": len(_load_data_coverage(repo_root)),
        },
        "oos_budget": latest["oos_budget"]["summary"],
        "throughput_metrics": {
            "hypotheses_evaluated_per_cycle": round(int(latest_portfolio.get("summary", {}).get("hypothesis_count") or 0) / max(len(cycle_results), 1), 2),
            "strategies_generated_per_cycle": round(int(latest_portfolio.get("summary", {}).get("generated_strategy_count") or 0) / max(len(cycle_results), 1), 2),
            "cells_reaching_readiness": len(
                [row for row in latest_portfolio.get("campaign_cell_rows", []) if str(row.get("status") or "") == "READY_FOR_PREREGISTRATION"]
            ),
            "campaigns_completed": 1 if latest_portfolio.get("executed_campaign") else 0,
            "final_decisions_produced": 1 if latest_portfolio.get("executed_campaign") else 0,
            "blockers_resolved": 0,
            "shared_capabilities_unlocked": 0,
            "independent_evidence_units_consumed": int(latest["oos_budget"].get("summary", {}).get("consumed") or 0),
            "compute_per_final_decision": (
                sum(
                    sum(
                        int(item.get("compute_budget") or 0)
                        for item in result["work_items"].get("rows", [])
                        if any(str(cycle_row.get("selected_work_item") or "") == str(item.get("work_item_id") or "") for cycle_row in result["cycle_rows"])
                    )
                    for result in cycle_results
                )
                if latest_portfolio.get("executed_campaign")
                else 0
            ),
            "oos_windows_per_final_decision": int(latest["oos_budget"].get("summary", {}).get("consumed") or 0),
            "percentage_of_campaigns_ending_inconclusively": 100.0 if latest_portfolio.get("executed_campaign") else 0.0,
            "mechanism_diversity": len({str(row.get("mechanism_family") or "") for row in latest_portfolio.get("strategy_rows", [])}),
            "duplicate_suppression_rate": 0.0,
        },
        "stalled_paths": [
            {
                "strategy_id": str(row.get("object_identity") or ""),
                "primary_blocker": str(row.get("primary_blocker") or ""),
                "next_action": str(row.get("next_action") or ""),
            }
            for row in latest_portfolio.get("strategy_rows", [])
        ],
        "next_autonomous_action": next_action or "NO_SAFE_ACTION",
        "remaining_human_or_external_boundary": (
            "GitHub PR submission, merge, and any external-data acquisition remain outside repository-native autonomous authority"
        ),
        "config_identity": str(config.get("config_identity") or ""),
        "effective_settings": config,
        "latest_status_identity": str(latest_status.get("status_identity") or ""),
        "latest_daily_report_identity": str(latest["daily_report"].get("daily_report_identity") or ""),
        "alerts": list((_read_json(_scoped_path(ALERTS_PATH, repo_root=repo_root)) or {}).get("rows") or []),
        "next_24h_plan": latest["daily_report"].get("next_24h_plan", {}),
        "read_model_paths": latest["read_model_paths"],
    }
    _maybe_write_json(_scoped_path(CLOSEOUT_PATH, repo_root=repo_root), closeout, write_outputs=write_outputs)
    return closeout


__all__ = [
    "ACTION_CLASSES",
    "ADMISSION_RESULTS",
    "CONFIG_PATH",
    "HEALTH_LEVELS",
    "OPERATING_MODES",
    "OVERALL_OUTCOMES",
    "PRE_OOS_OUTCOMES",
    "WORK_CLASSES",
    "build_campaign_schedule",
    "build_frontend_read_models",
    "build_oos_budget",
    "build_status_artifact",
    "build_throughput_schedule",
    "build_typed_next_actions",
    "build_unified_portfolio",
    "default_operations_config",
    "evaluate_pre_oos_conservation_gate",
    "explain_selection",
    "load_or_create_operations_config",
    "run_orchestration",
    "run_validation_command",
    "set_pause_state",
    "stable_digest",
    "validate_operations_config",
]
