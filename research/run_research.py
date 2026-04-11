"""
Research runner:
voert alle enabled strategieën uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import hashlib
import json
import subprocess
from datetime import timezone
from pathlib import Path

import yaml

from agent.backtesting.engine import (
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    normalize_evaluation_config,
)
from research.registry import get_enabled_strategies
from research.results import make_result_row, write_results_to_csv, write_latest_json
from research.universe import build_research_universe

WALK_FORWARD_PATH = "research/walk_forward_latest.v1.json"


def load_research_config(config_path="config/config.yaml"):
    path = Path(config_path)
    if not path.exists():
        return {}

    with path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

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

    adapter_names = sorted({event.adapter for event in provenance_events})
    cache_hit_counts = {
        "hits": sum(1 for event in provenance_events if event.cache_hit),
        "misses": sum(1 for event in provenance_events if not event.cache_hit),
    }
    payload = {
        "run_id": run_id,
        "adapter_names": adapter_names,
        "cache_hit_counts": cache_hit_counts,
        "config_hash": _config_hash(research_config, provenance_events),
        "git_revision": _git_revision(),
        "as_of_utc": as_of_utc.isoformat(),
        "interval_ranges": interval_ranges,
        "fredapi_version": next((event.source_version for event in provenance_events if event.adapter == "fredapi"), None),
        "yfinance_version": next((event.source_version for event in provenance_events if event.adapter == "yfinance"), None),
    }

    with (target_dir / f"{run_id}.json").open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _sidecar_strategy_entry(
    strategy: dict,
    asset: str,
    interval: str,
    report: dict,
) -> dict:
    return {
        "strategy_name": strategy["name"],
        "asset": asset,
        "interval": interval,
        "selected_params": report.get("selected_params", {}),
        "selection_metric": report.get("selection_metric", "sharpe"),
        "is_summary": report.get("is_summary", {}),
        "oos_summary": report.get("oos_summary", {}),
        "folds": report.get("folds", []),
        "leakage_checks_ok": report.get("leakage_checks_ok", False),
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
    payload = {
        "version": "v1",
        "generated_at_utc": as_of_utc.astimezone(timezone.utc).isoformat(),
        "evaluation_config": evaluation_config,
        "strategies": strategy_reports,
    }
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _build_engine(start_datum: str, eind_datum: str, evaluation_config: dict) -> BacktestEngine:
    try:
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
            evaluation_config=evaluation_config,
        )
    except TypeError as exc:
        if "evaluation_config" not in str(exc):
            raise
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
        )


def run_research():
    rows = []
    walk_forward_reports = []
    provenance_events = []
    research_config = load_research_config()
    evaluation_config = normalize_evaluation_config(research_config.get("evaluation"))
    assets, intervals, get_date_range, as_of_utc = build_research_universe(research_config)
    interval_ranges = {}

    for interval in intervals:
        start_datum, eind_datum = get_date_range(interval)
        interval_ranges[interval] = {
            "start": start_datum,
            "end": eind_datum,
        }

    for strategy in get_enabled_strategies():
        for interval in intervals:
            for asset in assets:
                start_datum = interval_ranges[interval]["start"]
                eind_datum = interval_ranges[interval]["end"]

                engine = _build_engine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                    evaluation_config=evaluation_config,
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
                    report = getattr(engine, "last_evaluation_report", None)
                    if report is not None:
                        walk_forward_reports.append(
                            _sidecar_strategy_entry(
                                strategy=strategy,
                                asset=asset.symbol,
                                interval=interval,
                                report=report,
                            )
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

    print(f"Klaar. {len(rows)} resultaten geschreven.")


if __name__ == "__main__":
    run_research()
