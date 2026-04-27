"""
Research runner:
voert alle enabled strategieen uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent.backtesting.engine import (
    MIN_ROBUSTNESS_FOLDS,
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    normalize_evaluation_config,
)
from agent.backtesting.features import FEATURE_VERSION
from research.candidate_pipeline import (
    SCREENING_PROMOTED,
    apply_eligibility,
    apply_fit_prior,
    build_candidate_artifact_payload,
    build_filter_summary_payload,
    deduplicate_candidates,
    index_readiness,
    plan_candidates,
    sampling_plan_for_param_grid,
    screening_candidates,
    summarize_candidates,
    validation_candidates,
)
from research.falsification import (
    check_corrected_significance,
    check_fee_drag_ratio,
    check_low_trade_count,
    check_oos_collapse,
)
from research.falsification_reporting import (
    build_candidate_gate_record,
    build_falsification_payload,
)
from research.integrity import IntegrityCheck, IntegrityReport
from research.integrity_reporting import build_integrity_report_payload
from research.batching import (
    build_batch_manifest_payload,
    build_run_batches_payload,
    partition_execution_batches,
)
from research.batch_execution import execute_screening_batch, execute_validation_batch
from research.campaigns import (
    build_campaign_id,
    build_run_campaign_payload,
    build_run_campaign_progress_payload,
)
from research.empty_run_reporting import (
    EXIT_CODE_DEGENERATE_NO_SURVIVORS,
    DegenerateResearchRunError,
    build_empty_run_diagnostics_payload,
)
from research.observability import ProgressTracker
from research.orchestration_policy import (
    resolve_continue_latest_policy,
    validate_continuation_compatibility,
)
from research.candidate_sidecars import (
    SidecarBuildContext,
    build_and_write_all as build_and_write_v3_12_sidecars,
)
from research.regime_sidecars import (
    RegimeSidecarBuildContext,
    build_and_write_regime_sidecars,
)
from research.regime_width_feed import (
    WidthFeedResult,
    build_width_distributions,
)
from research.candidate_returns_feed import build_records_from_evaluations
from research.portfolio_sleeve_sidecars import (
    PortfolioSleeveBuildContext,
    build_and_write_portfolio_sleeve_sidecars,
)
from research.paper_validation_sidecars import (
    PaperValidationBuildContext,
    build_and_write_paper_validation_sidecars,
)
from research.strategy_campaign_metadata import (
    write_campaign_metadata_sidecar,
)
from research.strategy_hypothesis_catalog import (
    HypothesisCatalogError,
    validate_active_discovery_preset_bridges,
    write_catalog_sidecar,
)
from research.portfolio_reporting import build_portfolio_aggregation_payload
from research.promotion_reporting import build_candidate_registry_payload
from research.recovery import (
    FRESH_ATTEMPT_REASON,
    RESUME_PENDING_ATTEMPT_REASON,
    RESUME_STALE_ATTEMPT_REASON,
    RETRY_FAILED_ATTEMPT_REASON,
    build_batch_recovery_state_payload,
    default_recovery_policy,
    prepare_resume_state,
    write_batch_recovery_state,
)
from research.regime_reporting import build_regime_diagnostics_payload
from research.presets import (
    ResearchPreset,
    get_preset,
    hypothesis_metadata_issues,
    resolve_preset_bundle,
    validate_preset,
)
from research.registry import get_enabled_strategies
from research.public_artifact_status import (
    PUBLIC_ARTIFACT_STATUS_PATH,
    build_public_artifact_status,
    read_public_artifact_status,
    write_public_artifact_status,
)
from research.report_agent import generate_post_run_report
from research.campaign_evidence_ledger import load_events as _load_campaign_events
from research.dead_zone_detection import write_dead_zones_artifact
from research.funnel_spawn_proposer import write_spawn_proposals_artifact
from research.information_gain import (
    InformationGainInputs,
    write_information_gain_artifact,
)
from research.research_evidence_ledger import write_research_evidence_artifact
from research.run_meta import (
    RUN_META_PATH,
    build_candidate_summary,
    build_run_meta_payload,
    rollup_rejection_reasons,
    write_run_meta_sidecar,
)
from research.stop_condition_engine import write_stop_conditions_artifact
from research.viability_metrics import write_viability_artifact
from research.results import make_result_row, write_latest_json, write_results_to_csv
from research.screening_evidence import (
    SCREENING_EVIDENCE_PATH,
    build_screening_evidence_payload,
)
from research.screening_process import execute_screening_candidate_isolated
from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_PASSED,
    FINAL_STATUS_REJECTED,
    FINAL_STATUS_TIMED_OUT,
    build_screening_runtime_records,
    build_screening_sidecar_payload,
)
from research._sidecar_io import write_sidecar_atomic
from research.run_state import RunStateStore
from research.statistical_reporting import build_statistical_defensibility_payload, regime_count_settings
from research.universe import (
    build_research_universe,
    build_research_universe_from_preset,
)

# v3.9 orchestration seam: research is the only module permitted to
# import from `orchestration/` beyond dashboard's late-phase launch
# API. Phase 4 upgrades the Orchestrator from a pass-through seam
# to the real owner of batch dispatch for both inline and parallel
# modes via dispatch_serial_batches / dispatch_parallel_batches.
# See ADR-009.
from orchestration import (
    BatchOutcome,
    Orchestrator,
    TaskKind,
    classify_batch_reason,
    deepcopy_batch,
)

SIDE_CAR_PATH = Path("research/statistical_defensibility_latest.v1.json")
WALK_FORWARD_PATH = "research/walk_forward_latest.v1.json"
CANDIDATE_REGISTRY_PATH = Path("research/candidate_registry_latest.v1.json")
UNIVERSE_SNAPSHOT_PATH = Path("research/universe_snapshot_latest.v1.json")
PORTFOLIO_AGGREGATION_PATH = Path("research/portfolio_aggregation_latest.v1.json")
REGIME_DIAGNOSTICS_PATH = Path("research/regime_diagnostics_latest.v1.json")
COST_SENSITIVITY_PATH = Path("research/cost_sensitivity_latest.v1.json")
EMPTY_RUN_DIAGNOSTICS_PATH = Path("research/empty_run_diagnostics_latest.v1.json")
RUN_CANDIDATES_PATH = Path("research/run_candidates_latest.v1.json")
RUN_FILTER_SUMMARY_PATH = Path("research/run_filter_summary_latest.v1.json")
RUN_BATCHES_PATH = Path("research/run_batches_latest.v1.json")
RUN_SCREENING_CANDIDATES_PATH = Path("research/run_screening_candidates_latest.v1.json")
RUN_CAMPAIGN_PATH = Path("research/run_campaign_latest.v1.json")
RUN_CAMPAIGN_PROGRESS_PATH = Path("research/run_campaign_progress_latest.v1.json")
RUN_PROGRESS_PATH = Path("research/run_progress_latest.v1.json")
RUN_STATE_PATH = Path("research/run_state.v1.json")
RUN_MANIFEST_PATH = Path("research/run_manifest_latest.v1.json")
INTEGRITY_REPORT_PATH = Path("research/integrity_report_latest.v1.json")
FALSIFICATION_GATES_PATH = Path("research/falsification_gates_latest.v1.json")
RUN_LOG_DIR = Path("logs/research")
RUN_HEARTBEAT_TIMEOUT_S = 300

# v3.15.2 Campaign Operating Layer breadcrumb.
# When the launcher (research.campaign_launcher) invokes this module as a
# subprocess it passes ``--campaign-id CID``; we stash it here so the
# campaign artifacts (run_state, run_campaign_latest) can record the
# linkage without threading a new kwarg through every _persist_campaign
# call site. None when the flag is absent — all callers see a null field.
_COL_CAMPAIGN_ID: str | None = None
SCREENING_PARAM_SAMPLE_LIMIT = 3
DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS = 300
DEFAULT_EXECUTION_MAX_WORKERS = 1
BATCH_EXECUTOR_CLASS = ProcessPoolExecutor

EVALUATION_VERSION = "1.0"
DEFAULT_COST_PER_SIDE = 0.0035


def load_research_config(config_path="config/config.yaml"):
    path = Path(config_path)
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    return config.get("research") or {}


def _resolve_execution_settings(research_config: dict) -> dict[str, str | int]:
    execution_config = research_config.get("execution") or {}
    max_workers = max(1, int(execution_config.get("max_workers", DEFAULT_EXECUTION_MAX_WORKERS)))
    execution_mode = "inline" if max_workers == 1 else "process_pool"
    return {
        "max_workers": max_workers,
        "execution_mode": execution_mode,
    }


def _git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _run_id(as_of_utc) -> str:
    return as_of_utc.strftime("%Y%m%dT%H%M%S%fZ")


def _preset_validation_is_strict() -> bool:
    """v3.11: strict preset validation is opt-in via env flag.

    Default is soft (warnings only). Setting
    ``QRE_STRICT_PRESET_VALIDATION=1`` elevates hypothesis-metadata
    issues to hard failures so the runner refuses to start. Any of
    {"1", "true", "yes", "on"} (case-insensitive) enables strict mode.
    """
    raw = os.environ.get("QRE_STRICT_PRESET_VALIDATION", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class PresetValidationError(RuntimeError):
    """Raised when strict preset validation is enabled and issues exist."""


def _enforce_preset_validation(
    preset_obj: ResearchPreset,
    tracker,
) -> None:
    """Surface preset validation issues as warnings or failures.

    v3.11 soft-validation contract (hypothesis metadata):
    - Empty rationale / expected_behavior / falsification on enabled
      presets emit a ``preset_validation_warning`` tracker event.

    v3.15.6 extension (funnel-stage validation):
    - ``screening_phase`` outside the Literal set emits the same
      ``preset_validation_warning`` event.

    Under ``QRE_STRICT_PRESET_VALIDATION=1`` either category raises
    ``PresetValidationError`` so misconfigured presets cannot reach
    a daily run.
    """
    metadata_issues = hypothesis_metadata_issues(preset_obj)
    phase_issues = [
        issue for issue in validate_preset(preset_obj)
        if issue.startswith("screening_phase_invalid:")
    ]
    issues = metadata_issues + phase_issues
    if not issues:
        return
    for issue in issues:
        tracker.emit_event(
            "preset_validation_warning",
            preset_name=preset_obj.name,
            issue=issue,
        )
    if _preset_validation_is_strict():
        raise PresetValidationError(
            f"preset {preset_obj.name!r} failed strict validation: {issues}"
        )


def _config_hash(research_config: dict, provenance_events: list) -> str:
    payload = {
        "research_config": research_config,
        "adapter_hashes": sorted({event.config_hash for event in provenance_events if event.config_hash}),
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_provenance_sidecar(
    research_config: dict,
    as_of_utc,
    interval_ranges: dict[str, dict[str, str]],
    provenance_events: list,
) -> None:
    run_id = _run_id(as_of_utc)
    target_dir = Path("research/provenance")
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "adapter_names": sorted({event.adapter for event in provenance_events}),
        "cache_hit_counts": {
            "hits": sum(1 for event in provenance_events if event.cache_hit),
            "misses": sum(1 for event in provenance_events if not event.cache_hit),
        },
        "config_hash": _config_hash(research_config, provenance_events),
        "git_revision": _git_revision(),
        "as_of_utc": as_of_utc.isoformat(),
        "interval_ranges": interval_ranges,
        "fredapi_version": next((event.source_version for event in provenance_events if event.adapter == "fredapi"), None),
        "yfinance_version": next((event.source_version for event in provenance_events if event.adapter == "yfinance"), None),
    }

    with (target_dir / f"{run_id}.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
    for attempt in range(3):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)


def _read_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_paper_blocked_index() -> dict[str, list[str]]:
    """v3.15.9 — read paper_readiness_latest.v1.json and derive a
    ``{candidate_id: [blocking_reasons]}`` index for the screening
    evidence builder. Missing / malformed sidecar yields an empty
    dict so the evidence artifact still writes.
    """
    path = Path("research/paper_readiness_latest.v1.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, list[str]] = {}
    for row in data.get("candidates", []) or []:
        if str(row.get("status")) != "blocked":
            continue
        cid = row.get("candidate_id")
        if cid is None:
            continue
        out[str(cid)] = [str(r) for r in (row.get("blocking_reasons") or [])]
    return out


def _write_json_with_history(*, path: Path, payload: dict, run_id: str, history_name: str) -> None:
    _write_json_atomic(path, payload)
    _write_json_atomic(Path("research/history") / run_id / history_name, payload)


def _write_universe_snapshot_sidecar(
    snapshot,
    path: Path = UNIVERSE_SNAPSHOT_PATH,
) -> None:
    _write_json_atomic(path, snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot)


def _write_statistical_defensibility_sidecar(
    evaluations: list[dict],
    as_of_utc,
    intervals: list[str],
    market_count: int,
    regime_count: int | None,
    regime_count_source: str,
    path: Path = SIDE_CAR_PATH,
) -> None:
    payload = build_statistical_defensibility_payload(
        evaluations=evaluations,
        as_of_utc=as_of_utc,
        intervals=intervals,
        market_count=market_count,
        regime_count=regime_count,
        regime_count_source=regime_count_source,
    )
    _write_json_atomic(path, payload)


def _sidecar_strategy_entry(
    strategy: dict,
    asset: str,
    interval: str,
    report: dict,
) -> dict:
    folds = report.get("folds", [])
    return {
        "strategy_name": strategy["name"],
        "asset": asset,
        "interval": interval,
        "selected_params": report.get("selected_params", {}),
        "selection_metric": report.get("selection_metric", "sharpe"),
        "is_summary": report.get("is_summary", {}),
        "oos_summary": report.get("oos_summary", {}),
        "folds": folds,
        "leakage_checks_ok": report.get("leakage_checks_ok", False),
        "robustness": _compute_robustness(folds),
    }


def _compute_robustness(folds: list[dict]) -> dict:
    fold_count = len(folds)
    oos_bars = sum(f["test"][1] - f["test"][0] + 1 for f in folds) if folds else 0
    total_bars_covered = 0
    if folds:
        min_start = min(f["train"][0] for f in folds)
        max_end = max(f["test"][1] for f in folds)
        total_bars_covered = max_end - min_start + 1
    oos_coverage_ratio = round(oos_bars / total_bars_covered, 4) if total_bars_covered > 0 else 0.0
    return {
        "fold_count": fold_count,
        "oos_bar_coverage": oos_bars,
        "total_bars_covered": total_bars_covered,
        "oos_coverage_ratio": oos_coverage_ratio,
        "robustness_sufficient": fold_count >= MIN_ROBUSTNESS_FOLDS,
    }


def _write_walk_forward_sidecar(
    *,
    as_of_utc,
    evaluation_config: dict,
    strategy_reports: list[dict],
    path: str = WALK_FORWARD_PATH,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    insufficient = [
        r["strategy_name"] for r in strategy_reports
        if not r.get("robustness", {}).get("robustness_sufficient", False)
    ]
    payload = {
        "version": "v1",
        "generated_at_utc": as_of_utc.astimezone(timezone.utc).isoformat(),
        "evaluation_config": evaluation_config,
        "robustness_summary": {
            "min_robustness_folds": MIN_ROBUSTNESS_FOLDS,
            "strategy_count": len(strategy_reports),
            "insufficient_count": len(insufficient),
            "all_strategies_sufficient": len(insufficient) == 0,
        },
        "strategies": strategy_reports,
    }
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_candidate_registry(
    *,
    rows: list[dict],
    walk_forward_reports: list[dict],
    research_config: dict,
    as_of_utc,
    candidates_by_id: dict[str, dict] | None = None,
    path: Path = CANDIDATE_REGISTRY_PATH,
) -> None:
    if not walk_forward_reports:
        return

    research_latest = {
        "generated_at_utc": as_of_utc.isoformat(),
        "results": rows,
    }
    walk_forward = {"strategies": walk_forward_reports}

    statistical_defensibility = None
    if SIDE_CAR_PATH.exists():
        with SIDE_CAR_PATH.open(encoding="utf-8") as handle:
            statistical_defensibility = json.load(handle)

    # v3.15.7: build a {strategy_id -> pass_kind} index from the
    # candidate runtime records so promotion_reporting can downgrade
    # exploratory passes to ``needs_investigation``. The index lives
    # here in run_research; promotion_reporting receives it via the
    # ``screening_pass_kinds`` kwarg and never serialises pass_kind
    # into the (frozen) candidate registry rows.
    screening_pass_kinds: dict[str, str | None] = {}
    if candidates_by_id:
        from research.promotion import build_strategy_id

        rows_by_key: dict[tuple[str, str, str], list[dict]] = {}
        for row in rows:
            if not row.get("success", False):
                continue
            key = (
                str(row.get("strategy_name")),
                str(row.get("asset")),
                str(row.get("interval")),
            )
            rows_by_key.setdefault(key, []).append(row)
        for candidate in candidates_by_id.values():
            screening = candidate.get("screening") or {}
            pass_kind = screening.get("pass_kind") if isinstance(screening, dict) else None
            key = (
                str(candidate.get("strategy_name")),
                str(candidate.get("asset")),
                str(candidate.get("interval")),
            )
            for matched_row in rows_by_key.get(key, []):
                selected_params = json.loads(matched_row.get("params_json", "{}"))
                strategy_id = build_strategy_id(
                    str(matched_row.get("strategy_name")),
                    str(matched_row.get("asset")),
                    str(matched_row.get("interval")),
                    selected_params,
                )
                screening_pass_kinds[strategy_id] = pass_kind

    payload = build_candidate_registry_payload(
        research_latest=research_latest,
        walk_forward=walk_forward,
        statistical_defensibility=statistical_defensibility,
        promotion_config=research_config.get("promotion"),
        git_revision=_git_revision(),
        screening_pass_kinds=screening_pass_kinds or None,
    )
    _write_json_atomic(path, payload)


def _write_portfolio_aggregation_sidecar(
    *,
    evaluations: list[dict],
    as_of_utc,
    path: Path = PORTFOLIO_AGGREGATION_PATH,
) -> None:
    payload = build_portfolio_aggregation_payload(
        evaluations=evaluations,
        as_of_utc=as_of_utc,
        git_revision=_git_revision(),
    )
    _write_json_atomic(path, payload)


def _write_integrity_report_sidecar(
    *,
    run_id: str,
    as_of_utc: datetime,
    research_config: dict,
    provenance_events: list,
    integrity_checks: list,
    path: Path = INTEGRITY_REPORT_PATH,
) -> dict:
    report = IntegrityReport(checks=list(integrity_checks))
    payload = build_integrity_report_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        config_hash=_config_hash(research_config, provenance_events),
        git_revision=_git_revision(),
        feature_version=FEATURE_VERSION,
        evaluation_version=EVALUATION_VERSION,
        report=report,
    )
    _write_json_with_history(
        path=path,
        payload=payload,
        run_id=run_id,
        history_name="integrity_report.v1.json",
    )
    return payload


def _write_falsification_gates_sidecar(
    *,
    run_id: str,
    as_of_utc: datetime,
    rows: list[dict],
    walk_forward_reports: list[dict],
    statistical_defensibility: dict | None,
    cost_per_side: float,
    path: Path = FALSIFICATION_GATES_PATH,
) -> dict:
    wf_index: dict[tuple[str, str, str], dict] = {
        (str(entry["strategy_name"]), str(entry["asset"]), str(entry["interval"])): entry
        for entry in walk_forward_reports
    }
    def_index: dict[tuple[str, str, str], dict] = {}
    if isinstance(statistical_defensibility, dict):
        for family_entry in statistical_defensibility.get("families", []) or []:
            interval = str(family_entry.get("interval") or "")
            for member in family_entry.get("members", []) or []:
                def_index[(str(member["strategy_name"]), str(member["asset"]), interval)] = member

    candidate_records: list[dict] = []
    for row in rows:
        if not row.get("success", False):
            continue
        strategy_name = str(row["strategy_name"])
        asset = str(row["asset"])
        interval = str(row["interval"])
        key = (strategy_name, asset, interval)
        wf_entry = wf_index.get(key)
        if wf_entry is None:
            continue
        selected_params = json.loads(row.get("params_json") or "{}")
        oos_summary = wf_entry.get("oos_summary") or {}
        is_summary = wf_entry.get("is_summary") or {}
        defensibility = def_index.get(key)
        verdicts = [
            check_low_trade_count(oos_summary),
            check_oos_collapse(is_summary, oos_summary),
            check_fee_drag_ratio(oos_summary, cost_per_side=cost_per_side),
            check_corrected_significance(defensibility),
        ]
        candidate_records.append(
            build_candidate_gate_record(
                strategy_name=strategy_name,
                asset=asset,
                interval=interval,
                selected_params=selected_params,
                sizing_regime="fixed_unit",
                verdicts=verdicts,
            )
        )

    payload = build_falsification_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        candidate_records=sorted(candidate_records, key=lambda item: str(item["candidate_id"])),
    )
    _write_json_with_history(
        path=path,
        payload=payload,
        run_id=run_id,
        history_name="falsification_gates.v1.json",
    )
    return payload


def _write_regime_diagnostics_sidecar(
    *,
    evaluations: list[dict],
    as_of_utc,
    research_config: dict,
    evaluation_config: dict,
    provenance_events: list,
    path: Path = REGIME_DIAGNOSTICS_PATH,
) -> None:
    payload = build_regime_diagnostics_payload(
        evaluations=evaluations,
        as_of_utc=as_of_utc,
        git_revision=_git_revision(),
        config_hash=_config_hash(research_config, provenance_events),
        evaluation_config=evaluation_config,
        regime_config=research_config.get("regime_diagnostics"),
    )
    _write_json_atomic(path, payload)


def _build_engine(
    start_datum: str,
    eind_datum: str,
    evaluation_config: dict,
    regime_config: dict | None = None,
) -> BacktestEngine:
    try:
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
            evaluation_config=evaluation_config,
            regime_config=regime_config,
        )
    except TypeError as exc:
        if "regime_config" in str(exc):
            try:
                return BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                    evaluation_config=evaluation_config,
                )
            except TypeError as exc2:
                if "evaluation_config" not in str(exc2):
                    raise
                return BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                )
        if "evaluation_config" not in str(exc):
            raise
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
        )


def _inspect_engine_readiness(engine, assets: list, interval: str) -> list[dict]:
    asset_symbols = [asset.symbol if hasattr(asset, "symbol") else str(asset) for asset in assets]
    if hasattr(engine, "inspect_asset_readiness"):
        return list(engine.inspect_asset_readiness(asset_symbols, interval))
    requested_start = getattr(engine, "start", "")
    requested_end = getattr(engine, "eind", getattr(engine, "end", ""))
    return [
        {
            "asset": asset,
            "interval": interval,
            "requested_start": requested_start,
            "requested_end": requested_end,
            "bar_count": 0,
            "fold_count": 1,
            "status": "evaluable",
            "drop_reason": None,
        }
        for asset in asset_symbols
    ]


def _count_evaluable_oos_daily_return_evaluations(evaluations: list[dict]) -> int:
    count = 0
    for evaluation in evaluations:
        report = evaluation.get("evaluation_report") or {}
        samples = report.get("evaluation_samples") or {}
        daily_returns = samples.get("daily_returns")
        if isinstance(daily_returns, list) and daily_returns:
            count += 1
    return count


def _write_empty_run_diagnostics_sidecar(
    *,
    as_of_utc,
    failure_stage: str,
    assets: list,
    intervals: list[str],
    interval_ranges: dict[str, dict[str, str]],
    pair_diagnostics: list[dict],
    evaluations_count: int = 0,
    evaluations_with_oos_daily_returns: int = 0,
    path: Path = EMPTY_RUN_DIAGNOSTICS_PATH,
) -> dict:
    payload = build_empty_run_diagnostics_payload(
        as_of_utc=as_of_utc,
        failure_stage=failure_stage,
        selected_assets=[asset.symbol if hasattr(asset, "symbol") else str(asset) for asset in assets],
        selected_intervals=list(intervals),
        interval_ranges=interval_ranges,
        pair_diagnostics=pair_diagnostics,
        evaluations_count=evaluations_count,
        evaluations_with_oos_daily_returns=evaluations_with_oos_daily_returns,
        col_campaign_id=_COL_CAMPAIGN_ID,
    )
    _write_json_atomic(path, payload)
    return payload


def _build_run_manifest_payload(
    *,
    run_id: str,
    started_at_utc,
    research_config: dict,
    assets: list,
    intervals: list[str],
    total_candidate_count: int,
    strategies: list[dict],
    universe_snapshot_path: Path,
    screening_candidate_budget_seconds: int,
    execution_settings: dict[str, str | int],
    lifecycle_mode: str,
    resumed_from_run_id: str | None,
    continuation_summary: dict[str, int],
    recovery_policy: dict[str, object],
    retry_failed_batches: bool,
) -> dict:
    asset_symbols = [asset.symbol if hasattr(asset, "symbol") else str(asset) for asset in assets]
    return {
        "version": "v1",
        "run_id": run_id,
        "created_at_utc": started_at_utc.isoformat(),
        "started_at_utc": started_at_utc.isoformat(),
        "status": "running",
        "git_revision": _git_revision(),
        "config_hash": _config_hash(research_config, []),
        "feature_version": FEATURE_VERSION,
        "evaluation_version": EVALUATION_VERSION,
        "lifecycle_mode": lifecycle_mode,
        "resumed_from_run_id": resumed_from_run_id,
        "retry_failed_batches": bool(retry_failed_batches),
        "continuation_summary": copy.deepcopy(continuation_summary),
        "recovery_policy": copy.deepcopy(recovery_policy),
        "universe_snapshot_path": universe_snapshot_path.as_posix(),
        "resolved_universe_summary": {
            "asset_count": len(asset_symbols),
            "interval_count": len(intervals),
            "assets": asset_symbols,
            "intervals": list(intervals),
        },
        "total_candidate_count": int(total_candidate_count),
        "candidate_grouping_summary": {
            "by_strategy": {
                strategy["name"]: len(asset_symbols) * len(intervals)
                for strategy in strategies
            },
            "by_interval": {
                interval: len(asset_symbols) * len(strategies)
                for interval in intervals
            },
        },
        "stage_definitions": [
            "planning",
            "dedupe",
            "fit_prior",
            "eligibility_filter",
            "screening",
            "validation",
            "writing_outputs",
        ],
        "screening_enabled": True,
        "validation_enabled": True,
        "screening_param_sample_limit": SCREENING_PARAM_SAMPLE_LIMIT,
        "screening_cost_model": {
            "mode": "representative_param_subset",
            "max_sampled_parameter_combinations": SCREENING_PARAM_SAMPLE_LIMIT,
        },
        "screening_candidate_budget_seconds": int(screening_candidate_budget_seconds),
        "execution": {
            "max_workers": int(execution_settings["max_workers"]),
            "execution_mode": str(execution_settings["execution_mode"]),
        },
        "artifacts": {
            "run_candidates_path": RUN_CANDIDATES_PATH.as_posix(),
            "run_filter_summary_path": RUN_FILTER_SUMMARY_PATH.as_posix(),
            "run_batches_path": RUN_BATCHES_PATH.as_posix(),
            "run_screening_candidates_path": RUN_SCREENING_CANDIDATES_PATH.as_posix(),
            "run_campaign_path": RUN_CAMPAIGN_PATH.as_posix(),
            "run_campaign_progress_path": RUN_CAMPAIGN_PROGRESS_PATH.as_posix(),
        },
    }


def _merge_manifest(path: Path, **fields) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key, value in fields.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    _write_json_atomic(path, payload)


def _persist_candidate_pipeline_sidecars(
    *,
    run_id: str,
    as_of_utc: datetime,
    candidates: list[dict],
) -> tuple[dict, dict]:
    candidate_payload = build_candidate_artifact_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        candidates=candidates,
    )
    filter_payload = build_filter_summary_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        candidates=candidates,
    )
    _write_json_with_history(
        path=RUN_CANDIDATES_PATH,
        payload=candidate_payload,
        run_id=run_id,
        history_name="run_candidates.v1.json",
    )
    _write_json_with_history(
        path=RUN_FILTER_SUMMARY_PATH,
        payload=filter_payload,
        run_id=run_id,
        history_name="run_filter_summary.v1.json",
    )
    return candidate_payload, filter_payload


def _persist_screening_candidate_sidecar(
    *,
    run_id: str,
    as_of_utc: datetime,
    screening_records: list[dict],
) -> dict:
    payload = build_screening_sidecar_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        records=screening_records,
    )
    _write_json_with_history(
        path=RUN_SCREENING_CANDIDATES_PATH,
        payload=payload,
        run_id=run_id,
        history_name="run_screening_candidates.v1.json",
    )
    return payload


def _persist_run_batches_sidecar(
    *,
    run_id: str,
    as_of_utc: datetime,
    batches: list[dict],
) -> dict:
    payload = build_run_batches_payload(
        run_id=run_id,
        as_of_utc=as_of_utc,
        batches=batches,
    )
    _write_json_with_history(
        path=RUN_BATCHES_PATH,
        payload=payload,
        run_id=run_id,
        history_name="run_batches.v1.json",
    )
    return payload


def _write_batch_manifest(*, run_id: str, batch: dict) -> None:
    payload = build_batch_manifest_payload(
        run_id=run_id,
        batch=batch,
    )
    _write_json_atomic(
        Path("research/history") / run_id / "batches" / str(batch["batch_id"]) / "run_batch_manifest.v1.json",
        payload,
    )


def _write_batch_recovery_state(
    *,
    run_id: str,
    batch: dict,
    candidates: list[dict],
    screening_records: list[dict],
    rows: list[dict],
    evaluations: list[dict],
    walk_forward_reports: list[dict],
) -> None:
    candidate_ids = {str(candidate_id) for candidate_id in batch.get("candidate_ids") or []}
    candidate_snapshots = [
        copy.deepcopy(candidate)
        for candidate in candidates
        if str(candidate["candidate_id"]) in candidate_ids
    ]
    screening_subset = [
        copy.deepcopy(record)
        for record in screening_records
        if str(record["candidate_id"]) in candidate_ids
    ]
    row_keys = {
        (str(candidate["strategy_name"]), str(candidate["asset"]), str(candidate["interval"]))
        for candidate in candidate_snapshots
    }
    payload = build_batch_recovery_state_payload(
        source_run_id=run_id,
        batch=batch,
        candidate_snapshots=candidate_snapshots,
        screening_records=screening_subset,
        rows=[
            copy.deepcopy(row)
            for row in rows
            if (
                str(row.get("strategy_name") or ""),
                str(row.get("asset") or ""),
                str(row.get("interval") or ""),
            ) in row_keys
        ],
        evaluations=[
            copy.deepcopy(item)
            for item in evaluations
            if (
                str(item.get("row", {}).get("strategy_name") or ""),
                str(item.get("row", {}).get("asset") or ""),
                str(item.get("row", {}).get("interval") or ""),
            ) in row_keys
        ],
        walk_forward_reports=[
            copy.deepcopy(item)
            for item in walk_forward_reports
            if (
                str(item.get("strategy_name") or ""),
                str(item.get("asset") or ""),
                str(item.get("interval") or ""),
            ) in row_keys
        ],
    )
    write_batch_recovery_state(
        history_root=Path("research/history"),
        run_id=run_id,
        payload=payload,
        write_json_atomic=_write_json_atomic,
    )


def _load_previous_run_artifacts() -> dict[str, dict | None]:
    return {
        "state": _read_json_if_exists(RUN_STATE_PATH),
        "manifest": _read_json_if_exists(RUN_MANIFEST_PATH),
        "batches": _read_json_if_exists(RUN_BATCHES_PATH),
    }


def _campaign_source_artifacts() -> dict[str, str]:
    return {
        "run_batches_path": RUN_BATCHES_PATH.as_posix(),
        "run_candidates_path": RUN_CANDIDATES_PATH.as_posix(),
        "run_screening_candidates_path": RUN_SCREENING_CANDIDATES_PATH.as_posix(),
    }


def _persist_campaign_artifacts(
    *,
    run_id: str,
    started_at: str | None,
    batches: list[dict],
    candidate_payload: dict | None,
    screening_payload: dict | None,
    finished_at: str | None = None,
    lifecycle_mode: str = "fresh",
    resumed_from_run_id: str | None = None,
    continuation_summary: dict | None = None,
) -> tuple[dict, dict]:
    generated_at_utc = datetime.now(UTC)
    campaign_id = build_campaign_id(run_id=run_id)
    latest_payload = build_run_campaign_payload(
        campaign_id=campaign_id,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        started_at=started_at,
        finished_at=finished_at,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
        source_artifacts=_campaign_source_artifacts(),
    )
    latest_payload["lifecycle_mode"] = lifecycle_mode
    latest_payload["resumed_from_run_id"] = resumed_from_run_id
    latest_payload["continuation_summary"] = copy.deepcopy(continuation_summary or {})
    latest_payload["col_campaign_id"] = _COL_CAMPAIGN_ID
    _write_json_with_history(
        path=RUN_CAMPAIGN_PATH,
        payload=latest_payload,
        run_id=run_id,
        history_name="run_campaign_manifest.v1.json",
    )
    progress_payload = build_run_campaign_progress_payload(
        campaign_id=campaign_id,
        run_id=run_id,
        generated_at_utc=generated_at_utc,
        started_at=started_at,
        finished_at=finished_at,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
    )
    progress_payload["lifecycle_mode"] = lifecycle_mode
    progress_payload["resumed_from_run_id"] = resumed_from_run_id
    progress_payload["continuation_summary"] = copy.deepcopy(continuation_summary or {})
    progress_payload["col_campaign_id"] = _COL_CAMPAIGN_ID
    _write_json_atomic(RUN_CAMPAIGN_PROGRESS_PATH, progress_payload)
    return latest_payload, progress_payload


def _batch_progress_payload(*, batch: dict | None, total_batches: int) -> dict | None:
    if batch is None:
        return None
    return {
        "batch_id": batch.get("batch_id"),
        "batch_index": batch.get("batch_index"),
        "total_batches": int(total_batches),
        "strategy_family": batch.get("strategy_family"),
        "interval": batch.get("interval"),
        "status": batch.get("status"),
        "current_stage": batch.get("current_stage"),
        "completed_candidates": int(batch.get("completed_candidate_count") or 0),
        "total_candidates": int(batch.get("candidate_count") or 0),
        "elapsed_seconds": int(batch.get("elapsed_seconds") or 0),
    }


def _batch_stage(batch: dict) -> str:
    stage = str(batch.get("current_stage") or "screening")
    return stage if stage in {"screening", "validation"} else "screening"


def _batch_needs_screening(batch: dict) -> bool:
    return str(batch.get("status") or "") == "pending" and _batch_stage(batch) == "screening"


def _batch_ready_for_validation(batch: dict) -> bool:
    return str(batch.get("status") or "") == "pending" and _batch_stage(batch) == "validation"


def _mark_batch_pending_validation(batch: dict) -> None:
    batch["status"] = "pending"
    batch["current_stage"] = "validation"
    batch["finished_at"] = None


def _candidate_index(candidates: list[dict]) -> dict[str, dict]:
    return {
        str(candidate["candidate_id"]): candidate
        for candidate in candidates
    }


def _apply_candidate_updates(*, candidates_by_id: dict[str, dict], updates: list[dict]) -> None:
    for update in updates:
        candidate = candidates_by_id.get(str(update["candidate_id"]))
        if candidate is None:
            continue
        for key, value in update.items():
            if key == "candidate_id":
                continue
            candidate[key] = value


def _apply_screening_record_updates(*, screening_records_by_id: dict[str, dict], records: list[dict]) -> None:
    for record in records:
        existing = screening_records_by_id.get(str(record["candidate_id"]))
        if existing is None:
            continue
        existing.update(record)


def _apply_batch_result(*, target_batch: dict, source_batch: dict) -> None:
    target_batch.update(source_batch)


def _mark_later_batches_skipped(*, run_id: str, batches: list[dict], failed_batch: dict) -> None:
    for later_batch in batches:
        if later_batch["batch_index"] <= failed_batch["batch_index"] or later_batch["status"] != "pending":
            continue
        later_batch["status"] = "skipped"
        later_batch["reason_code"] = "upstream_batch_failed"
        later_batch["reason_detail"] = f"skipped after failed batch {failed_batch['batch_id']}"
        later_batch["error_type"] = None
        _write_batch_manifest(run_id=run_id, batch=later_batch)


def _submit_parallel_batch(
    *,
    executor,
    future_by_batch_id: dict[str, object],
    batch: dict,
    worker,
    worker_kwargs: dict,
) -> None:
    future_by_batch_id[str(batch["batch_id"])] = executor.submit(
        worker,
        batch=copy.deepcopy(batch),
        **worker_kwargs,
    )


def _screening_progress_payload(
    *,
    completed_candidates: int,
    total_candidates: int,
    record: dict | None,
) -> dict:
    return {
        "completed_screening_candidates": int(completed_candidates),
        "total_screening_candidates": int(total_candidates),
        "candidate_id": None if record is None else record.get("candidate_id"),
        "runtime_status": None if record is None else record.get("runtime_status"),
        "final_status": None if record is None else record.get("final_status"),
        "samples_completed": None if record is None else record.get("samples_completed"),
        "samples_total": None if record is None else record.get("samples_total"),
        "budget_seconds": None if record is None else record.get("budget_seconds"),
        "candidate_elapsed_seconds": None if record is None else record.get("elapsed_seconds"),
    }


def _merge_screening_batch_result(
    *,
    result: dict,
    batch: dict,
    batches: list[dict],
    candidates_by_id: dict[str, dict],
    screening_records_by_id: dict[str, dict],
    candidates: list[dict],
    screening_records: list[dict],
    screening_completed: int,
    screening_items_count: int,
    run_id: str,
    started_at_utc: str,
    as_of_utc: datetime,
    tracker: ProgressTracker,
    provenance_events: list,
    lifecycle_mode: str,
    resumed_from_run_id: str | None,
    continuation_summary: dict[str, int],
) -> tuple[dict, dict, int]:
    _apply_batch_result(target_batch=batch, source_batch=result["batch"])
    _apply_candidate_updates(candidates_by_id=candidates_by_id, updates=result["candidate_updates"])
    _apply_screening_record_updates(
        screening_records_by_id=screening_records_by_id,
        records=result["screening_records"],
    )

    candidate_payload, _ = _persist_candidate_pipeline_sidecars(
        run_id=run_id,
        as_of_utc=as_of_utc,
        candidates=candidates,
    )
    screening_payload = _persist_screening_candidate_sidecar(
        run_id=run_id,
        as_of_utc=as_of_utc,
        screening_records=screening_records,
    )
    _persist_run_batches_sidecar(
        run_id=run_id,
        as_of_utc=as_of_utc,
        batches=batches,
    )
    _write_batch_manifest(run_id=run_id, batch=batch)
    _persist_campaign_artifacts(
        run_id=run_id,
        started_at=started_at_utc,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
        lifecycle_mode=lifecycle_mode,
        resumed_from_run_id=resumed_from_run_id,
        continuation_summary=continuation_summary,
    )
    if batch["status"] in {"completed", "partial", "pending"}:
        _write_batch_recovery_state(
            run_id=run_id,
            batch=batch,
            candidates=candidates,
            screening_records=screening_records,
            rows=[],
            evaluations=[],
            walk_forward_reports=[],
        )

    for event in result["events"]:
        tracker.emit_event(event.pop("event"), **event)
    provenance_events.extend(result.get("provenance_events", []))

    screening_completed += int(result["completed_candidates"])
    tracker.advance(completed=screening_completed, total=screening_items_count)
    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
    tracker.set_screening(
        _screening_progress_payload(
            completed_candidates=screening_completed,
            total_candidates=screening_items_count,
            record=result.get("last_record"),
        ),
        persist=True,
    )

    if batch["status"] == "partial":
        tracker.emit_event(
            "batch_partial",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
            reason_code=batch["reason_code"],
        )
    elif batch["status"] == "completed":
        tracker.emit_event(
            "batch_completed",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
        )
    elif batch["status"] == "failed":
        tracker.emit_event(
            "batch_failed",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
            reason_code=batch["reason_code"],
            reason_detail=batch["reason_detail"],
        )

    return candidate_payload, screening_payload, screening_completed


def _merge_validation_batch_result(
    *,
    result: dict,
    batch: dict,
    batches: list[dict],
    candidates_by_id: dict[str, dict],
    candidates: list[dict],
    screening_records: list[dict],
    rows: list[dict],
    evaluations: list[dict],
    walk_forward_reports: list[dict],
    validation_completed: int,
    validation_items_count: int,
    run_id: str,
    started_at_utc: str,
    as_of_utc: datetime,
    screening_payload: dict | None,
    tracker: ProgressTracker,
    provenance_events: list,
    lifecycle_mode: str,
    resumed_from_run_id: str | None,
    continuation_summary: dict[str, int],
) -> tuple[dict, int]:
    _apply_batch_result(target_batch=batch, source_batch=result["batch"])
    _apply_candidate_updates(candidates_by_id=candidates_by_id, updates=result["candidate_updates"])
    rows.extend(result["rows"])
    evaluations.extend(result["evaluations"])
    walk_forward_reports.extend(result["walk_forward_reports"])
    provenance_events.extend(result.get("provenance_events", []))

    candidate_payload, _ = _persist_candidate_pipeline_sidecars(
        run_id=run_id,
        as_of_utc=as_of_utc,
        candidates=candidates,
    )
    _persist_run_batches_sidecar(
        run_id=run_id,
        as_of_utc=as_of_utc,
        batches=batches,
    )
    _write_batch_manifest(run_id=run_id, batch=batch)
    _persist_campaign_artifacts(
        run_id=run_id,
        started_at=started_at_utc,
        batches=batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
        lifecycle_mode=lifecycle_mode,
        resumed_from_run_id=resumed_from_run_id,
        continuation_summary=continuation_summary,
    )
    if batch["status"] in {"completed", "partial"}:
        _write_batch_recovery_state(
            run_id=run_id,
            batch=batch,
            candidates=candidates,
            screening_records=screening_records,
            rows=result["rows"],
            evaluations=result["evaluations"],
            walk_forward_reports=result["walk_forward_reports"],
        )

    validation_completed += int(result["completed_candidates"])
    tracker.advance(completed=validation_completed, total=validation_items_count)
    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)

    if batch["status"] == "partial":
        tracker.emit_event(
            "batch_partial",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
            reason_code=batch["reason_code"],
        )
    elif batch["status"] == "completed":
        tracker.emit_event(
            "batch_completed",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
        )
    elif batch["status"] == "failed":
        tracker.emit_event(
            "batch_failed",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=batch["elapsed_seconds"],
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
            reason_code=batch["reason_code"],
            reason_detail=batch["reason_detail"],
        )

    return candidate_payload, validation_completed


def _inline_on_batch_complete(batch: dict, _result: object) -> BatchOutcome:
    """v3.9 phase 6: explicit `on_batch_complete` hook for inline
    dispatch.

    Inline batches carry their own exception handling inside the
    per-batch closure (the closure sets ``batch["status"] = "failed"``
    and re-raises on error, which `Orchestrator.dispatch_serial_batches`
    catches). This hook translates the closure's final ``batch["status"]``
    into a typed ``BatchOutcome``.

    Serial dispatch does not act on the outcome for flow control
    (failures propagate via the re-raised exception). The hook exists
    to make the inline path's outcome contract explicit at the call
    site - removing the Phase-5 implicit dependency on
    `orchestration.orchestrator._default_complete` that was pinned
    open at Phase-5 exit and closed by Phase 6
    (`tests/unit/test_orchestration_default_complete_scope.py`).
    """

    if batch.get("status") == "failed":
        return BatchOutcome.failure(
            reason_code=classify_batch_reason(batch.get("reason_code")),
            message=str(batch.get("reason_detail") or ""),
        )
    return BatchOutcome.success()


def _run_parallel_screening_batches(
    *,
    orchestrator: Orchestrator,
    batches: list[dict],
    screening_items: list[dict],
    interval_ranges: dict[str, dict[str, str]],
    evaluation_config: dict,
    regime_config: dict | None,
    screening_candidate_budget_seconds: int,
    run_id: str,
    started_at_utc: str,
    as_of_utc: datetime,
    tracker: ProgressTracker,
    candidates: list[dict],
    candidate_payload: dict | None,
    screening_payload: dict | None,
    screening_records: list[dict],
    screening_records_by_id: dict[str, dict],
    screening_completed: int,
    execution_max_workers: int,
    provenance_events: list,
    lifecycle_mode: str,
    resumed_from_run_id: str | None,
    continuation_summary: dict[str, int],
) -> tuple[dict | None, dict | None, int, set[str]]:
    """Route parallel screening through the v3.9 Orchestrator.

    The batch-dispatch loop (rolling-submit, in-order result
    collection, stop-on-failure) lives in
    `orchestration.Orchestrator.dispatch_parallel_batches`. This
    function supplies the pre-submit hook (batch state + sidecars +
    tracker events), the per-batch task payload builder, and the
    post-submit merge hook, all of which were the v3.8 inline logic.
    """

    screening_batches = [batch for batch in batches if _batch_needs_screening(batch)]
    candidate_lookup = _candidate_index(candidates)
    items_by_batch_id = {
        str(batch["batch_id"]): [
            candidate for candidate in screening_items if str(candidate["candidate_id"]) in {str(candidate_id) for candidate_id in batch["candidate_ids"]}
        ]
        for batch in screening_batches
    }
    failed_batch_ids: set[str] = set()
    state_box = {
        "candidate_payload": candidate_payload,
        "screening_payload": screening_payload,
        "screening_completed": screening_completed,
    }

    def _on_start(batch: dict) -> None:
        batch["status"] = "running"
        batch["current_stage"] = "screening"
        batch["started_at"] = batch.get("started_at") or datetime.now(UTC).isoformat()
        tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
        _persist_run_batches_sidecar(run_id=run_id, as_of_utc=as_of_utc, batches=batches)
        _write_batch_manifest(run_id=run_id, batch=batch)
        _persist_campaign_artifacts(
            run_id=run_id,
            started_at=started_at_utc,
            batches=batches,
            candidate_payload=state_box["candidate_payload"],
            screening_payload=state_box["screening_payload"],
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )
        tracker.emit_event(
            "batch_started",
            batch_id=batch["batch_id"],
            batch_index=batch["batch_index"],
            strategy_family=batch["strategy_family"],
            interval=batch["interval"],
            elapsed_seconds=0,
            candidate_count=batch["candidate_count"],
            completed_candidate_count=batch["completed_candidate_count"],
        )

    def _payload_for(batch: dict) -> dict:
        # Deepcopy matches v3.8 `_submit_parallel_batch` behavior
        # (the batch dict that travels to the worker is decoupled
        # from the submit-side batch reference).
        return {
            "batch": deepcopy_batch(batch),
            "batch_candidates": items_by_batch_id[str(batch["batch_id"])],
            "interval_ranges": interval_ranges,
            "evaluation_config": evaluation_config,
            "regime_config": regime_config,
            "screening_candidate_budget_seconds": screening_candidate_budget_seconds,
            "screening_param_sample_limit": SCREENING_PARAM_SAMPLE_LIMIT,
        }

    def _on_complete(batch: dict, result: dict | None) -> BatchOutcome:
        """Phase 5: translate the research-semantic batch result into
        a typed BatchOutcome. The Orchestrator drives
        stop_on_failure from the returned outcome (it no longer
        inspects `batch["status"]`)."""

        if result is None:
            # Phase 4/5 batch kinds do not emit None results on
            # success; this branch fires only when the worker
            # returned a typed TaskFailure (per-candidate kinds) or
            # the dispatch observed a protocol violation. Mark the
            # batch failed for the runner's own failure-tracking
            # (downstream skip logic still reads batch state) and
            # return a typed failure outcome to the dispatch.
            batch["status"] = "failed"
            failed_batch_ids.add(str(batch["batch_id"]))
            return BatchOutcome.failure(
                reason_code=classify_batch_reason(batch.get("reason_code")),
                message=str(batch.get("reason_detail") or "worker returned no result"),
            )
        cp, sp, sc = _merge_screening_batch_result(
            result=result,
            batch=batch,
            batches=batches,
            candidates_by_id=candidate_lookup,
            screening_records_by_id=screening_records_by_id,
            candidates=candidates,
            screening_records=screening_records,
            screening_completed=state_box["screening_completed"],
            screening_items_count=len(screening_items),
            run_id=run_id,
            started_at_utc=started_at_utc,
            as_of_utc=as_of_utc,
            tracker=tracker,
            provenance_events=provenance_events,
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )
        state_box["candidate_payload"] = cp
        state_box["screening_payload"] = sp
        state_box["screening_completed"] = sc
        if batch["status"] == "failed":
            failed_batch_ids.add(str(batch["batch_id"]))
            return BatchOutcome.failure(
                reason_code=classify_batch_reason(batch.get("reason_code")),
                message=str(batch.get("reason_detail") or ""),
            )
        return BatchOutcome.success()

    orchestrator.dispatch_parallel_batches(
        batches=screening_batches,
        kind=TaskKind.SCREENING_BATCH,
        max_workers=execution_max_workers,
        task_payload_for=_payload_for,
        on_batch_starting=_on_start,
        on_batch_complete=_on_complete,
        stop_on_failure=True,
        # Honor the module-level BATCH_EXECUTOR_CLASS so tests can
        # monkey-patch in ThreadPoolExecutor for in-process dispatch.
        # Production config is ProcessPoolExecutor; see v3.8 baseline.
        executor_class=BATCH_EXECUTOR_CLASS,
    )

    if failed_batch_ids:
        first_failed = next(batch for batch in batches if str(batch["batch_id"]) in failed_batch_ids)
        _mark_later_batches_skipped(run_id=run_id, batches=batches, failed_batch=first_failed)
        _persist_run_batches_sidecar(run_id=run_id, as_of_utc=as_of_utc, batches=batches)
        _persist_campaign_artifacts(
            run_id=run_id,
            started_at=started_at_utc,
            batches=batches,
            candidate_payload=state_box["candidate_payload"],
            screening_payload=state_box["screening_payload"],
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )

    return (
        state_box["candidate_payload"],
        state_box["screening_payload"],
        state_box["screening_completed"],
        failed_batch_ids,
    )


def _run_parallel_validation_batches(
    *,
    orchestrator: Orchestrator,
    batches: list[dict],
    validation_items: list[dict],
    candidate_to_batch_id: dict[str, str],
    interval_ranges: dict[str, dict[str, str]],
    evaluation_config: dict,
    regime_config: dict | None,
    as_of_utc: datetime,
    run_id: str,
    started_at_utc: str,
    screening_payload: dict | None,
    tracker: ProgressTracker,
    candidates: list[dict],
    candidate_payload: dict | None,
    rows: list[dict],
    evaluations: list[dict],
    walk_forward_reports: list[dict],
    validation_completed: int,
    execution_max_workers: int,
    provenance_events: list,
    screening_records: list[dict],
    lifecycle_mode: str,
    resumed_from_run_id: str | None,
    continuation_summary: dict[str, int],
) -> tuple[dict | None, int, set[str]]:
    """Route parallel validation through the v3.9 Orchestrator.

    Same pattern as `_run_parallel_screening_batches`: the batch
    dispatch loop lives in `Orchestrator.dispatch_parallel_batches`;
    this function supplies the pre-submit hook, task payload
    builder, and merge hook that were v3.8 inline logic.
    """
    validation_batches = [
        batch for batch in batches if _batch_ready_for_validation(batch)
    ]
    candidate_lookup = _candidate_index(candidates)
    items_by_batch_id = {
        str(batch["batch_id"]): [
            candidate
            for candidate in validation_items
            if candidate_to_batch_id.get(str(candidate["candidate_id"])) == str(batch["batch_id"])
        ]
        for batch in validation_batches
    }
    failed_batch_ids: set[str] = set()
    state_box = {
        "candidate_payload": candidate_payload,
        "validation_completed": validation_completed,
    }

    def _on_start(batch: dict) -> None:
        batch["status"] = "running"
        batch["current_stage"] = "validation"
        batch["started_at"] = batch.get("started_at") or datetime.now(UTC).isoformat()
        tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
        _persist_run_batches_sidecar(run_id=run_id, as_of_utc=as_of_utc, batches=batches)
        _write_batch_manifest(run_id=run_id, batch=batch)
        _persist_campaign_artifacts(
            run_id=run_id,
            started_at=started_at_utc,
            batches=batches,
            candidate_payload=state_box["candidate_payload"],
            screening_payload=screening_payload,
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )

    def _payload_for(batch: dict) -> dict:
        return {
            "batch": deepcopy_batch(batch),
            "batch_candidates": items_by_batch_id[str(batch["batch_id"])],
            "interval_ranges": interval_ranges,
            "evaluation_config": evaluation_config,
            "regime_config": regime_config,
            "as_of_utc": as_of_utc,
        }

    def _on_complete(batch: dict, result: dict | None) -> BatchOutcome:
        """Phase 5: return a typed BatchOutcome that the Orchestrator
        uses to drive stop_on_failure."""

        if result is None:
            batch["status"] = "failed"
            failed_batch_ids.add(str(batch["batch_id"]))
            return BatchOutcome.failure(
                reason_code=classify_batch_reason(batch.get("reason_code")),
                message=str(batch.get("reason_detail") or "worker returned no result"),
            )
        cp, vc = _merge_validation_batch_result(
            result=result,
            batch=batch,
            batches=batches,
            candidates_by_id=candidate_lookup,
            candidates=candidates,
            screening_records=screening_records,
            rows=rows,
            evaluations=evaluations,
            walk_forward_reports=walk_forward_reports,
            validation_completed=state_box["validation_completed"],
            validation_items_count=len(validation_items),
            run_id=run_id,
            started_at_utc=started_at_utc,
            as_of_utc=as_of_utc,
            screening_payload=screening_payload,
            tracker=tracker,
            provenance_events=provenance_events,
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )
        state_box["candidate_payload"] = cp
        state_box["validation_completed"] = vc
        if batch["status"] == "failed":
            failed_batch_ids.add(str(batch["batch_id"]))
            return BatchOutcome.failure(
                reason_code=classify_batch_reason(batch.get("reason_code")),
                message=str(batch.get("reason_detail") or ""),
            )
        return BatchOutcome.success()

    orchestrator.dispatch_parallel_batches(
        batches=validation_batches,
        kind=TaskKind.VALIDATION_BATCH,
        max_workers=execution_max_workers,
        task_payload_for=_payload_for,
        on_batch_starting=_on_start,
        on_batch_complete=_on_complete,
        stop_on_failure=True,
        # Honor the module-level BATCH_EXECUTOR_CLASS so tests can
        # monkey-patch in ThreadPoolExecutor for in-process dispatch.
        executor_class=BATCH_EXECUTOR_CLASS,
    )

    if failed_batch_ids:
        first_failed = next(batch for batch in batches if str(batch["batch_id"]) in failed_batch_ids)
        _mark_later_batches_skipped(run_id=run_id, batches=batches, failed_batch=first_failed)
        _persist_run_batches_sidecar(run_id=run_id, as_of_utc=as_of_utc, batches=batches)
        _persist_campaign_artifacts(
            run_id=run_id,
            started_at=started_at_utc,
            batches=batches,
            candidate_payload=state_box["candidate_payload"],
            screening_payload=screening_payload,
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            continuation_summary=continuation_summary,
        )

    return (
        state_box["candidate_payload"],
        state_box["validation_completed"],
        failed_batch_ids,
    )


def _result_row_sort_key(row: dict) -> tuple[str, str, str, str, str]:
    return (
        str(row["strategy_name"]),
        str(row["asset"]),
        str(row["interval"]),
        str(row["params_json"]),
        str(row["error"]),
    )


def _elapsed_from_started_at(started_at: str | None) -> int:
    if not started_at:
        return 0
    return max(0, int(round((datetime.now(UTC) - datetime.fromisoformat(started_at)).total_seconds())))


def _write_public_artifact_status_sidecar(
    *,
    outcome: str,
    run_id: str | None,
    attempted_at_utc: str,
    preset_name: str | None,
    failure_stage: str | None = None,
    path: Path = PUBLIC_ARTIFACT_STATUS_PATH,
) -> dict | None:
    """Emit the v3.15.1 freshness sidecar.

    Write failures are logged via the caller's tracker but must never
    block the run — this is an observability artifact, not a gate.
    """
    existing = read_public_artifact_status(path)
    payload = build_public_artifact_status(
        outcome=outcome,  # type: ignore[arg-type]
        run_id=str(run_id) if run_id is not None else "",
        attempted_at_utc=attempted_at_utc,
        preset=preset_name,
        failure_stage=failure_stage,
        existing=existing,
    )
    write_public_artifact_status(payload, path=path)
    return payload


def _raise_degenerate_run(
    *,
    as_of_utc,
    failure_stage: str,
    assets: list,
    intervals: list[str],
    interval_ranges: dict[str, dict[str, str]],
    pair_diagnostics: list[dict],
    evaluations_count: int = 0,
    evaluations_with_oos_daily_returns: int = 0,
    run_id: str | None = None,
    preset_name: str | None = None,
    tracker: Any | None = None,
) -> None:
    payload = _write_empty_run_diagnostics_sidecar(
        as_of_utc=as_of_utc,
        failure_stage=failure_stage,
        assets=assets,
        intervals=intervals,
        interval_ranges=interval_ranges,
        pair_diagnostics=pair_diagnostics,
        evaluations_count=evaluations_count,
        evaluations_with_oos_daily_returns=evaluations_with_oos_daily_returns,
    )
    try:
        _write_public_artifact_status_sidecar(
            outcome="degenerate",
            run_id=run_id,
            attempted_at_utc=as_of_utc.isoformat(),
            preset_name=preset_name,
            failure_stage=failure_stage,
        )
    except Exception as status_exc:
        if tracker is not None:
            try:
                tracker.emit_event(
                    "public_artifact_status_sidecar_failed",
                    error=str(status_exc),
                    outcome="degenerate",
                    failure_stage=failure_stage,
                )
            except Exception:
                pass
    # v3.15.3.1 audit-sidecar hotfix: the strategy hypothesis catalog +
    # campaign metadata sidecars are pure descriptions of static config —
    # they must be written even when a run terminates as
    # degenerate / no-survivor so the COL audit trail is never missing
    # the catalog snapshot at the moment of the rejection. Mirrors the
    # public_artifact_status pattern above: best-effort with tracker
    # event on failure, never blocks the original DegenerateResearchRunError.
    try:
        write_catalog_sidecar(
            generated_at_utc=as_of_utc,
            git_revision=_git_revision(),
            run_id=run_id,
        )
        write_campaign_metadata_sidecar(
            generated_at_utc=as_of_utc,
            git_revision=_git_revision(),
            run_id=run_id,
        )
    except Exception as v3_15_3_exc:
        if tracker is not None:
            try:
                tracker.emit_event(
                    "v3_15_3_hypothesis_catalog_sidecars_failed",
                    error=str(v3_15_3_exc),
                    outcome="degenerate",
                    failure_stage=failure_stage,
                )
            except Exception:
                pass
    raise DegenerateResearchRunError(payload["message"])

def run_research(
    *,
    resume: bool = False,
    retry_failed_batches: bool = False,
    continue_latest: bool = False,
    preset: str | None = None,
    col_campaign_id: str | None = None,
):
    if continue_latest and resume:
        raise RuntimeError("continue-latest cannot be combined with explicit resume")
    # v3.15.2: stash the breadcrumb for artifact writers below. Additive
    # only; downstream behaviour is unchanged when the kwarg is None.
    global _COL_CAMPAIGN_ID
    _COL_CAMPAIGN_ID = col_campaign_id
    preset_obj: ResearchPreset | None = None
    if preset is not None:
        preset_obj = get_preset(preset)
        if not preset_obj.enabled:
            raise RuntimeError(
                f"preset {preset!r} is disabled (status={preset_obj.status!r}); "
                f"backlog_reason={preset_obj.backlog_reason!r}"
            )

    lifecycle = RunStateStore(
        state_path=RUN_STATE_PATH,
        history_root=Path("research/history"),
    )
    previous_run_artifacts = {"state": None, "manifest": None, "batches": None}
    requested_resumed_from_run_id = None
    continue_latest_resolution: dict | None = None
    if continue_latest:
        lifecycle.repair_stale_run()
        preview_research_config = load_research_config()
        preview_execution_settings = _resolve_execution_settings(preview_research_config)
        latest_artifacts = _load_previous_run_artifacts()
        continue_latest_resolution = resolve_continue_latest_policy(
            state_payload=latest_artifacts.get("state"),
            manifest_payload=latest_artifacts.get("manifest"),
            batches_payload=latest_artifacts.get("batches"),
            retry_failed_batches=retry_failed_batches,
            execution_mode=str(preview_execution_settings["execution_mode"]),
        )
        resume = bool(continue_latest_resolution["resume"])
        retry_failed_batches = bool(continue_latest_resolution["retry_failed_batches"])
        if resume:
            previous_run_artifacts = latest_artifacts
            requested_resumed_from_run_id = continue_latest_resolution.get("source_run_id")
    elif resume:
        previous_run_artifacts = _load_previous_run_artifacts()
        if isinstance(previous_run_artifacts.get("manifest"), dict):
            requested_resumed_from_run_id = str(previous_run_artifacts["manifest"].get("run_id") or "") or None
        preview_research_config = load_research_config()
        preview_execution_settings = _resolve_execution_settings(preview_research_config)
        compatibility = validate_continuation_compatibility(
            state_payload=previous_run_artifacts.get("state"),
            manifest_payload=previous_run_artifacts.get("manifest"),
            batches_payload=previous_run_artifacts.get("batches"),
            retry_failed_batches=retry_failed_batches,
            execution_mode=str(preview_execution_settings["execution_mode"]),
            context_label="resume",
        )
        requested_resumed_from_run_id = compatibility.get("source_run_id")
    state = lifecycle.start_run(
        progress_path=RUN_PROGRESS_PATH,
        manifest_path=RUN_MANIFEST_PATH,
        log_dir=RUN_LOG_DIR,
        heartbeat_timeout_s=RUN_HEARTBEAT_TIMEOUT_S,
        stage="starting",
        status_reason="research_run_started",
    )
    # v3.15.2: additive linkage so the campaign launcher can reconcile this
    # subprocess back to its parent COL campaign. Null when absent.
    state["col_campaign_id"] = _COL_CAMPAIGN_ID
    _write_json_atomic(RUN_STATE_PATH, state)
    started_at_utc = datetime.fromisoformat(state["started_at_utc"])
    # v3.9 phase 4: Orchestrator owns dispatch for both inline and
    # parallel modes. Its Scheduler + Queue track pending / in-flight /
    # completed / failed state across the run; parallel dispatch uses
    # an internal ProcessPoolBackend sized per dispatch call. The
    # default InlineBackend field is unused for dispatch in phase 4
    # (inline mode uses dispatch_serial_batches with callbacks, not
    # worker Tasks).
    orchestrator = Orchestrator(run_id=str(state["run_id"]))
    tracker = ProgressTracker(
        path=RUN_PROGRESS_PATH,
        lifecycle=lifecycle,
        run_id=state["run_id"],
        started_at_utc=started_at_utc,
        manifest_path=RUN_MANIFEST_PATH,
        log_path=Path(state["log_path"]),
    )
    rows: list[dict] = []
    evaluations: list[dict] = []
    walk_forward_reports: list[dict] = []
    provenance_events: list = []
    pair_diagnostics: list[dict] = []
    interval_ranges: dict[str, dict[str, str]] = {}
    candidates: list[dict] = []
    batches: list[dict] = []
    integrity_checks: list[IntegrityCheck] = []
    candidate_payload: dict | None = None
    screening_payload: dict | None = None
    lifecycle_mode = "resume" if resume else "fresh"
    resumed_from_run_id = requested_resumed_from_run_id
    continuation_summary = {
        "fresh_batch_count": 0,
        "reused_terminal_batch_count": 0,
        "resumed_pending_batch_count": 0,
        "resumed_stale_batch_count": 0,
        "retried_failed_batch_count": 0,
    }
    recovery_policy = default_recovery_policy(heartbeat_timeout_s=RUN_HEARTBEAT_TIMEOUT_S)
    try:
        # v3.15.4: cross-module bridge invariant — every active_discovery
        # hypothesis in the catalog must have a stable+enabled preset
        # whose bundle resolves to >=1 enabled registry strategy. Runs
        # once per invocation; not at module import to keep catalog ↔
        # presets one-directional. Fails fast before any preset / config
        # work happens.
        try:
            validate_active_discovery_preset_bridges()
        except HypothesisCatalogError as exc:
            tracker.emit_event(
                "active_discovery_preset_bridge_violation",
                error=str(exc),
            )
            raise
        if preset_obj is not None:
            _enforce_preset_validation(preset_obj, tracker)
            # v3.15.6: emit run-level screening_phase visibility event.
            # Run-level only — per-candidate event lives at the
            # screening-call site (see _run_screening_phase_observed_event).
            tracker.emit_event(
                "screening_phase_active",
                preset_name=preset_obj.name,
                screening_phase=preset_obj.screening_phase,
            )
        research_config = load_research_config()
        execution_settings = _resolve_execution_settings(research_config)
        execution_max_workers = int(execution_settings["max_workers"])
        regime_count, regime_count_source = regime_count_settings(research_config)
        evaluation_config = normalize_evaluation_config(research_config.get("evaluation"))
        screening_config = research_config.get("screening") or {}
        screening_candidate_budget_seconds = max(
            0,
            int(screening_config.get("candidate_budget_seconds", DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS)),
        )
        # v3.14.1: preset.universe is load-bearing for preset-runs. The
        # config ``research.universe`` stanza is only consulted when no
        # preset is active — this stops preset-driven runs from silently
        # resolving to ``crypto_major`` when the preset actually specifies
        # an equity universe. See docs/handoffs/v3.15-to-v3.16.md §4.
        if preset_obj is not None:
            assets, intervals, get_date_range, as_of_utc, universe_snapshot = (
                build_research_universe_from_preset(preset_obj, research_config)
            )
            strategies = resolve_preset_bundle(preset_obj)
            if not strategies:
                raise RuntimeError(
                    f"preset {preset_obj.name!r} has no executable strategies"
                )
        else:
            assets, intervals, get_date_range, as_of_utc, universe_snapshot = (
                build_research_universe(research_config)
            )
            strategies = get_enabled_strategies()
        strategy_by_name = {strategy["name"]: strategy for strategy in strategies}

        _write_universe_snapshot_sidecar(universe_snapshot)

        for interval in intervals:
            start_datum, eind_datum = get_date_range(interval)
            interval_ranges[str(interval)] = {"start": start_datum, "end": eind_datum}

        tracker.start_stage("planning")
        planned_candidates = plan_candidates(
            strategies=strategies,
            assets=assets,
            intervals=intervals,
        )
        tracker.write_manifest(
            _build_run_manifest_payload(
                run_id=state["run_id"],
                started_at_utc=started_at_utc,
                research_config=research_config,
                assets=assets,
                intervals=intervals,
                total_candidate_count=len(planned_candidates),
                strategies=strategies,
                universe_snapshot_path=UNIVERSE_SNAPSHOT_PATH,
                screening_candidate_budget_seconds=screening_candidate_budget_seconds,
                execution_settings=execution_settings,
                lifecycle_mode=lifecycle_mode,
                resumed_from_run_id=resumed_from_run_id,
                continuation_summary=continuation_summary,
                recovery_policy=recovery_policy,
                retry_failed_batches=retry_failed_batches,
            )
        )
        if continue_latest_resolution is not None:
            tracker.emit_event(
                "continue_latest_resolved",
                action=str(continue_latest_resolution["action"]),
                resumed_from_run_id=continue_latest_resolution.get("source_run_id"),
                retry_failed_batches=bool(continue_latest_resolution["retry_failed_batches"]),
            )
        tracker.mark_stage_completed(raw_candidate_count=len(planned_candidates))

        tracker.start_stage("dedupe", total=len(planned_candidates))
        candidates, dedupe_summary = deduplicate_candidates(planned_candidates)
        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _merge_manifest(RUN_MANIFEST_PATH, **dedupe_summary)
        tracker.mark_stage_completed(**dedupe_summary)

        tracker.start_stage("fit_prior", total=len(candidates))
        candidates, fit_summary = apply_fit_prior(candidates)
        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _merge_manifest(RUN_MANIFEST_PATH, **fit_summary)
        tracker.mark_stage_completed(
            fit_allowed_count=fit_summary["fit_allowed_count"],
            fit_discouraged_count=fit_summary["fit_discouraged_count"],
            fit_blocked_count=fit_summary["fit_blocked_count"],
        )

        tracker.start_stage("eligibility_filter", total=len(candidates))
        for interval in intervals:
            start_datum = interval_ranges[str(interval)]["start"]
            eind_datum = interval_ranges[str(interval)]["end"]
            engine = _build_engine(
                start_datum=start_datum,
                eind_datum=eind_datum,
                evaluation_config=evaluation_config,
                regime_config=research_config.get("regime_diagnostics"),
            )
            pair_diagnostics.extend(_inspect_engine_readiness(engine, assets, str(interval)))
            provenance_events.extend(getattr(engine, "_provenance_events", []))

        candidates, eligibility_summary = apply_eligibility(
            candidates=candidates,
            readiness_by_pair=index_readiness(pair_diagnostics),
            universe_symbols={asset.symbol if hasattr(asset, "symbol") else str(asset) for asset in assets},
            integrity_checks=integrity_checks,
        )
        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _merge_manifest(RUN_MANIFEST_PATH, **eligibility_summary)
        tracker.mark_stage_completed(
            eligible_candidate_count=eligibility_summary["eligible_candidate_count"],
            eligibility_rejected_count=eligibility_summary["eligibility_rejected_count"],
        )
        if eligibility_summary["eligible_candidate_count"] == 0:
            _raise_degenerate_run(
                as_of_utc=as_of_utc,
                failure_stage="eligibility_no_candidates",
                assets=assets,
                intervals=intervals,
                interval_ranges=interval_ranges,
                pair_diagnostics=pair_diagnostics,
                run_id=str(state["run_id"]),
                preset_name=preset_obj.name if preset_obj else None,
                tracker=tracker,
            )

        tracker.start_stage("screening", total=eligibility_summary["eligible_candidate_count"])
        screening_items = screening_candidates(candidates)
        batches = partition_execution_batches(candidates=screening_items)
        for batch in batches:
            batch["attempt_count"] = 1
            batch["execution_mode"] = str(execution_settings["execution_mode"])
            batch["error_type"] = None
            batch["current_stage"] = "screening"
            batch["last_attempt_reason"] = FRESH_ATTEMPT_REASON
        candidate_to_batch_id = {
            str(candidate_id): str(batch["batch_id"])
            for batch in batches
            for candidate_id in batch["candidate_ids"]
        }
        screening_records = build_screening_runtime_records(
            candidates=screening_items,
            budget_seconds=screening_candidate_budget_seconds,
        )
        recovery_context = prepare_resume_state(
            resume=resume,
            retry_failed_batches=retry_failed_batches,
            heartbeat_timeout_s=RUN_HEARTBEAT_TIMEOUT_S,
            history_root=Path("research/history"),
            state_payload=previous_run_artifacts.get("state"),
            manifest_payload=previous_run_artifacts.get("manifest"),
            batches_payload=previous_run_artifacts.get("batches"),
            planned_batches=batches,
            candidates=candidates,
            screening_records=screening_records,
            rows=rows,
            evaluations=evaluations,
            walk_forward_reports=walk_forward_reports,
            execution_mode=str(execution_settings["execution_mode"]),
        )
        lifecycle_mode = str(recovery_context["lifecycle_mode"])
        resumed_from_run_id = recovery_context.get("resumed_from_run_id")
        continuation_summary = dict(recovery_context["continuation_summary"])
        recovery_policy = dict(recovery_context["recovery_policy"])
        campaign_kwargs = {
            "lifecycle_mode": lifecycle_mode,
            "resumed_from_run_id": resumed_from_run_id,
            "continuation_summary": continuation_summary,
        }
        if resumed_from_run_id is not None:
            tracker.emit_event(
                "run_resumed",
                resumed_from_run_id=resumed_from_run_id,
                continuation_summary=continuation_summary,
                retry_failed_batches=retry_failed_batches,
            )
        screening_records_by_id = {
            str(record["candidate_id"]): record
            for record in screening_records
        }
        screening_completed = sum(
            1
            for record in screening_records
            if record.get("final_status") is not None
        )
        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        screening_payload = _persist_screening_candidate_sidecar(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            screening_records=screening_records,
        )
        _persist_run_batches_sidecar(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            batches=batches,
        )
        for batch in batches:
            _write_batch_manifest(run_id=state["run_id"], batch=batch)
        _merge_manifest(
            RUN_MANIFEST_PATH,
            lifecycle_mode=lifecycle_mode,
            resumed_from_run_id=resumed_from_run_id,
            retry_failed_batches=retry_failed_batches,
            continuation_summary=continuation_summary,
            recovery_policy=recovery_policy,
            batching_enabled=True,
            batch_partitioning={
                "mode": "strategy_family_x_interval",
                "batch_count": len(batches),
            },
            execution={
                "max_workers": execution_max_workers,
                "execution_mode": str(execution_settings["execution_mode"]),
            },
        )
        _persist_campaign_artifacts(
            run_id=state["run_id"],
            started_at=state["started_at_utc"],
            batches=batches,
            candidate_payload=candidate_payload,
            screening_payload=screening_payload,
            **campaign_kwargs,
        )
        tracker.set_batch(None, persist=True)
        tracker.set_screening(
            _screening_progress_payload(
                completed_candidates=screening_completed,
                total_candidates=len(screening_items),
                record=None,
            ),
            persist=True,
        )
        if screening_completed > 0:
            tracker.advance(completed=screening_completed, total=len(screening_items))
        screening_items_by_id = {
            str(candidate["candidate_id"]): candidate
            for candidate in screening_items
        }
        if execution_max_workers > 1:
            # v3.9 phase 4: the parallel screening adapter internally
            # drives dispatch through the Orchestrator
            # (Scheduler + Queue + ProcessPoolBackend).
            candidate_payload, screening_payload, screening_completed, failed_batch_ids = _run_parallel_screening_batches(
                orchestrator=orchestrator,
                batches=batches,
                screening_items=screening_items,
                interval_ranges=interval_ranges,
                evaluation_config=evaluation_config,
                regime_config=research_config.get("regime_diagnostics"),
                screening_candidate_budget_seconds=screening_candidate_budget_seconds,
                run_id=state["run_id"],
                started_at_utc=state["started_at_utc"],
                as_of_utc=as_of_utc,
                tracker=tracker,
                candidates=candidates,
                candidate_payload=candidate_payload,
                screening_payload=screening_payload,
                screening_records=screening_records,
                screening_records_by_id=screening_records_by_id,
                screening_completed=screening_completed,
                execution_max_workers=execution_max_workers,
                provenance_events=provenance_events,
                lifecycle_mode=lifecycle_mode,
                resumed_from_run_id=resumed_from_run_id,
                continuation_summary=continuation_summary,
            )
            if failed_batch_ids:
                failed_batch = next(batch for batch in batches if str(batch["batch_id"]) in failed_batch_ids)
                raise RuntimeError(f"batch execution failed for {failed_batch['batch_id']}: {failed_batch['reason_detail']}")
        def _inline_screening_batch(batch: dict) -> None:
            """Phase 4 inline-screening closure.

            Routed through orchestrator.dispatch_serial_batches so that
            inline mode (max_workers == 1) no longer bypasses the
            Orchestrator. Body is the v3.8 per-batch inline logic
            verbatim; only rebindings of outer-scope payload / counter
            variables are declared nonlocal.
            """

            nonlocal candidate_payload, screening_payload, screening_completed
            batch_started_monotonic = time.monotonic()
            batch["status"] = "running"
            batch["current_stage"] = "screening"
            batch["started_at"] = batch.get("started_at") or datetime.now(UTC).isoformat()
            batch["finished_at"] = None
            tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
            _persist_run_batches_sidecar(run_id=state["run_id"], as_of_utc=as_of_utc, batches=batches)
            _write_batch_manifest(run_id=state["run_id"], batch=batch)
            _persist_campaign_artifacts(
                run_id=state["run_id"],
                started_at=state["started_at_utc"],
                batches=batches,
                candidate_payload=candidate_payload,
                screening_payload=screening_payload,
                **campaign_kwargs,
            )
            tracker.emit_event(
                "batch_started",
                batch_id=batch["batch_id"],
                batch_index=batch["batch_index"],
                strategy_family=batch["strategy_family"],
                interval=batch["interval"],
                elapsed_seconds=0,
                candidate_count=batch["candidate_count"],
                completed_candidate_count=batch["completed_candidate_count"],
            )
            try:
                for candidate_id in batch["candidate_ids"]:
                    candidate = screening_items_by_id[str(candidate_id)]
                    strategy = strategy_by_name[candidate["strategy_name"]]
                    # v3.15.8: build the SamplingPlan once per
                    # candidate so the runtime record's samples_total
                    # and the synthetic timeout/error outcome dicts
                    # below carry consistent coverage metadata. The
                    # plan also flows into the subprocess via
                    # execute_screening_candidate_isolated → _build_child_payload.
                    plan = sampling_plan_for_param_grid(
                        strategy.get("params"),
                        max_samples_for_legacy=SCREENING_PARAM_SAMPLE_LIMIT,
                    )
                    sampling_metadata = plan.metadata()
                    runtime_record = screening_records_by_id[str(candidate["candidate_id"])]
                    runtime_record["runtime_status"] = "running"
                    runtime_record["final_status"] = None
                    runtime_record["started_at"] = datetime.now(UTC).isoformat()
                    runtime_record["finished_at"] = None
                    runtime_record["elapsed_seconds"] = 0
                    runtime_record["samples_completed"] = 0
                    runtime_record["samples_total"] = plan.sampled_count
                    runtime_record["decision"] = None
                    runtime_record["reason_code"] = None
                    runtime_record["reason_detail"] = None
                    tracker.begin_item(
                        strategy=candidate["strategy_name"],
                        asset=candidate["asset"],
                        interval=candidate["interval"],
                    )
                    batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - batch_started_monotonic)))
                    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                    tracker.set_screening(
                        _screening_progress_payload(
                            completed_candidates=screening_completed,
                            total_candidates=len(screening_items),
                            record=runtime_record,
                        ),
                        persist=True,
                    )
                    screening_payload = _persist_screening_candidate_sidecar(
                        run_id=state["run_id"],
                        as_of_utc=as_of_utc,
                        screening_records=screening_records,
                    )
                    _persist_campaign_artifacts(
                        run_id=state["run_id"],
                        started_at=state["started_at_utc"],
                        batches=batches,
                        candidate_payload=candidate_payload,
                        screening_payload=screening_payload,
                        **campaign_kwargs,
                    )
                    tracker.emit_event(
                        "screening_candidate_started",
                        candidate_id=candidate["candidate_id"],
                        strategy=candidate["strategy_name"],
                        asset=candidate["asset"],
                        interval=candidate["interval"],
                        elapsed_seconds=0,
                        samples_completed=0,
                        samples_total=runtime_record["samples_total"],
                    )

                    def _on_screening_progress(progress: dict[str, int]) -> None:
                        runtime_record["elapsed_seconds"] = int(progress["elapsed_seconds"])
                        runtime_record["samples_completed"] = int(progress["samples_completed"])
                        runtime_record["samples_total"] = int(progress["samples_total"])
                        batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - batch_started_monotonic)))
                        tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                        tracker.set_screening(
                            _screening_progress_payload(
                                completed_candidates=screening_completed,
                                total_candidates=len(screening_items),
                                record=runtime_record,
                            ),
                            persist=True,
                        )
                        screening_payload = _persist_screening_candidate_sidecar(
                            run_id=state["run_id"],
                            as_of_utc=as_of_utc,
                            screening_records=screening_records,
                        )
                        _persist_run_batches_sidecar(run_id=state["run_id"], as_of_utc=as_of_utc, batches=batches)
                        _write_batch_manifest(run_id=state["run_id"], batch=batch)
                        _persist_campaign_artifacts(
                            run_id=state["run_id"],
                            started_at=state["started_at_utc"],
                            batches=batches,
                            candidate_payload=candidate_payload,
                            screening_payload=screening_payload,
                            **campaign_kwargs,
                        )
                        tracker.emit_event(
                            "screening_candidate_progress",
                            candidate_id=candidate["candidate_id"],
                            strategy=candidate["strategy_name"],
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            elapsed_seconds=runtime_record["elapsed_seconds"],
                            samples_completed=runtime_record["samples_completed"],
                            samples_total=runtime_record["samples_total"],
                        )

                    # v3.15.6: per-candidate visibility for screening_phase.
                    # Lives only at run_research's call site (the screening
                    # process boundary itself does not emit; batch_execution
                    # has no tracker context).
                    tracker.emit_event(
                        "screening_phase_observed",
                        candidate_id=str(candidate.get("candidate_id")),
                        screening_phase=(
                            preset_obj.screening_phase if preset_obj is not None else None
                        ),
                    )
                    try:
                        start_datum = interval_ranges[candidate["interval"]]["start"]
                        eind_datum = interval_ranges[candidate["interval"]]["end"]
                        isolated_result = execute_screening_candidate_isolated(
                            strategy=strategy,
                            candidate=candidate,
                            interval_range={"start": start_datum, "end": eind_datum},
                            evaluation_config=evaluation_config,
                            regime_config=research_config.get("regime_diagnostics"),
                            budget_seconds=screening_candidate_budget_seconds,
                            max_samples=SCREENING_PARAM_SAMPLE_LIMIT,
                            engine_class=BacktestEngine,
                            on_progress=_on_screening_progress,
                            run_id=state["run_id"],
                            resume_run_id=resumed_from_run_id,
                            batch_id=str(batch["batch_id"]),
                            history_root=Path("research/history"),
                            screening_phase=(
                                preset_obj.screening_phase if preset_obj is not None else None
                            ),
                        )
                        if isolated_result["execution_state"] == "interrupted":
                            # v3.14.1: budget exhaustion is a candidate-level
                            # timeout. The run continues with the next
                            # candidate. A real user KeyboardInterrupt from
                            # outside this block is a BaseException and still
                            # propagates — only the isolated_result
                            # "interrupted" state is handled here.
                            elapsed = int(isolated_result.get("elapsed_seconds") or 0)
                            samples_total = int(isolated_result.get("samples_total") or 0)
                            samples_done = int(isolated_result.get("samples_completed") or 0)
                            runtime_record["elapsed_seconds"] = elapsed
                            runtime_record["samples_total"] = samples_total
                            runtime_record["samples_completed"] = samples_done
                            outcome = {
                                "legacy_decision": {
                                    "status": "rejected_in_screening",
                                    "reason": "candidate_budget_exceeded",
                                    "sampled_combination_count": samples_done,
                                },
                                "runtime_status": "running",
                                "final_status": FINAL_STATUS_TIMED_OUT,
                                "started_at": runtime_record["started_at"],
                                "finished_at": datetime.now(UTC).isoformat(),
                                "elapsed_seconds": elapsed,
                                "samples_total": samples_total,
                                "samples_completed": samples_done,
                                "decision": "rejected_in_screening",
                                "reason_code": "candidate_budget_exceeded",
                                "reason_detail": (
                                    f"screening candidate budget exceeded "
                                    f"(elapsed={elapsed}s, "
                                    f"budget={screening_candidate_budget_seconds}s)"
                                ),
                                # v3.15.8: synthetic outcome dict —
                                # carry the plan-derived sampling
                                # block so screening evidence sees
                                # the same shape on the v3.14.1
                                # interrupt-transform path.
                                "sampling": dict(sampling_metadata),
                            }
                            tracker.emit_event(
                                "screening_candidate_budget_exceeded",
                                candidate_id=candidate["candidate_id"],
                                strategy=candidate["strategy_name"],
                                asset=candidate["asset"],
                                interval=candidate["interval"],
                                elapsed_seconds=elapsed,
                                budget_seconds=screening_candidate_budget_seconds,
                                samples_completed=samples_done,
                            )
                        else:
                            outcome = dict(isolated_result["outcome"])
                    except Exception as exc:
                        outcome = {
                            "legacy_decision": {
                                "status": "rejected_in_screening",
                                "reason": "screening_candidate_error",
                                "sampled_combination_count": runtime_record["samples_completed"],
                            },
                            "runtime_status": "running",
                            "final_status": FINAL_STATUS_ERRORED,
                            "started_at": runtime_record["started_at"],
                            "finished_at": datetime.now(UTC).isoformat(),
                            "elapsed_seconds": int(runtime_record["elapsed_seconds"]),
                            "samples_total": runtime_record["samples_total"],
                            "samples_completed": runtime_record["samples_completed"],
                            "decision": "rejected_in_screening",
                            "reason_code": "screening_candidate_error",
                            "reason_detail": str(exc),
                            # v3.15.8: synthetic outcome dict — see
                            # the timeout branch above for rationale.
                            "sampling": dict(sampling_metadata),
                        }
                        isolated_result = {"provenance_events": []}
                    provenance_events.extend(isolated_result.get("provenance_events") or [])

                    runtime_record.update(outcome)
                    runtime_record["elapsed_seconds"] = int(runtime_record.get("elapsed_seconds") or 0)
                    runtime_record["samples_total"] = int(runtime_record.get("samples_total") or 0)
                    runtime_record["samples_completed"] = int(runtime_record.get("samples_completed") or 0)
                    # v3.15.7: emit a per-candidate tracker event when a
                    # candidate passes the exploratory funnel. Run-level
                    # only — never emitted from screening_runtime,
                    # screening_process, or batch_execution. Payload metrics
                    # come straight from outcome["diagnostic_metrics"].
                    if outcome.get("pass_kind") == "exploratory":
                        diag = outcome.get("diagnostic_metrics") or {}
                        tracker.emit_event(
                            "exploratory_screening_pass",
                            candidate_id=str(candidate.get("candidate_id")),
                            expectancy=float(diag.get("expectancy", 0.0)),
                            profit_factor=float(diag.get("profit_factor", 0.0)),
                            win_rate=float(diag.get("win_rate", 0.0)),
                            max_drawdown=float(diag.get("max_drawdown", 0.0)),
                        )
                    decision = dict(outcome["legacy_decision"])
                    for item in candidates:
                        if item["candidate_id"] != candidate["candidate_id"]:
                            continue
                        item["screening"] = dict(decision)
                        item["current_status"] = "promoted_to_validation" if decision["status"] == SCREENING_PROMOTED else "screening_rejected"
                        break
                    if runtime_record["final_status"] == FINAL_STATUS_TIMED_OUT:
                        batch["timed_out_count"] += 1
                        batch["completed_candidate_count"] += 1
                    elif runtime_record["final_status"] == FINAL_STATUS_ERRORED:
                        batch["errored_count"] += 1
                        batch["completed_candidate_count"] += 1
                    elif decision["status"] == SCREENING_PROMOTED:
                        batch["promoted_candidate_count"] += 1
                    else:
                        batch["screening_rejected_count"] += 1
                        batch["completed_candidate_count"] += 1
                    candidate_payload, _ = _persist_candidate_pipeline_sidecars(
                        run_id=state["run_id"],
                        as_of_utc=as_of_utc,
                        candidates=candidates,
                    )
                    screening_payload = _persist_screening_candidate_sidecar(
                        run_id=state["run_id"],
                        as_of_utc=as_of_utc,
                        screening_records=screening_records,
                    )
                    batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - batch_started_monotonic)))
                    _persist_run_batches_sidecar(run_id=state["run_id"], as_of_utc=as_of_utc, batches=batches)
                    _write_batch_manifest(run_id=state["run_id"], batch=batch)
                    _persist_campaign_artifacts(
                        run_id=state["run_id"],
                        started_at=state["started_at_utc"],
                        batches=batches,
                        candidate_payload=candidate_payload,
                        screening_payload=screening_payload,
                        **campaign_kwargs,
                    )
                    if runtime_record["final_status"] in {FINAL_STATUS_PASSED, FINAL_STATUS_REJECTED}:
                        tracker.emit_event(
                            "screening_candidate_decision",
                            candidate_id=candidate["candidate_id"],
                            strategy=candidate["strategy_name"],
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            elapsed_seconds=runtime_record["elapsed_seconds"],
                            samples_completed=runtime_record["samples_completed"],
                            samples_total=runtime_record["samples_total"],
                            decision=runtime_record["decision"],
                            reason_code=runtime_record["reason_code"],
                        )
                    elif runtime_record["final_status"] == FINAL_STATUS_TIMED_OUT:
                        tracker.emit_event(
                            "screening_candidate_timeout",
                            candidate_id=candidate["candidate_id"],
                            strategy=candidate["strategy_name"],
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            elapsed_seconds=runtime_record["elapsed_seconds"],
                            samples_completed=runtime_record["samples_completed"],
                            samples_total=runtime_record["samples_total"],
                            decision=runtime_record["decision"],
                            reason_code=runtime_record["reason_code"],
                        )
                    elif runtime_record["final_status"] == FINAL_STATUS_ERRORED:
                        tracker.emit_event(
                            "screening_candidate_error",
                            candidate_id=candidate["candidate_id"],
                            strategy=candidate["strategy_name"],
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            elapsed_seconds=runtime_record["elapsed_seconds"],
                            samples_completed=runtime_record["samples_completed"],
                            samples_total=runtime_record["samples_total"],
                            decision=runtime_record["decision"],
                            reason_code=runtime_record["reason_code"],
                            reason_detail=runtime_record["reason_detail"],
                        )
                    tracker.emit_event(
                        "screening_candidate_finished",
                        candidate_id=candidate["candidate_id"],
                        strategy=candidate["strategy_name"],
                        asset=candidate["asset"],
                        interval=candidate["interval"],
                        elapsed_seconds=runtime_record["elapsed_seconds"],
                        samples_completed=runtime_record["samples_completed"],
                        samples_total=runtime_record["samples_total"],
                        final_status=runtime_record["final_status"],
                        decision=runtime_record["decision"],
                        reason_code=runtime_record["reason_code"],
                    )
                    screening_completed += 1
                    tracker.advance(completed=screening_completed, total=len(screening_items))
                    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                    tracker.set_screening(
                        _screening_progress_payload(
                            completed_candidates=screening_completed,
                            total_candidates=len(screening_items),
                            record=runtime_record,
                        ),
                        persist=True,
                    )

                if batch["promoted_candidate_count"] == 0:
                    batch["finished_at"] = datetime.now(UTC).isoformat()
                    batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - batch_started_monotonic)))
                    if batch["timed_out_count"] > 0 or batch["errored_count"] > 0:
                        batch["status"] = "partial"
                        batch["current_stage"] = "screening"
                        batch["reason_code"] = "isolated_candidate_execution_issues"
                        batch["reason_detail"] = "batch completed with screening timeout/error isolation"
                        tracker.emit_event(
                            "batch_partial",
                            batch_id=batch["batch_id"],
                            batch_index=batch["batch_index"],
                            strategy_family=batch["strategy_family"],
                            interval=batch["interval"],
                            elapsed_seconds=batch["elapsed_seconds"],
                            candidate_count=batch["candidate_count"],
                            completed_candidate_count=batch["completed_candidate_count"],
                            reason_code=batch["reason_code"],
                        )
                    else:
                        batch["status"] = "completed"
                        batch["current_stage"] = "screening"
                        tracker.emit_event(
                            "batch_completed",
                            batch_id=batch["batch_id"],
                            batch_index=batch["batch_index"],
                            strategy_family=batch["strategy_family"],
                            interval=batch["interval"],
                            elapsed_seconds=batch["elapsed_seconds"],
                            candidate_count=batch["candidate_count"],
                            completed_candidate_count=batch["completed_candidate_count"],
                        )
                else:
                    _mark_batch_pending_validation(batch)
                _persist_run_batches_sidecar(run_id=state["run_id"], as_of_utc=as_of_utc, batches=batches)
                _write_batch_manifest(run_id=state["run_id"], batch=batch)
                _persist_campaign_artifacts(
                    run_id=state["run_id"],
                    started_at=state["started_at_utc"],
                    batches=batches,
                    candidate_payload=candidate_payload,
                    screening_payload=screening_payload,
                    **campaign_kwargs,
                )
                _write_batch_recovery_state(
                    run_id=state["run_id"],
                    batch=batch,
                    candidates=candidates,
                    screening_records=screening_records,
                    rows=[],
                    evaluations=[],
                    walk_forward_reports=[],
                )
                tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
            except Exception as exc:
                batch["status"] = "failed"
                batch["current_stage"] = "screening"
                batch["finished_at"] = datetime.now(UTC).isoformat()
                batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - batch_started_monotonic)))
                batch["reason_code"] = "batch_execution_failed"
                batch["reason_detail"] = str(exc)
                batch["error_type"] = type(exc).__name__
                for later_batch in batches:
                    if later_batch["batch_index"] <= batch["batch_index"] or later_batch["status"] != "pending":
                        continue
                    later_batch["status"] = "skipped"
                    later_batch["reason_code"] = "upstream_batch_failed"
                    later_batch["reason_detail"] = f"skipped after failed batch {batch['batch_id']}"
                    _write_batch_manifest(run_id=state["run_id"], batch=later_batch)
                _persist_run_batches_sidecar(run_id=state["run_id"], as_of_utc=as_of_utc, batches=batches)
                _write_batch_manifest(run_id=state["run_id"], batch=batch)
                _persist_campaign_artifacts(
                    run_id=state["run_id"],
                    started_at=state["started_at_utc"],
                    batches=batches,
                    candidate_payload=candidate_payload,
                    screening_payload=screening_payload,
                    **campaign_kwargs,
                )
                tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                tracker.emit_event(
                    "batch_failed",
                    batch_id=batch["batch_id"],
                    batch_index=batch["batch_index"],
                    strategy_family=batch["strategy_family"],
                    interval=batch["interval"],
                    elapsed_seconds=batch["elapsed_seconds"],
                    candidate_count=batch["candidate_count"],
                    completed_candidate_count=batch["completed_candidate_count"],
                    reason_code=batch["reason_code"],
                    reason_detail=batch["reason_detail"],
                )
                raise

        if execution_max_workers == 1:
            # v3.9 phase 4: route inline-mode screening through the
            # Orchestrator seam. Lifecycle (Queue + Scheduler) is
            # exercised; execute_batch is the local closure defined
            # above which contains the v3.8 per-batch body unchanged.
            #
            # v3.9 phase 6: supply an explicit on_batch_complete hook
            # so production code does not silently rely on
            # `_default_complete`. See
            # tests/unit/test_orchestration_default_complete_scope.py.
            orchestrator.dispatch_serial_batches(
                batches=[item for item in batches if _batch_needs_screening(item)],
                kind=TaskKind.SCREENING_BATCH,
                execute_batch=_inline_screening_batch,
                on_batch_complete=_inline_on_batch_complete,
            )

        screening_summary = summarize_candidates(candidates)
        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _persist_campaign_artifacts(
            run_id=state["run_id"],
            started_at=state["started_at_utc"],
            batches=batches,
            candidate_payload=candidate_payload,
            screening_payload=screening_payload,
            **campaign_kwargs,
        )
        _merge_manifest(
            RUN_MANIFEST_PATH,
            screening_rejected_count=screening_summary["screening_rejected_count"],
            validation_candidate_count=screening_summary["validation_candidate_count"],
        )
        tracker.mark_stage_completed(
            screening_rejected_count=screening_summary["screening_rejected_count"],
            validation_candidate_count=screening_summary["validation_candidate_count"],
        )
        if screening_summary["validation_candidate_count"] == 0:
            _raise_degenerate_run(
                as_of_utc=as_of_utc,
                failure_stage="screening_no_survivors",
                assets=assets,
                intervals=intervals,
                interval_ranges=interval_ranges,
                pair_diagnostics=pair_diagnostics,
                run_id=str(state["run_id"]),
                preset_name=preset_obj.name if preset_obj else None,
                tracker=tracker,
            )

        tracker.start_stage("validation", total=screening_summary["validation_candidate_count"])
        validation_items = validation_candidates(candidates)
        validation_completed = sum(
            1
            for candidate in candidates
            if candidate.get("validation", {}).get("status") == "validated"
        )
        if validation_completed > 0:
            tracker.advance(completed=validation_completed, total=len(validation_items))
        if execution_max_workers > 1:
            # v3.9 phase 4: the parallel validation adapter internally
            # drives dispatch through the Orchestrator
            # (Scheduler + Queue + ProcessPoolBackend).
            candidate_payload, validation_completed, failed_batch_ids = _run_parallel_validation_batches(
                orchestrator=orchestrator,
                batches=batches,
                validation_items=validation_items,
                candidate_to_batch_id=candidate_to_batch_id,
                interval_ranges=interval_ranges,
                evaluation_config=evaluation_config,
                regime_config=research_config.get("regime_diagnostics"),
                as_of_utc=as_of_utc,
                run_id=state["run_id"],
                started_at_utc=state["started_at_utc"],
                screening_payload=screening_payload,
                tracker=tracker,
                candidates=candidates,
                candidate_payload=candidate_payload,
                rows=rows,
                evaluations=evaluations,
                walk_forward_reports=walk_forward_reports,
                validation_completed=validation_completed,
                execution_max_workers=execution_max_workers,
                provenance_events=provenance_events,
                screening_records=screening_records,
                lifecycle_mode=lifecycle_mode,
                resumed_from_run_id=resumed_from_run_id,
                continuation_summary=continuation_summary,
            )
            if failed_batch_ids:
                failed_batch = next(batch for batch in batches if str(batch["batch_id"]) in failed_batch_ids)
                raise RuntimeError(f"batch execution failed for {failed_batch['batch_id']}: {failed_batch['reason_detail']}")
        def _inline_validation_batch(batch: dict) -> None:
            """Phase 4 inline-validation closure.

            Routed through orchestrator.dispatch_serial_batches so that
            inline mode (max_workers == 1) no longer bypasses the
            Orchestrator. Body is the v3.8 per-batch inline logic
            verbatim; the original `continue` that skipped batches with
            no validation items is replaced with `return` (closure
            semantics) but has identical effect.
            """

            nonlocal candidate_payload, validation_completed
            batch_validation_items = [
                candidate
                for candidate in validation_items
                if candidate_to_batch_id.get(str(candidate["candidate_id"])) == str(batch["batch_id"])
            ]
            if not batch_validation_items:
                return
            batch["status"] = "running"
            batch["current_stage"] = "validation"
            batch["started_at"] = batch.get("started_at") or datetime.now(UTC).isoformat()
            tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
            _persist_run_batches_sidecar(
                run_id=state["run_id"],
                as_of_utc=as_of_utc,
                batches=batches,
            )
            _write_batch_manifest(run_id=state["run_id"], batch=batch)
            _persist_campaign_artifacts(
                run_id=state["run_id"],
                started_at=state["started_at_utc"],
                batches=batches,
                candidate_payload=candidate_payload,
                screening_payload=screening_payload,
                **campaign_kwargs,
            )
            try:
                for candidate in batch_validation_items:
                    strategy = strategy_by_name[candidate["strategy_name"]]
                    tracker.begin_item(
                        strategy=strategy["name"],
                        asset=candidate["asset"],
                        interval=candidate["interval"],
                    )
                    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                    start_datum = interval_ranges[candidate["interval"]]["start"]
                    eind_datum = interval_ranges[candidate["interval"]]["end"]
                    engine = _build_engine(
                        start_datum=start_datum,
                        eind_datum=eind_datum,
                        evaluation_config=evaluation_config,
                        regime_config=research_config.get("regime_diagnostics"),
                    )
                    try:
                        metrics = engine.grid_search(
                            strategie_factory=strategy["factory"],
                            param_grid=strategy["params"],
                            assets=[candidate["asset"]],
                            interval=candidate["interval"],
                        )
                        params_used = metrics.get("beste_params", {})
                        row = make_result_row(
                            strategy=strategy,
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            params=params_used,
                            as_of_utc=as_of_utc,
                            metrics=metrics,
                        )
                        evaluation_report = getattr(engine, "last_evaluation_report", None)
                        if evaluation_report is not None:
                            walk_forward_reports.append(
                                _sidecar_strategy_entry(
                                    strategy=strategy,
                                    asset=candidate["asset"],
                                    interval=candidate["interval"],
                                    report=evaluation_report,
                                )
                            )
                            evaluations.append(
                                {
                                    "family": strategy["family"],
                                    "interval": candidate["interval"],
                                    "selected_params": json.loads(row["params_json"]),
                                    "evaluation_report": evaluation_report,
                                    "row": row,
                                }
                            )
                    except (EvaluationScheduleError, FoldLeakageError, RuntimeError):
                        raise
                    except Exception as exc:
                        row = make_result_row(
                            strategy=strategy,
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            params={},
                            as_of_utc=as_of_utc,
                            metrics={},
                            error=str(exc),
                        )

                    provenance_events.extend(getattr(engine, "_provenance_events", []))
                    rows.append(row)
                    for item in candidates:
                        if item["candidate_id"] != candidate["candidate_id"]:
                            continue
                        item["validation"] = {
                            "status": "validated",
                            "result_success": bool(row["success"]),
                        }
                        item["current_status"] = "validated"
                        break
                    batch["validated_candidate_count"] += 1
                    batch["completed_candidate_count"] += 1
                    if row["success"]:
                        batch["result_success_count"] += 1
                    else:
                        batch["result_failed_count"] += 1
                        batch["validation_error_count"] += 1
                    candidate_payload, _ = _persist_candidate_pipeline_sidecars(
                        run_id=state["run_id"],
                        as_of_utc=as_of_utc,
                        candidates=candidates,
                    )
                    _persist_run_batches_sidecar(
                        run_id=state["run_id"],
                        as_of_utc=as_of_utc,
                        batches=batches,
                    )
                    _write_batch_manifest(run_id=state["run_id"], batch=batch)
                    _persist_campaign_artifacts(
                        run_id=state["run_id"],
                        started_at=state["started_at_utc"],
                        batches=batches,
                        candidate_payload=candidate_payload,
                        screening_payload=screening_payload,
                        **campaign_kwargs,
                    )
                    validation_completed += 1
                    batch["elapsed_seconds"] = _elapsed_from_started_at(batch.get("started_at"))
                    tracker.advance(completed=validation_completed, total=len(validation_items))
                    tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)

                batch["finished_at"] = datetime.now(UTC).isoformat()
                batch["elapsed_seconds"] = _elapsed_from_started_at(batch.get("started_at"))
                if batch["timed_out_count"] > 0 or batch["errored_count"] > 0 or batch["validation_error_count"] > 0:
                    batch["status"] = "partial"
                    batch["current_stage"] = "validation"
                    if batch["reason_code"] is None:
                        batch["reason_code"] = "isolated_candidate_execution_issues"
                        batch["reason_detail"] = "batch completed with candidate-level timeout/error isolation"
                    tracker.emit_event(
                        "batch_partial",
                        batch_id=batch["batch_id"],
                        batch_index=batch["batch_index"],
                        strategy_family=batch["strategy_family"],
                        interval=batch["interval"],
                        elapsed_seconds=batch["elapsed_seconds"],
                        candidate_count=batch["candidate_count"],
                        completed_candidate_count=batch["completed_candidate_count"],
                        reason_code=batch["reason_code"],
                    )
                else:
                    batch["status"] = "completed"
                    batch["current_stage"] = "validation"
                    tracker.emit_event(
                        "batch_completed",
                        batch_id=batch["batch_id"],
                        batch_index=batch["batch_index"],
                        strategy_family=batch["strategy_family"],
                        interval=batch["interval"],
                        elapsed_seconds=batch["elapsed_seconds"],
                        candidate_count=batch["candidate_count"],
                        completed_candidate_count=batch["completed_candidate_count"],
                    )
                _persist_run_batches_sidecar(
                    run_id=state["run_id"],
                    as_of_utc=as_of_utc,
                    batches=batches,
                )
                _write_batch_manifest(run_id=state["run_id"], batch=batch)
                _persist_campaign_artifacts(
                    run_id=state["run_id"],
                    started_at=state["started_at_utc"],
                    batches=batches,
                    candidate_payload=candidate_payload,
                    screening_payload=screening_payload,
                    **campaign_kwargs,
                )
                _write_batch_recovery_state(
                    run_id=state["run_id"],
                    batch=batch,
                    candidates=candidates,
                    screening_records=screening_records,
                    rows=rows,
                    evaluations=evaluations,
                    walk_forward_reports=walk_forward_reports,
                )
                tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
            except Exception as exc:
                batch["status"] = "failed"
                batch["current_stage"] = "validation"
                batch["finished_at"] = datetime.now(UTC).isoformat()
                batch["elapsed_seconds"] = _elapsed_from_started_at(batch.get("started_at"))
                batch["reason_code"] = "batch_execution_failed"
                batch["reason_detail"] = str(exc)
                batch["error_type"] = type(exc).__name__
                for later_batch in batches:
                    if later_batch["batch_index"] <= batch["batch_index"] or later_batch["status"] != "pending":
                        continue
                    later_batch["status"] = "skipped"
                    later_batch["reason_code"] = "upstream_batch_failed"
                    later_batch["reason_detail"] = f"skipped after failed batch {batch['batch_id']}"
                    _write_batch_manifest(run_id=state["run_id"], batch=later_batch)
                _persist_run_batches_sidecar(
                    run_id=state["run_id"],
                    as_of_utc=as_of_utc,
                    batches=batches,
                )
                _write_batch_manifest(run_id=state["run_id"], batch=batch)
                _persist_campaign_artifacts(
                    run_id=state["run_id"],
                    started_at=state["started_at_utc"],
                    batches=batches,
                    candidate_payload=candidate_payload,
                    screening_payload=screening_payload,
                    **campaign_kwargs,
                )
                tracker.set_batch(_batch_progress_payload(batch=batch, total_batches=len(batches)), persist=True)
                tracker.emit_event(
                    "batch_failed",
                    batch_id=batch["batch_id"],
                    batch_index=batch["batch_index"],
                    strategy_family=batch["strategy_family"],
                    interval=batch["interval"],
                    elapsed_seconds=batch["elapsed_seconds"],
                    candidate_count=batch["candidate_count"],
                    completed_candidate_count=batch["completed_candidate_count"],
                    reason_code=batch["reason_code"],
                    reason_detail=batch["reason_detail"],
                )
                raise

        if execution_max_workers == 1:
            # v3.9 phase 4: route inline-mode validation through the
            # Orchestrator seam. Queue + Scheduler track batch
            # lifecycle state; execute_batch is the local closure
            # defined above which contains the v3.8 per-batch body
            # unchanged.
            #
            # v3.9 phase 6: supply an explicit on_batch_complete hook
            # so production code does not silently rely on
            # `_default_complete`. See
            # tests/unit/test_orchestration_default_complete_scope.py.
            orchestrator.dispatch_serial_batches(
                batches=[item for item in batches if _batch_ready_for_validation(item)],
                kind=TaskKind.VALIDATION_BATCH,
                execute_batch=_inline_validation_batch,
                on_batch_complete=_inline_on_batch_complete,
            )

        candidate_payload, _ = _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _persist_campaign_artifacts(
            run_id=state["run_id"],
            started_at=state["started_at_utc"],
            batches=batches,
            candidate_payload=candidate_payload,
            screening_payload=screening_payload,
            **campaign_kwargs,
        )
        validation_summary = summarize_candidates(candidates)
        _merge_manifest(
            RUN_MANIFEST_PATH,
            validation_candidate_count=validation_summary["validation_candidate_count"],
            validated_count=validation_summary["validated_count"],
        )
        tracker.mark_stage_completed(
            validation_candidate_count=validation_summary["validation_candidate_count"],
            validated_count=validation_summary["validated_count"],
        )

        successful_rows = [row for row in rows if row["success"]]
        if validation_items and not successful_rows:
            _raise_degenerate_run(
                as_of_utc=as_of_utc,
                failure_stage="validation_no_survivors",
                assets=assets,
                intervals=intervals,
                interval_ranges=interval_ranges,
                pair_diagnostics=pair_diagnostics,
                evaluations_count=len(evaluations),
                run_id=str(state["run_id"]),
                preset_name=preset_obj.name if preset_obj else None,
                tracker=tracker,
            )

        evaluable_oos_daily_return_count = _count_evaluable_oos_daily_return_evaluations(evaluations)
        if evaluations and evaluable_oos_daily_return_count == 0:
            _raise_degenerate_run(
                as_of_utc=as_of_utc,
                failure_stage="postrun_no_oos_daily_returns",
                assets=assets,
                intervals=intervals,
                interval_ranges=interval_ranges,
                pair_diagnostics=pair_diagnostics,
                evaluations_count=len(evaluations),
                evaluations_with_oos_daily_returns=evaluable_oos_daily_return_count,
                run_id=str(state["run_id"]),
                preset_name=preset_obj.name if preset_obj else None,
                tracker=tracker,
            )

        tracker.start_stage("writing_outputs", total=len(rows))
        rows = sorted(rows, key=_result_row_sort_key)
        write_results_to_csv(rows)
        write_latest_json(rows, as_of_utc=as_of_utc)

        try:
            _write_public_artifact_status_sidecar(
                outcome="success",
                run_id=str(state["run_id"]),
                attempted_at_utc=as_of_utc.isoformat(),
                preset_name=preset_obj.name if preset_obj else None,
            )
        except Exception as status_exc:
            tracker.emit_event(
                "public_artifact_status_sidecar_failed",
                error=str(status_exc),
                outcome="success",
            )

        if any(not report["leakage_checks_ok"] for report in walk_forward_reports):
            raise FoldLeakageError("Leakage check failed; walk-forward sidecar will not be written")

        _write_walk_forward_sidecar(
            as_of_utc=as_of_utc,
            evaluation_config=evaluation_config,
            strategy_reports=walk_forward_reports,
        )
        _write_provenance_sidecar(
            research_config=research_config,
            as_of_utc=as_of_utc,
            interval_ranges=interval_ranges,
            provenance_events=provenance_events,
        )

        if evaluations and len(evaluations) != len(successful_rows):
            raise RuntimeError(
                "successful research rows are missing evaluation samples for statistical defensibility"
            )
        if evaluations and len(evaluations) == len(successful_rows):
            _write_statistical_defensibility_sidecar(
                evaluations=evaluations,
                as_of_utc=as_of_utc,
                intervals=intervals,
                market_count=len(assets),
                regime_count=regime_count,
                regime_count_source=regime_count_source,
            )

        _write_candidate_registry(
            rows=rows,
            walk_forward_reports=walk_forward_reports,
            research_config=research_config,
            as_of_utc=as_of_utc,
            # v3.15.7: provide screening pass_kind index so exploratory
            # passes are downgraded to needs_investigation instead of
            # auto-promoting to candidate. The registry row schema is
            # bytewise unchanged — pass_kind is consumed but not written.
            candidates_by_id=_candidate_index(candidates),
        )
        _write_portfolio_aggregation_sidecar(
            evaluations=evaluations,
            as_of_utc=as_of_utc,
        )
        _write_regime_diagnostics_sidecar(
            evaluations=evaluations,
            as_of_utc=as_of_utc,
            research_config=research_config,
            evaluation_config=evaluation_config,
            provenance_events=provenance_events,
        )
        _write_integrity_report_sidecar(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            research_config=research_config,
            provenance_events=provenance_events,
            integrity_checks=integrity_checks,
        )
        tracker.emit_event(
            "integrity_report_written",
            path=INTEGRITY_REPORT_PATH.as_posix(),
            check_count=len(integrity_checks),
        )
        statistical_defensibility_payload: dict | None = None
        if SIDE_CAR_PATH.exists():
            statistical_defensibility_payload = json.loads(
                SIDE_CAR_PATH.read_text(encoding="utf-8")
            )
        falsification_payload = _write_falsification_gates_sidecar(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            rows=rows,
            walk_forward_reports=walk_forward_reports,
            statistical_defensibility=statistical_defensibility_payload,
            cost_per_side=DEFAULT_COST_PER_SIDE,
        )
        tracker.emit_event(
            "falsification_gates_written",
            path=FALSIFICATION_GATES_PATH.as_posix(),
            candidate_count=len(falsification_payload.get("candidates") or []),
        )
        tracker.mark_stage_completed(results_written=len(rows))

        # v3.10: run_meta sidecar + post-run report agent.
        # Adjacent artifacts — no mutation of the frozen public contract.
        try:
            meta_payload = build_run_meta_payload(
                run_id=str(state["run_id"]),
                preset=preset_obj,
                started_at_utc=state["started_at_utc"],
                completed_at_utc=datetime.now(UTC).isoformat(),
                git_revision=_git_revision(),
                config_hash=_config_hash(research_config, provenance_events),
                candidate_summary=build_candidate_summary(
                    raw=len(rows),
                    screened=sum(1 for r in rows if r.get("success")),
                    validated=len(evaluations),
                    rejected=sum(1 for r in rows if not r.get("goedgekeurd")),
                    promoted=sum(1 for r in rows if r.get("goedgekeurd")),
                ),
                top_rejection_reasons=rollup_rejection_reasons(rows),
                artifact_paths={
                    "run_state": RUN_STATE_PATH.as_posix(),
                    "run_manifest": RUN_MANIFEST_PATH.as_posix(),
                    "run_candidates": RUN_CANDIDATES_PATH.as_posix(),
                    "report_markdown": "research/report_latest.md",
                    "report_json": "research/report_latest.json",
                },
            )
            write_run_meta_sidecar(meta_payload, path=RUN_META_PATH)
        except Exception as meta_exc:
            tracker.emit_event("run_meta_sidecar_failed", error=str(meta_exc))
        # v3.12: first-class candidate sidecars (registry v2, status
        # history, advisory agent definitions). Additive only — does
        # not mutate research_latest.json / strategy_matrix.csv /
        # candidate_registry_latest.v1.json.
        try:
            v3_12_ctx = SidecarBuildContext(
                run_id=str(state["run_id"]),
                generated_at_utc=as_of_utc.isoformat(),
                git_revision=_git_revision(),
                research_latest={
                    "generated_at_utc": as_of_utc.isoformat(),
                    "results": rows,
                },
                candidate_registry_v1=_read_json_if_exists(CANDIDATE_REGISTRY_PATH)
                or {"candidates": []},
                run_candidates=_read_json_if_exists(RUN_CANDIDATES_PATH),
                run_meta=meta_payload,
                defensibility=_read_json_if_exists(SIDE_CAR_PATH),
                regime=_read_json_if_exists(REGIME_DIAGNOSTICS_PATH),
                cost_sens=_read_json_if_exists(COST_SENSITIVITY_PATH),
            )
            v3_12_paths = build_and_write_v3_12_sidecars(v3_12_ctx)
            tracker.emit_event(
                "v3_12_candidate_sidecars_written",
                paths={name: path.as_posix() for name, path in v3_12_paths.items()},
            )
        except Exception as v3_12_exc:
            tracker.emit_event("v3_12_candidate_sidecars_failed", error=str(v3_12_exc))
        # v3.13: parallel regime-intelligence façade. Writes two
        # adjacent sidecars joined on candidate_id. Additive only —
        # v3.12 artifacts and frozen public contracts are not
        # mutated. v3.14 populates width_distributions via the
        # research.regime_width_feed module (same OHLCV cache the
        # backtest used; no re-downloads).
        registry_v2_payload = _read_json_if_exists(
            Path("research/candidate_registry_latest.v2.json")
        ) or {"entries": []}
        width_feed_result: WidthFeedResult | None = None
        try:
            date_range_by_interval: dict[str, tuple[str, str]] = {}
            for interval, ranges in interval_ranges.items():
                start = ranges.get("start")
                end = ranges.get("end")
                if isinstance(start, str) and isinstance(end, str):
                    date_range_by_interval[interval] = (start, end)
            width_feed_result = build_width_distributions(
                registry_v2=registry_v2_payload,
                date_range_by_interval=date_range_by_interval,
            )
        except Exception as width_exc:
            tracker.emit_event("v3_14_width_feed_failed", error=str(width_exc))
            width_feed_result = None
        try:
            regime_ctx = RegimeSidecarBuildContext(
                run_id=str(state["run_id"]),
                generated_at_utc=as_of_utc.isoformat(),
                git_revision=_git_revision(),
                registry_v2=registry_v2_payload,
                regime_diagnostics=_read_json_if_exists(REGIME_DIAGNOSTICS_PATH),
                width_distributions=(
                    width_feed_result.distributions if width_feed_result else None
                ),
            )
            regime_paths = build_and_write_regime_sidecars(regime_ctx)
            tracker.emit_event(
                "v3_13_regime_sidecars_written",
                paths={name: path.as_posix() for name, path in regime_paths.items()},
            )
        except Exception as v3_13_exc:
            tracker.emit_event("v3_13_regime_sidecars_failed", error=str(v3_13_exc))
        # v3.14: portfolio / sleeve research façade. Strictly
        # additive — consumes v3.12 registry v2 + v3.13 overlay +
        # per-candidate daily returns captured from in-memory
        # evaluations. Produces sleeve registry, candidate returns,
        # portfolio diagnostics, and (when width-feed data is
        # available) the regime width distributions sidecar.
        try:
            regime_overlay_payload = _read_json_if_exists(
                Path("research/candidate_registry_regime_overlay_latest.v1.json")
            )
            candidate_returns_records = build_records_from_evaluations(evaluations)
            portfolio_ctx = PortfolioSleeveBuildContext(
                run_id=str(state["run_id"]),
                generated_at_utc=as_of_utc.isoformat(),
                git_revision=_git_revision(),
                registry_v2=registry_v2_payload,
                regime_overlay=regime_overlay_payload,
                candidate_returns=candidate_returns_records,
                width_feed_result=width_feed_result,
            )
            portfolio_paths = build_and_write_portfolio_sleeve_sidecars(portfolio_ctx)
            tracker.emit_event(
                "v3_14_portfolio_sleeve_sidecars_written",
                paths={name: path.as_posix() for name, path in portfolio_paths.items()},
            )
        except Exception as v3_14_exc:
            tracker.emit_event("v3_14_portfolio_sleeve_sidecars_failed", error=str(v3_14_exc))
        # v3.15: paper validation engine — additive, isolated,
        # diagnostic-only. Produces timestamped-returns, ledger,
        # divergence, and readiness sidecars. Consumes the v3.14
        # sleeve_registry payload for sleeve lookup; never writes
        # to v3.12/v3.13/v3.14 artifacts.
        try:
            sleeve_registry_payload = _read_json_if_exists(
                Path("research/sleeve_registry_latest.v1.json")
            )
            paper_ctx = PaperValidationBuildContext(
                run_id=str(state["run_id"]),
                generated_at_utc=as_of_utc.isoformat(),
                git_revision=_git_revision(),
                registry_v2=registry_v2_payload,
                sleeve_registry=sleeve_registry_payload,
                evaluations=list(evaluations),
                # v3.15.4: stamp the COL ownership breadcrumb so the
                # campaign_launcher can verify a stale paper_readiness
                # sidecar from a prior campaign isn't read after a
                # subprocess crash. None when invoked directly via CLI.
                col_campaign_id=_COL_CAMPAIGN_ID,
            )
            paper_paths = build_and_write_paper_validation_sidecars(paper_ctx)
            tracker.emit_event(
                "v3_15_paper_validation_sidecars_written",
                paths={name: path.as_posix() for name, path in paper_paths.items()},
            )
        except Exception as v3_15_exc:
            tracker.emit_event("v3_15_paper_validation_sidecars_failed", error=str(v3_15_exc))
        # v3.15.3: strategy hypothesis catalog + campaign metadata.
        # Adjacent artifacts only — never spliced into research_latest.json
        # or strategy_matrix.csv. The v3.15.2 Campaign Operating Layer
        # reads these sidecars at tick boundaries to gate spawning by
        # hypothesis status (active_discovery / planned / disabled /
        # diagnostic). Invariant (v3.15.4): >=1 active_discovery row, plus
        # per-row strict checks (bounded grid, non-empty eligible types,
        # canonical failure modes) enforced by _validate_catalog().
        try:
            v3_15_3_paths = {
                "strategy_hypothesis_catalog": write_catalog_sidecar(
                    generated_at_utc=as_of_utc,
                    git_revision=_git_revision(),
                    run_id=str(state["run_id"]),
                ),
                "strategy_campaign_metadata": write_campaign_metadata_sidecar(
                    generated_at_utc=as_of_utc,
                    git_revision=_git_revision(),
                    run_id=str(state["run_id"]),
                ),
            }
            tracker.emit_event(
                "v3_15_3_hypothesis_catalog_sidecars_written",
                paths={name: path.as_posix() for name, path in v3_15_3_paths.items()},
            )
        except Exception as v3_15_3_exc:
            tracker.emit_event(
                "v3_15_3_hypothesis_catalog_sidecars_failed",
                error=str(v3_15_3_exc),
            )
        # v3.15.9: funnel evidence artifact. Adjacent non-frozen
        # sidecar emitted AFTER paper validation so paper_blocked
        # signals can be folded in. Builder is pure and resilient
        # to malformed candidates (identity-fallback path); this
        # try/except therefore only protects against I/O failures.
        screening_evidence_payload: dict[str, Any] | None = None
        try:
            paper_blocked_index = _read_paper_blocked_index()
            screening_pass_kinds_by_strategy: dict[str, str | None] = {}
            for _candidate_for_evidence in candidates:
                screening_block = (
                    _candidate_for_evidence.get("screening") or {}
                )
                _strategy_key = str(
                    _candidate_for_evidence.get("strategy_id")
                    or _candidate_for_evidence.get("strategy_name")
                    or ""
                )
                if _strategy_key:
                    screening_pass_kinds_by_strategy[_strategy_key] = (
                        screening_block.get("pass_kind")
                        if isinstance(screening_block, dict)
                        else None
                    )
            evidence_payload = build_screening_evidence_payload(
                run_id=str(state["run_id"]),
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                campaign_id=_COL_CAMPAIGN_ID,
                col_campaign_id=_COL_CAMPAIGN_ID,
                preset_name=preset_obj.name if preset_obj is not None else None,
                screening_phase=(
                    preset_obj.screening_phase if preset_obj is not None else None
                ),
                candidates=candidates,
                screening_records=screening_records,
                screening_pass_kinds=screening_pass_kinds_by_strategy,
                paper_blocked_index=paper_blocked_index,
            )
            write_sidecar_atomic(SCREENING_EVIDENCE_PATH, evidence_payload)
            screening_evidence_payload = evidence_payload
            tracker.emit_event(
                "v3_15_9_screening_evidence_written",
                path=SCREENING_EVIDENCE_PATH.as_posix(),
                artifact_fingerprint=evidence_payload["artifact_fingerprint"],
                identity_fallbacks=evidence_payload["summary"]["identity_fallbacks"],
                near_passes=evidence_payload["summary"]["near_passes"],
                coverage_warnings=evidence_payload["summary"]["coverage_warnings"],
            )
        except Exception as v3_15_9_exc:
            tracker.emit_event(
                "v3_15_9_screening_evidence_failed", error=str(v3_15_9_exc)
            )
        # v3.15.11: research intelligence layer (advisory observability).
        # Writes 5 deterministic non-frozen sidecars under
        # research/campaigns/evidence/. Strictly artifact-write — does
        # NOT mutate campaign_policy.decide(), the queue, the
        # registry, or any frozen contract. Each stage is wrapped
        # individually so partial failure cannot mask the run's
        # original outcome.
        intelligence_run_id = str(state["run_id"])
        intelligence_evidence_payload: dict[str, Any] | None = None
        ig_payload: dict[str, Any] | None = None
        stop_payload: dict[str, Any] | None = None
        dz_payload: dict[str, Any] | None = None
        via_payload: dict[str, Any] | None = None
        try:
            intelligence_evidence_payload = write_research_evidence_artifact(
                run_id=intelligence_run_id,
                col_campaign_id=_COL_CAMPAIGN_ID,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
            )
            tracker.emit_event(
                "v3_15_11_research_evidence_ledger_written",
                hypothesis_count=len(
                    intelligence_evidence_payload.get("hypothesis_evidence") or []
                ),
            )
        except Exception as ev_exc:
            tracker.emit_event(
                "v3_15_11_research_evidence_ledger_failed", error=str(ev_exc)
            )
        try:
            evidence_summary: dict[str, Any] = (
                screening_evidence_payload.get("summary")
                if screening_evidence_payload is not None
                else {}
            ) or {}
            sampling_block: dict[str, Any] = {}
            if screening_evidence_payload is not None:
                first_candidates = (
                    screening_evidence_payload.get("candidates") or []
                )
                if first_candidates:
                    candidate_sampling = first_candidates[0].get("sampling")
                    if isinstance(candidate_sampling, dict):
                        sampling_block = candidate_sampling
            ig_inputs = InformationGainInputs(
                exploratory_pass=int(evidence_summary.get("exploratory_passes") or 0) > 0,
                near_candidate=int(evidence_summary.get("near_passes") or 0) > 0,
                promotion_candidate=int(
                    evidence_summary.get("promotion_grade_candidates") or 0
                ) > 0,
                paper_ready=False,
                technical_failure=False,
                parameter_coverage_pct=sampling_block.get("coverage_pct") if isinstance(sampling_block, dict) else None,
                sampled_count=sampling_block.get("sampled_count") if isinstance(sampling_block, dict) else None,
                grid_size=sampling_block.get("grid_size") if isinstance(sampling_block, dict) else None,
            )
            ig_payload = write_information_gain_artifact(
                run_id=intelligence_run_id,
                col_campaign_id=_COL_CAMPAIGN_ID,
                preset_name=preset_obj.name if preset_obj is not None else None,
                hypothesis_id=None,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                inputs=ig_inputs,
            )
            tracker.emit_event(
                "v3_15_11_information_gain_written",
                bucket=ig_payload["information_gain"]["bucket"],
                score=ig_payload["information_gain"]["score"],
            )
        except Exception as ig_exc:
            tracker.emit_event(
                "v3_15_11_information_gain_failed", error=str(ig_exc)
            )
        try:
            ledger_for_stop = intelligence_evidence_payload or {
                "hypothesis_evidence": []
            }
            stop_payload = write_stop_conditions_artifact(
                run_id=intelligence_run_id,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                evidence_ledger=ledger_for_stop,
            )
            tracker.emit_event(
                "v3_15_11_stop_conditions_written",
                advisory_decision_count=len(stop_payload["decisions"]),
            )
        except Exception as sc_exc:
            tracker.emit_event(
                "v3_15_11_stop_conditions_failed", error=str(sc_exc)
            )
        try:
            ledger_events = _load_campaign_events(
                Path("research/campaign_evidence_ledger.jsonl")
            )
            dz_payload = write_dead_zones_artifact(
                run_id=intelligence_run_id,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                events=ledger_events,
            )
            tracker.emit_event(
                "v3_15_11_dead_zones_written",
                zone_count=len(dz_payload["zones"]),
            )
        except Exception as dz_exc:
            tracker.emit_event(
                "v3_15_11_dead_zones_failed", error=str(dz_exc)
            )
        try:
            ledger_for_viability = intelligence_evidence_payload or {
                "hypothesis_evidence": []
            }
            via_payload = write_viability_artifact(
                run_id=intelligence_run_id,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                evidence_ledger=ledger_for_viability,
            )
            tracker.emit_event(
                "v3_15_11_viability_written",
                verdict=via_payload["verdict"]["status"],
            )
        except Exception as via_exc:
            tracker.emit_event(
                "v3_15_11_viability_failed", error=str(via_exc)
            )
        # v3.15.12: funnel spawn proposer (advisory shadow mode).
        # Forward-looking complement to the v3.15.11 backward-looking
        # intelligence layer. Writes:
        #   - research/campaigns/evidence/spawn_proposals_latest.v1.json
        #   - research/campaigns/evidence/spawn_proposal_history.jsonl
        # Strictly artifact-write. Does NOT mutate campaign_policy,
        # the queue, the registry, or any frozen contract. Top-level
        # enforcement_state="advisory_only" + mode="shadow".
        try:
            registry_payload_for_proposer = _read_json_if_exists(
                Path("research/campaign_registry_latest.v1.json")
            )
            spawn_payload = write_spawn_proposals_artifact(
                run_id=intelligence_run_id,
                as_of_utc=as_of_utc,
                git_revision=_git_revision(),
                screening_evidence=screening_evidence_payload,
                evidence_ledger=intelligence_evidence_payload,
                information_gain=ig_payload,
                stop_conditions=stop_payload,
                dead_zones=dz_payload,
                viability=via_payload,
                campaign_registry=registry_payload_for_proposer,
            )
            tracker.emit_event(
                "v3_15_12_spawn_proposals_written",
                proposed_count=spawn_payload["summary"]["proposed_count"],
                proposal_mode=spawn_payload["proposal_mode"],
                suppressed_zone_count=spawn_payload["summary"]["suppressed_zone_count"],
            )
        except Exception as spawn_exc:
            tracker.emit_event(
                "v3_15_12_spawn_proposals_failed", error=str(spawn_exc)
            )
        try:
            generate_post_run_report(run_id=str(state["run_id"]))
        except Exception as report_exc:
            tracker.emit_event("report_agent_failed", error=str(report_exc))

        tracker.complete()
        print(f"Klaar. {len(rows)} resultaten geschreven.")
    except Exception as exc:
        tracker.fail(exc, failure_stage=tracker.current_stage)
        raise


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run quant research with optional artifact-driven resume.")
    parser.add_argument(
        "--continue-latest",
        action="store_true",
        help="Resolve the latest run artifacts to fresh, resume, retry_failed_batches, or fail-closed.",
    )
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted research run from artifacts.")
    parser.add_argument(
        "--retry-failed-batches",
        action="store_true",
        help="When used with --resume, retry failed batches at batch level.",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=None,
        help="Named research preset (see research/presets.py). Filters bundle to the preset's strategies.",
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help=(
            "v3.15.2 COL breadcrumb. Usually injected by "
            "research.campaign_launcher; pipeline behaviour is unchanged "
            "when absent."
        ),
    )
    args = parser.parse_args()
    if args.continue_latest and args.resume:
        parser.error("--continue-latest cannot be combined with --resume")
    return args


if __name__ == "__main__":
    args = _parse_cli_args()
    # v3.15.5: a controlled DegenerateResearchRunError must surface as
    # rc=EXIT_CODE_DEGENERATE_NO_SURVIVORS so the campaign launcher can
    # classify the run as `degenerate_no_survivors` instead of falling
    # back to `worker_crashed`. The callable run_research() still raises
    # the exception so existing tests (and library callers) keep working.
    try:
        run_research(
            resume=bool(args.resume),
            retry_failed_batches=bool(args.retry_failed_batches),
            continue_latest=bool(args.continue_latest),
            preset=args.preset,
            col_campaign_id=args.campaign_id,
        )
    except DegenerateResearchRunError:
        sys.exit(EXIT_CODE_DEGENERATE_NO_SURVIVORS)
