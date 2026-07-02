from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_research.alpha_discovery.contracts import (
    ExperimentContract,
    content_id,
)
from packages.qre_research.alpha_discovery.data_planner import (
    build_data_requirement,
    resolve_data_plan,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_resolve_data_plan_uses_ready_cache_file_even_when_manifest_is_not_research_ready(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    cache_path = repo_root / "data/cache/market/yfinance__AAPL__1d__20260408__20260415__abc.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range("2026-04-08", periods=5, freq="D", tz="UTC"),
            "open": [1.0, 1.1, 1.2, 1.3, 1.4],
            "high": [1.1, 1.2, 1.3, 1.4, 1.5],
            "low": [0.9, 1.0, 1.1, 1.2, 1.3],
            "close": [1.05, 1.15, 1.25, 1.35, 1.45],
            "volume": [100, 110, 120, 130, 140],
        }
    )
    frame.to_parquet(cache_path, index=False)
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": False},
            "files": [
                {
                    "path": cache_path.relative_to(repo_root).as_posix(),
                    "cache_kind": "market",
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "status": "ready",
                    "row_count": 5,
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "max_timestamp_utc": "2026-04-12T00:00:00Z",
                    "content_hash": "sha256:test",
                }
            ],
            "coverage": [
                {
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "status": "ready",
                    "row_count": 5,
                    "content_hash": "sha256:test",
                }
            ],
        },
    )
    _write_json(repo_root / "logs/qre_data_source_quality_readiness/latest.json", {"schema_version": "1.0", "rows": []})

    contract = ExperimentContract(
        experiment_id="qexp_fixture",
        hypothesis_id="qah_fixture",
        research_question="fixture question",
        predicted_observable="fixture observable",
        counter_hypothesis="fixture counter hypothesis",
        universe_spec="single_asset_liquid_cache_universe",
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
        minimum_signal_count=1,
        minimum_trade_count=1,
        success_criteria=("fixture",),
        failure_criteria=("fixture",),
        required_evidence_families=("controlled_evaluation",),
        content_identity=content_id("qexp", {"fixture": True}),
    )

    requirement = build_data_requirement(contract)
    decision = resolve_data_plan(repo_root, requirement)

    assert decision.decision == "CACHE_READY"
    assert decision.approved_fetch is False
    assert decision.selected_data["selected_row"]["path"] == cache_path.relative_to(repo_root).as_posix()
    assert decision.selected_data["row_count"] == 5
    assert "frame" in decision.selected_data
