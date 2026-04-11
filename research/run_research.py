"""
Research runner:
voert alle enabled strategieen uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import yaml

from agent.backtesting.engine import BacktestEngine
from research.registry import get_enabled_strategies
from research.results import make_result_row, write_latest_json, write_results_to_csv
from research.statistical_reporting import build_statistical_defensibility_payload, regime_count_settings
from research.universe import build_research_universe

SIDE_CAR_PATH = Path("research/statistical_defensibility_latest.v1.json")


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


def run_research():
    rows = []
    evaluations = []
    provenance_events = []
    research_config = load_research_config()
    regime_count, regime_count_source = regime_count_settings(research_config)
    assets, intervals, get_date_range, as_of_utc = build_research_universe(research_config)
    interval_ranges = {}
    strategies = get_enabled_strategies()

    for interval in intervals:
        start_datum, eind_datum = get_date_range(interval)
        interval_ranges[interval] = {"start": start_datum, "end": eind_datum}

    for strategy in strategies:
        for interval in intervals:
            for asset in assets:
                engine = BacktestEngine(
                    start_datum=interval_ranges[interval]["start"],
                    eind_datum=interval_ranges[interval]["end"],
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
                        evaluations.append(
                            {
                                "family": strategy["family"],
                                "interval": interval,
                                "selected_params": json.loads(row["params_json"]),
                                "evaluation_report": evaluation_report,
                                "row": row,
                            }
                        )
                except Exception as exc:
                    row = make_result_row(
                        strategy=strategy,
                        asset=asset.symbol,
                        interval=interval,
                        params={},
                        as_of_utc=as_of_utc,
                        metrics={},
                        error=str(exc),
                    )

                provenance_events.extend(getattr(engine, "_provenance_events", []))
                rows.append(row)

    write_results_to_csv(rows)
    write_latest_json(rows, as_of_utc=as_of_utc)
    _write_provenance_sidecar(
        research_config=research_config,
        as_of_utc=as_of_utc,
        interval_ranges=interval_ranges,
        provenance_events=provenance_events,
    )

    successful_rows = [row for row in rows if row["success"]]
    if evaluations and len(evaluations) != len(successful_rows):
        raise RuntimeError("successful research rows are missing evaluation samples for statistical defensibility")
    if evaluations and len(evaluations) == len(successful_rows):
        _write_statistical_defensibility_sidecar(
            evaluations=evaluations,
            as_of_utc=as_of_utc,
            intervals=intervals,
            market_count=len(assets),
            regime_count=regime_count,
            regime_count_source=regime_count_source,
        )

    print(f"Klaar. {len(rows)} resultaten geschreven.")


if __name__ == "__main__":
    run_research()
