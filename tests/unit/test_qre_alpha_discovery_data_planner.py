from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from packages.qre_research.alpha_discovery.contracts import (
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
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


def _contract(*, requested_tier: str) -> ExperimentContract:
    return ExperimentContract(
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
        minimum_signal_count=3,
        minimum_trade_count=3,
        success_criteria=("fixture",),
        failure_criteria=("fixture",),
        required_evidence_families=("controlled_evaluation",),
        requested_execution_tier=requested_tier,
        content_identity=content_id("qexp", {"fixture": True, "tier": requested_tier}),
    )


def _prepare_dataset(
    repo_root: Path,
    *,
    row_count: int,
    start: str,
    source_ready: bool,
    identity_status: str = "ready",
) -> Path:
    cache_path = repo_root / "data/cache/market/yfinance__AAPL__1d__fixture.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        {
            "timestamp_utc": pd.date_range(start, periods=row_count, freq="D", tz="UTC"),
            "open": [float(index + 1) for index in range(row_count)],
            "high": [float(index + 2) for index in range(row_count)],
            "low": [float(index) for index in range(row_count)],
            "close": [float(index + 1.5) for index in range(row_count)],
            "volume": [100 + index for index in range(row_count)],
        }
    )
    frame.to_parquet(cache_path, index=False)
    _write_json(
        repo_root / "logs/qre_data_cache_manifest/latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_data_cache_manifest",
            "summary": {"research_ready": source_ready},
            "files": [
                {
                    "path": cache_path.relative_to(repo_root).as_posix(),
                    "cache_kind": "market",
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "status": "ready",
                    "row_count": row_count,
                    "min_timestamp_utc": frame["timestamp_utc"].iloc[0].isoformat().replace("+00:00", "Z"),
                    "max_timestamp_utc": frame["timestamp_utc"].iloc[-1].isoformat().replace("+00:00", "Z"),
                    "content_hash": "sha256:test",
                    "identity_status": identity_status,
                }
            ],
        },
    )
    _write_json(
        repo_root / "logs/qre_data_source_quality_readiness/latest.json",
        {
            "schema_version": "1.0",
            "summary": {"status": "ready" if source_ready else "blocked", "identity_status": identity_status},
            "rows": [
                {
                    "source": "yfinance",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "effective_research_quality_status": "ready" if source_ready else "blocked",
                    "source_quality_status": "ready" if source_ready else "blocked",
                    "identity_status": identity_status,
                }
            ],
        },
    )
    return cache_path


def test_tiny_cache_row_is_only_executor_smoke_when_upstream_source_is_blocked(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, row_count=5, start="2026-04-08", source_ready=False)

    requirement = build_data_requirement(_contract(requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING))
    decision = resolve_data_plan(repo_root, requirement)

    assert decision.decision == "CACHE_READY"
    assert decision.admissible_execution_tier == EXECUTION_TIER_EXECUTOR_SMOKE
    assert "source_quality_not_research_ready" in decision.tier_downgrade_reasons
    assert decision.selected_data["effective_research_quality_status"] == "blocked"


def test_sufficient_history_without_locked_oos_caps_at_empirical_screening(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, row_count=120, start="2026-01-01", source_ready=True)

    requirement = build_data_requirement(_contract(requested_tier=EXECUTION_TIER_LOCKED_OOS_VALIDATION))
    decision = resolve_data_plan(repo_root, requirement)

    assert decision.decision == "CACHE_READY"
    assert decision.admissible_execution_tier == EXECUTION_TIER_EMPIRICAL_SCREENING
    assert "locked_oos_not_available" in decision.tier_downgrade_reasons


def test_row_ready_but_identity_ambiguous_fails_closed_for_empirical_admission(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _prepare_dataset(repo_root, row_count=120, start="2026-01-01", source_ready=True, identity_status="ambiguous")

    requirement = build_data_requirement(_contract(requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING))
    decision = resolve_data_plan(repo_root, requirement)

    assert decision.admissible_execution_tier == EXECUTION_TIER_EXECUTOR_SMOKE
    assert "identity_not_resolved" in decision.tier_downgrade_reasons
