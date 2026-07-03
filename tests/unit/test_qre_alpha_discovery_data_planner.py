from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_data.dataset_catalog import build_data_census, materialize_data_truth
from packages.qre_research.alpha_discovery.acquisition import execute_acquisition_once
from packages.qre_research.alpha_discovery.contracts import (
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    ExperimentContract,
    content_id,
)
from packages.qre_research.alpha_discovery.data_planner import (
    build_data_requirement,
    resolve_data_plan,
)
from packages.qre_research.alpha_discovery.universe_planner import plan_universe


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _contract(*, requested_tier: str, universe_spec: str = "single_asset_liquid_cache_universe") -> ExperimentContract:
    return ExperimentContract(
        experiment_id="qexp_fixture",
        hypothesis_id="qah_fixture",
        research_question="fixture question",
        predicted_observable="fixture observable",
        counter_hypothesis="fixture counter hypothesis",
        universe_spec=universe_spec,
        timeframe="1d",
        sampling_frequency="1d",
        required_data_fields=("close", "high", "low", "open", "volume"),
        required_history="ready cache window",
        required_point_in_time_metadata=("timestamp_utc",),
        required_features=("close",),
        signal_semantics="fixture",
        position_semantics="long_only",
        entry_semantics="fixture entry",
        exit_semantics="fixture exit",
        portfolio_semantics="single-strategy research only",
        null_models=("null_hold",),
        falsification_tests=("fixture falsification",),
        confounder_controls=("cost_only_baseline",),
        transaction_cost_model="canonical_fixed_cost_proxy",
        slippage_model="canonical_zero_slippage_proxy",
        IS_policy="fixture",
        validation_policy="fixture",
        locked_OOS_policy="fixture",
        embargo_policy="fixture",
        warmup_policy="fixture",
        minimum_signal_count=3,
        minimum_trade_count=3,
        success_criteria=("fixture",),
        failure_criteria=("fixture",),
        required_evidence_families=("controlled_evaluation",),
        requested_execution_tier=requested_tier,
        content_identity=content_id("qexp", {"fixture": True, "tier": requested_tier, "universe": universe_spec}),
    )


def _prepare_dataset(repo_root: Path, *, files: int = 2, rows_per_file: int = 5, timeframe: str = "1d", instrument: str = "AAPL") -> None:
    cache_dir = repo_root / "data/cache/market"
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_rows = []
    frames = []
    for index in range(files):
        start = pd.Timestamp("2026-04-08", tz="UTC") + pd.Timedelta(days=index * rows_per_file)
        frame = pd.DataFrame(
            {
                "timestamp_utc": pd.date_range(start, periods=rows_per_file, freq="D", tz="UTC"),
                "open": [float(i + 1) for i in range(rows_per_file)],
                "high": [float(i + 2) for i in range(rows_per_file)],
                "low": [float(i) for i in range(rows_per_file)],
                "close": [float(i + 1.5) for i in range(rows_per_file)],
                "volume": [100 + i for i in range(rows_per_file)],
            }
        )
        path = cache_dir / f"yfinance__{instrument}__{timeframe}__2026040{index+8}__2026041{index+5}__fixture{index}.parquet"
        frame.to_parquet(path, index=False)
        frames.append(frame)
        file_rows.append(
            {
                "path": path.relative_to(repo_root).as_posix(),
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": instrument,
                "timeframe": timeframe,
                "status": "ready",
                "row_count": len(frame),
                "min_timestamp_utc": frame["timestamp_utc"].iloc[0].isoformat().replace("+00:00", "Z"),
                "max_timestamp_utc": frame["timestamp_utc"].iloc[-1].isoformat().replace("+00:00", "Z"),
                "content_hash": f"sha256:test{index}",
                "identity_status": "ready",
            }
        )
    combined = pd.concat(frames, ignore_index=True)
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": True},
            "files": file_rows,
            "coverage": [
                {
                    "source": "yfinance",
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "file_count": files,
                    "row_count": len(combined),
                    "min_timestamp_utc": combined["timestamp_utc"].iloc[0].isoformat().replace("+00:00", "Z"),
                    "max_timestamp_utc": combined["timestamp_utc"].iloc[-1].isoformat().replace("+00:00", "Z"),
                    "content_hash": "sha256:logical",
                    "status_counts": {"ready": files},
                    "ready": True,
                }
            ],
        },
    )
    _write_json(
        repo_root / "logs/qre_data_source_quality_readiness/latest.json",
        {
            "schema_version": "1.0",
            "summary": {"status": "ready", "identity_status": "ready"},
            "rows": [
                {
                    "source": "yfinance",
                    "instrument": instrument,
                    "timeframe": timeframe,
                    "effective_research_quality_status": "ready",
                    "source_quality_status": "ready",
                    "identity_status": "ready",
                }
            ],
        },
    )


def test_census_explains_five_row_inventory_as_file_level_selection(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, files=2, rows_per_file=5)

    census = build_data_census(repo_root)

    assert census["root_cause"]["selector_behavior"] == "manifest.files preferred over manifest.coverage when files are present"
    assert census["root_cause"]["example_physical_row_count"] == 5
    assert census["root_cause"]["example_logical_row_count"] == 10
    assert "inventory_bug" in census["root_cause"]["causes"]


def test_data_plan_uses_logical_dataset_but_fails_closed_on_source_authority(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, files=3, rows_per_file=40)
    truth = materialize_data_truth(repo_root)
    experiment = _contract(requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING)
    universe = plan_universe(repo_root=repo_root, experiment=experiment, catalog=truth["catalog"])
    requirement = build_data_requirement(experiment, universe)

    decision, coverage, acquisition, _, _ = resolve_data_plan(repo_root, requirement, universe_plan=universe)

    assert decision.selected_data["row_count"] == 120
    assert decision.selected_data["dataset_partition_count"] == 3
    assert coverage.decision == "SOURCE_QUALITY_BLOCKED"
    assert acquisition.external_boundary == "STOPPED_SOURCE_QUALITY_BOUNDARY"
    assert decision.admissible_execution_tier == "EXECUTOR_SMOKE"


def test_cross_sectional_universe_fails_closed_without_point_in_time_membership(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, files=2, rows_per_file=50)
    truth = materialize_data_truth(repo_root)
    experiment = _contract(
        requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        universe_spec="cross_sectional_panel_universe",
    )

    universe = plan_universe(repo_root=repo_root, experiment=experiment, catalog=truth["catalog"])

    assert universe.point_in_time_required is True
    assert universe.point_in_time_status == "PIT_UNAVAILABLE"
    assert universe.final_universe_decision == "UNIVERSE_CAPABILITY_BLOCKED"


def test_replay_keeps_fingerprint_stable_and_avoids_duplicate_downloads(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, files=3, rows_per_file=40, instrument="BTC-EUR")

    truth = materialize_data_truth(repo_root)
    experiment = _contract(requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING)
    universe = plan_universe(repo_root=repo_root, experiment=experiment, catalog=truth["catalog"])
    requirement = build_data_requirement(experiment, universe)

    _, coverage, acquisition, _, _ = resolve_data_plan(repo_root, requirement, universe_plan=universe)
    first = execute_acquisition_once(repo_root=repo_root, plan=acquisition)
    second = execute_acquisition_once(repo_root=repo_root, plan=acquisition)

    assert first["rows_downloaded"] == 0
    assert second["rows_downloaded"] == 0
    assert first["provider_calls"] == 0
    assert second["provider_calls"] == 0
    assert first["content_identity"] == second["content_identity"]
