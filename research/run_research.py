"""
Research runner:
voert alle enabled strategieen uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml

from agent.backtesting.engine import (
    MIN_ROBUSTNESS_FOLDS,
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    normalize_evaluation_config,
)
from research.candidate_pipeline import (
    SCREENING_PROMOTED,
    apply_eligibility,
    apply_fit_prior,
    build_candidate_artifact_payload,
    build_filter_summary_payload,
    deduplicate_candidates,
    index_readiness,
    normalize_screening_decision,
    plan_candidates,
    screening_candidates,
    screening_param_samples,
    summarize_candidates,
    validation_candidates,
)
from research.empty_run_reporting import (
    DegenerateResearchRunError,
    build_empty_run_diagnostics_payload,
)
from research.observability import ProgressTracker
from research.portfolio_reporting import build_portfolio_aggregation_payload
from research.promotion_reporting import build_candidate_registry_payload
from research.regime_reporting import build_regime_diagnostics_payload
from research.registry import get_enabled_strategies
from research.results import make_result_row, write_latest_json, write_results_to_csv
from research.run_state import RunStateStore
from research.statistical_reporting import build_statistical_defensibility_payload, regime_count_settings
from research.universe import build_research_universe

SIDE_CAR_PATH = Path("research/statistical_defensibility_latest.v1.json")
WALK_FORWARD_PATH = "research/walk_forward_latest.v1.json"
CANDIDATE_REGISTRY_PATH = Path("research/candidate_registry_latest.v1.json")
UNIVERSE_SNAPSHOT_PATH = Path("research/universe_snapshot_latest.v1.json")
PORTFOLIO_AGGREGATION_PATH = Path("research/portfolio_aggregation_latest.v1.json")
REGIME_DIAGNOSTICS_PATH = Path("research/regime_diagnostics_latest.v1.json")
EMPTY_RUN_DIAGNOSTICS_PATH = Path("research/empty_run_diagnostics_latest.v1.json")
RUN_CANDIDATES_PATH = Path("research/run_candidates_latest.v1.json")
RUN_FILTER_SUMMARY_PATH = Path("research/run_filter_summary_latest.v1.json")
RUN_PROGRESS_PATH = Path("research/run_progress_latest.v1.json")
RUN_STATE_PATH = Path("research/run_state.v1.json")
RUN_MANIFEST_PATH = Path("research/run_manifest_latest.v1.json")
RUN_LOG_DIR = Path("logs/research")
RUN_HEARTBEAT_TIMEOUT_S = 300
SCREENING_PARAM_SAMPLE_LIMIT = 3


def load_research_config(config_path="config/config.yaml"):
    path = Path(config_path)
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    return config.get("research") or {}


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

    payload = build_candidate_registry_payload(
        research_latest=research_latest,
        walk_forward=walk_forward,
        statistical_defensibility=statistical_defensibility,
        promotion_config=research_config.get("promotion"),
        git_revision=_git_revision(),
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
        "artifacts": {
            "run_candidates_path": RUN_CANDIDATES_PATH.as_posix(),
            "run_filter_summary_path": RUN_FILTER_SUMMARY_PATH.as_posix(),
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


def _persist_candidate_pipeline_sidecars(*, run_id: str, as_of_utc: datetime, candidates: list[dict]) -> None:
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
    raise DegenerateResearchRunError(payload["message"])


def _screen_candidate(
    *,
    strategy: dict,
    candidate: dict,
    engine,
) -> dict[str, str | None]:
    if not hasattr(engine, "run"):
        return {
            "status": SCREENING_PROMOTED,
            "reason": None,
            "sampled_combination_count": 0,
        }

    sample_results: list[dict[str, str | None]] = []
    for params in screening_param_samples(
        strategy.get("params") or {},
        max_samples=SCREENING_PARAM_SAMPLE_LIMIT,
    ):
        try:
            metrics = engine.run(
                strategy["factory"](**params),
                assets=[candidate["asset"]],
                interval=candidate["interval"],
            )
            report = getattr(engine, "last_evaluation_report", None) or {}
            evaluation_samples = report.get("evaluation_samples") or {}
            daily_returns = evaluation_samples.get("daily_returns") or []
            if not isinstance(daily_returns, list) or not daily_returns:
                sample_results.append({"status": "rejected_in_screening", "reason": "no_oos_samples"})
                continue
            min_trades = int(getattr(engine, "min_trades", 10))
            if int(metrics.get("totaal_trades", 0)) < min_trades:
                sample_results.append({"status": "rejected_in_screening", "reason": "insufficient_trades"})
                continue
            if not metrics.get("goedgekeurd", False):
                sample_results.append({"status": "rejected_in_screening", "reason": "screening_criteria_not_met"})
                continue
            sample_results.append({"status": SCREENING_PROMOTED, "reason": None})
        except Exception:
            sample_results.append({"status": "rejected_in_screening", "reason": "screening_error"})

    return normalize_screening_decision(sample_results)


def run_research():
    lifecycle = RunStateStore(
        state_path=RUN_STATE_PATH,
        history_root=Path("research/history"),
    )
    state = lifecycle.start_run(
        progress_path=RUN_PROGRESS_PATH,
        manifest_path=RUN_MANIFEST_PATH,
        log_dir=RUN_LOG_DIR,
        heartbeat_timeout_s=RUN_HEARTBEAT_TIMEOUT_S,
        stage="starting",
        status_reason="research_run_started",
    )
    started_at_utc = datetime.fromisoformat(state["started_at_utc"])
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
    try:
        research_config = load_research_config()
        regime_count, regime_count_source = regime_count_settings(research_config)
        evaluation_config = normalize_evaluation_config(research_config.get("evaluation"))
        assets, intervals, get_date_range, as_of_utc, universe_snapshot = build_research_universe(research_config)
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
            )
        )
        tracker.mark_stage_completed(raw_candidate_count=len(planned_candidates))

        tracker.start_stage("dedupe", total=len(planned_candidates))
        candidates, dedupe_summary = deduplicate_candidates(planned_candidates)
        _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
        )
        _merge_manifest(RUN_MANIFEST_PATH, **dedupe_summary)
        tracker.mark_stage_completed(**dedupe_summary)

        tracker.start_stage("fit_prior", total=len(candidates))
        candidates, fit_summary = apply_fit_prior(candidates)
        _persist_candidate_pipeline_sidecars(
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
        )
        _persist_candidate_pipeline_sidecars(
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
            )

        tracker.start_stage("screening", total=eligibility_summary["eligible_candidate_count"])
        screening_items = screening_candidates(candidates)
        for index, candidate in enumerate(screening_items, start=1):
            tracker.begin_item(
                strategy=candidate["strategy_name"],
                asset=candidate["asset"],
                interval=candidate["interval"],
            )
            strategy = strategy_by_name[candidate["strategy_name"]]
            start_datum = interval_ranges[candidate["interval"]]["start"]
            eind_datum = interval_ranges[candidate["interval"]]["end"]
            engine = _build_engine(
                start_datum=start_datum,
                eind_datum=eind_datum,
                evaluation_config=evaluation_config,
                regime_config=research_config.get("regime_diagnostics"),
            )
            decision = _screen_candidate(strategy=strategy, candidate=candidate, engine=engine)
            provenance_events.extend(getattr(engine, "_provenance_events", []))
            for item in candidates:
                if item["candidate_id"] != candidate["candidate_id"]:
                    continue
                item["screening"] = dict(decision)
                if decision["status"] == SCREENING_PROMOTED:
                    item["current_status"] = "promoted_to_validation"
                else:
                    item["current_status"] = "screening_rejected"
                break
            tracker.advance(completed=index, total=len(screening_items))

        screening_summary = summarize_candidates(candidates)
        _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
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
            )

        tracker.start_stage("validation", total=screening_summary["validation_candidate_count"])
        validation_items = validation_candidates(candidates)
        for index, candidate in enumerate(validation_items, start=1):
            strategy = strategy_by_name[candidate["strategy_name"]]
            tracker.begin_item(
                strategy=strategy["name"],
                asset=candidate["asset"],
                interval=candidate["interval"],
            )
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
            except (EvaluationScheduleError, FoldLeakageError):
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
            tracker.advance(completed=index, total=len(validation_items))

        _persist_candidate_pipeline_sidecars(
            run_id=state["run_id"],
            as_of_utc=as_of_utc,
            candidates=candidates,
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
            )

        tracker.start_stage("writing_outputs", total=len(rows))
        write_results_to_csv(rows)
        write_latest_json(rows, as_of_utc=as_of_utc)

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
        tracker.mark_stage_completed(results_written=len(rows))
        tracker.complete()
        print(f"Klaar. {len(rows)} resultaten geschreven.")
    except Exception as exc:
        tracker.fail(exc, failure_stage=tracker.current_stage)
        raise


if __name__ == "__main__":
    run_research()
