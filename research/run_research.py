"""
Research runner:
voert alle enabled strategieen uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import hashlib
import json
import os
import subprocess
from datetime import timezone
from pathlib import Path

import yaml

from agent.backtesting.engine import (
    MIN_ROBUSTNESS_FOLDS,
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    normalize_evaluation_config,
)
from research.registry import get_enabled_strategies
from research.results import make_result_row, write_latest_json, write_results_to_csv
from research.portfolio_reporting import build_portfolio_aggregation_payload
from research.promotion_reporting import build_candidate_registry_payload
from research.regime_reporting import build_regime_diagnostics_payload
from research.statistical_reporting import build_statistical_defensibility_payload, regime_count_settings
from research.universe import build_research_universe

SIDE_CAR_PATH = Path("research/statistical_defensibility_latest.v1.json")
WALK_FORWARD_PATH = "research/walk_forward_latest.v1.json"
CANDIDATE_REGISTRY_PATH = Path("research/candidate_registry_latest.v1.json")
UNIVERSE_SNAPSHOT_PATH = Path("research/universe_snapshot_latest.v1.json")
PORTFOLIO_AGGREGATION_PATH = Path("research/portfolio_aggregation_latest.v1.json")
REGIME_DIAGNOSTICS_PATH = Path("research/regime_diagnostics_latest.v1.json")


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
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
    os.replace(tmp_path, path)


def _write_universe_snapshot_sidecar(
    snapshot,
    path: Path = UNIVERSE_SNAPSHOT_PATH,
) -> None:
    """Write the resolved universe snapshot for lineage."""
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
    """Derive robustness metadata from serialized fold list."""
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
    """Build and write candidate registry from in-memory artifacts.

    Skips silently when walk_forward_reports is empty (no OOS data to promote).
    """
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


def run_research():
    rows = []
    evaluations = []
    walk_forward_reports = []
    provenance_events = []
    research_config = load_research_config()
    regime_count, regime_count_source = regime_count_settings(research_config)
    evaluation_config = normalize_evaluation_config(research_config.get("evaluation"))
    assets, intervals, get_date_range, as_of_utc, universe_snapshot = build_research_universe(research_config)
    _write_universe_snapshot_sidecar(universe_snapshot)
    interval_ranges = {}
    strategies = get_enabled_strategies()

    for interval in intervals:
        start_datum, eind_datum = get_date_range(interval)
        interval_ranges[interval] = {"start": start_datum, "end": eind_datum}

    for strategy in strategies:
        for interval in intervals:
            for asset in assets:
                start_datum = interval_ranges[interval]["start"]
                eind_datum = interval_ranges[interval]["end"]

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
                        assets=[asset.symbol],
                        interval=interval,
                    )
                    params_used = metrics.get("beste_params", {})
                    row = make_result_row(
                        strategy=strategy,
                        asset=asset.symbol,
                        interval=interval,
                        params=params_used,
                        as_of_utc=as_of_utc,
                        metrics=metrics,
                    )
                    evaluation_report = getattr(engine, "last_evaluation_report", None)
                    if evaluation_report is not None:
                        walk_forward_reports.append(
                            _sidecar_strategy_entry(
                                strategy=strategy,
                                asset=asset.symbol,
                                interval=interval,
                                report=evaluation_report,
                            )
                        )
                        evaluations.append(
                            {
                                "family": strategy["family"],
                                "interval": interval,
                                "selected_params": json.loads(row["params_json"]),
                                "evaluation_report": evaluation_report,
                                "row": row,
                            }
                        )
                except (EvaluationScheduleError, FoldLeakageError):
                    raise
                except Exception as e:
                    row = make_result_row(
                        strategy=strategy,
                        asset=asset.symbol,
                        interval=interval,
                        params={},
                        as_of_utc=as_of_utc,
                        metrics={},
                        error=str(e),
                    )

                provenance_events.extend(getattr(engine, "_provenance_events", []))
                rows.append(row)

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

    successful_rows = [row for row in rows if row["success"]]
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

    print(f"Klaar. {len(rows)} resultaten geschreven.")
    
if __name__ == "__main__":
    run_research()

