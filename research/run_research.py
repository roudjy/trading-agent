"""
Research runner:
voert alle enabled strategieën uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import yaml

from agent.backtesting.engine import BacktestEngine
from research.registry import get_enabled_strategies
from research.results import make_result_row, write_results_to_csv, write_latest_json
from research.universe import build_research_universe


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

def run_research():
    rows = []
    provenance_events = []
    research_config = load_research_config()
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

                engine = BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
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
    _write_provenance_sidecar(
        research_config=research_config,
        as_of_utc=as_of_utc,
        interval_ranges=interval_ranges,
        provenance_events=provenance_events,
    )

    print(f"Klaar. {len(rows)} resultaten geschreven.")


if __name__ == "__main__":
    run_research()
