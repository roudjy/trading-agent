from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from packages.qre_research import second_preregistered_campaign as campaign

REPO_ROOT = Path(__file__).resolve().parents[2]

_COPIED_INPUTS = (
    "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
    "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
    "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
    "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
    "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
    "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
    "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
    "generated_research/registry/generated_strategy_registry.v1.json",
    "generated_research/specs/qsp_28cdbc0005ae7c93.json",
    "generated_research/validation/qgs_e565b01bd0a162d0.json",
    "generated_research/lineage/generated_null_controls.v1.json",
    "agent/backtesting/generated_strategies/generated_qgs_e565b01bd0a162d0.py",
)


def _copy(repo_root: Path, relative: str) -> None:
    source = REPO_ROOT / relative
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(0o666)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_manifest(repo_root: Path) -> None:
    payload = {
        "campaign_manifest_identity": "qcm_fixture_cross_sectional",
        "schema_version": "1.0",
        "module_version": "ade-qre-024.1",
        "report_kind": "qre_generated_second_campaign_manifest",
        "rows": [
            {
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "strategy_spec_id": "qsp_28cdbc0005ae7c93",
                "preset_id": "qgp_2b995bee52e0662b",
                "dataset_identity": "qds_fixture_cross_sectional",
                "snapshot_identity": "qsn_fixture_cross_sectional",
                "timeframe": "1d",
                "train_window": {
                    "start": "2026-04-08T00:00:00Z",
                    "end": "2026-05-20T00:00:00Z",
                },
                "validation_window": {
                    "start": "2026-05-24T00:00:00Z",
                    "end": "2026-06-06T00:00:00Z",
                },
                "oos_window": {
                    "start": "2026-06-10T00:00:00Z",
                    "end": "2026-06-24T00:00:00Z",
                },
            }
        ],
    }
    _write_json(
        repo_root / "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
        payload,
    )


def _filter_rows(repo_root: Path, relative: str, *, campaign_cell_id: str) -> None:
    path = repo_root / relative
    payload = _read_json(path)
    payload["rows"] = [
        row for row in payload["rows"] if row.get("campaign_cell_id") == campaign_cell_id
    ]
    if relative.endswith("automated_portfolio_readiness.v1.json"):
        row = payload["rows"][0]
        row["status"] = "READY_FOR_PREREGISTRATION"
        row["blockers"] = []
        row["preset_id"] = "qgp_2b995bee52e0662b"
        row["dataset_identity"] = "qds_fixture_cross_sectional"
        row["snapshot_identity"] = "qsn_fixture_cross_sectional"
        row["train_window"] = {
            "start": "2026-04-08T00:00:00Z",
            "end": "2026-05-20T00:00:00Z",
        }
        row["validation_window"] = {
            "start": "2026-05-24T00:00:00Z",
            "end": "2026-06-06T00:00:00Z",
        }
        row["oos_window"] = {
            "start": "2026-06-10T00:00:00Z",
            "end": "2026-06-24T00:00:00Z",
        }
    elif relative.endswith("immutable_strategy_snapshots.v1.json"):
        row = payload["rows"][0]
        row["dataset_identity"] = "qds_fixture_cross_sectional"
        row["snapshot_identity"] = "qsn_fixture_cross_sectional"
        row["coverage_start_utc"] = "2026-04-08T00:00:00Z"
        row["coverage_end_utc"] = "2026-06-24T00:00:00Z"
    elif relative.endswith("authoritative_window_assignments.v1.json"):
        row = payload["rows"][0]
        row["window_policy_outcome"] = "WINDOW_POLICY_READY"
        row["reason"] = ""
        row["train_window"] = {
            "start": "2026-04-08T00:00:00Z",
            "end": "2026-05-20T00:00:00Z",
        }
        row["validation_window"] = {
            "start": "2026-05-24T00:00:00Z",
            "end": "2026-06-06T00:00:00Z",
        }
        row["oos_window"] = {
            "start": "2026-06-10T00:00:00Z",
            "end": "2026-06-24T00:00:00Z",
        }
    elif relative.endswith("oos_independence_proof.v1.json"):
        payload["rows"][0]["outcome"] = "INDEPENDENCE_PROVEN"
        payload["rows"][0]["reason"] = ""
    elif relative.endswith("signal_density_capacity.v1.json"):
        payload["rows"][0]["outcome"] = "SIGNAL_CAPACITY_READY"
        payload["rows"][0]["reason"] = ""
    elif relative.endswith("strategy_data_quality_coverage.v1.json"):
        row = payload["rows"][0]
        row["quality_state"] = "QUALITY_READY"
        row["coverage_map"] = [
            {
                "source": "yfinance",
                "instrument": instrument,
                "timeframe": "1d",
                "start": "2026-04-08T00:00:00Z",
                "end": "2026-06-24T00:00:00Z",
            }
            for instrument in ("AAPL", "AMD", "MSFT", "NVDA")
        ]
    _write_json(path, payload)


def _write_window_ledger(repo_root: Path) -> None:
    payload = {
        "window_ledger_identity": "qwlr_fixture",
        "rows": [
            {
                "window_id": "qwl_fixture_train",
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "purpose": "TRAIN",
                "status": "RESERVED",
                "window": {"start": "2026-04-08T00:00:00Z", "end": "2026-05-20T00:00:00Z"},
            },
            {
                "window_id": "qwl_fixture_validation",
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "purpose": "VALIDATION",
                "status": "RESERVED",
                "window": {"start": "2026-05-24T00:00:00Z", "end": "2026-06-06T00:00:00Z"},
            },
            {
                "window_id": "qwl_fixture_oos",
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "purpose": "OOS",
                "status": "RESERVED",
                "window": {"start": "2026-06-10T00:00:00Z", "end": "2026-06-24T00:00:00Z"},
            },
        ],
    }
    _write_json(
        repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
        payload,
    )


def _write_cache_manifest(repo_root: Path) -> None:
    files: list[dict[str, object]] = []
    for instrument in ("AAPL", "AMD", "MSFT", "NVDA"):
        rel = f"data/cache/market/yfinance__{instrument}__1d__20260408__20260624__fixture.parquet"
        files.append(
            {
                "path": rel,
                "cache_kind": "market",
                "source": "yfinance",
                "instrument": instrument,
                "timeframe": "1d",
                "status": "ready",
                "row_count": 56,
                "min_timestamp_utc": "2026-04-08T00:00:00Z",
                "max_timestamp_utc": "2026-06-24T00:00:00Z",
                "content_hash": f"sha256:{instrument.lower()}",
            }
        )
    _write_json(repo_root / "logs/qre_data_cache_manifest/latest.json", {"files": files})


def _write_cache_rows(repo_root: Path) -> None:
    timestamps = pd.date_range("2026-04-08T00:00:00Z", "2026-06-24T00:00:00Z", freq="B", tz="UTC")
    offsets = {"AAPL": 0.0, "AMD": 5.0, "MSFT": 10.0, "NVDA": 15.0}
    for instrument, offset in offsets.items():
        base = np.linspace(100.0 + offset, 140.0 + offset, len(timestamps), dtype=float)
        frame = pd.DataFrame(
            {
                "timestamp_utc": timestamps,
                "open": base,
                "high": base + 1.0,
                "low": base - 1.0,
                "close": base + 0.5,
                "volume": np.full(len(timestamps), 1_000.0 + offset, dtype=float),
            }
        )
        target = repo_root / f"data/cache/market/yfinance__{instrument}__1d__20260408__20260624__fixture.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(target, index=False)


def _fake_evaluate_strategy(frame: pd.DataFrame, bundle: dict[str, object]) -> dict[str, pd.Series]:
    assert isinstance(frame.index, pd.MultiIndex)
    index = frame.index
    signal = pd.Series(0, index=index, dtype=int)
    position = pd.Series(0, index=index, dtype=int)
    returns = pd.Series(0.001, index=index, dtype=float)
    assets = sorted(set(index.get_level_values(1)))
    windows = {
        "train": ("2026-04-08T00:00:00Z", "2026-05-20T00:00:00Z", 12),
        "validation": ("2026-05-24T00:00:00Z", "2026-06-06T00:00:00Z", 4),
        "oos": ("2026-06-10T00:00:00Z", "2026-06-24T00:00:00Z", 3),
    }
    for asset_index, asset in enumerate(assets):
        asset_mask = index.get_level_values(1) == asset
        asset_index_values = index[asset_mask]
        for start, end, count in windows.values():
            window_index = [
                idx
                for idx in asset_index_values
                if pd.Timestamp(start) <= idx[0] <= pd.Timestamp(end)
            ]
            active = window_index[asset_index :: max(1, len(assets))][:count]
            for idx in active:
                signal.loc[idx] = 1 if asset_index % 2 == 0 else -1
                position.loc[idx] = 1 if asset_index % 2 == 0 else -1
    gross_returns = position.astype(float) * returns
    turnover = campaign._turnover(position)
    return {
        "signal": signal,
        "position": position,
        "returns": returns,
        "gross_returns": gross_returns,
        "turnover": turnover,
    }


@pytest.fixture
def qre025_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = tmp_path / "repo"
    for relative in _COPIED_INPUTS:
        _copy(repo_root, relative)
    _write_manifest(repo_root)
    for relative in (
        "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
        "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
        "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
        "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
        "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
    ):
        _filter_rows(repo_root, relative, campaign_cell_id="qrcell_44aa81da7c2fc7c9")
    _write_window_ledger(repo_root)
    _write_cache_manifest(repo_root)
    _write_cache_rows(repo_root)
    monkeypatch.setattr(campaign, "_evaluate_strategy", _fake_evaluate_strategy)
    monkeypatch.setattr(campaign, "validate_write_target", lambda path: None)
    return repo_root


def test_generated_strategy_paths_allow_campaign_execution_surface() -> None:
    from packages.qre_research import generated_strategy_paths as gsp

    for relative in (
        "generated_research/campaign_execution/manifest_integrity/sample.json",
        "generated_research/campaign_execution/stages/sample.json",
        "generated_research/campaign_execution/evidence/sample.json",
        "generated_research/campaign_execution/ledgers/sample.json",
        "generated_research/campaign_execution/reports/sample.json",
    ):
        gsp.validate_write_target(gsp.REPO_ROOT / Path(relative))


def test_manifest_verification_passes_on_cross_sectional_bundle(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["manifest_integrity"]["status"] == "MANIFEST_VERIFIED"
    assert result["executed_campaign_cell"] == "qrcell_44aa81da7c2fc7c9"
    assert result["selection"]["source_hypothesis_id"] == "cross_sectional_momentum_v0"


def test_strategy_hash_mismatch_blocks_execution(qre025_repo: Path) -> None:
    registry_path = qre025_repo / "generated_research/registry/generated_strategy_registry.v1.json"
    payload = _read_json(registry_path)
    row = next(item for item in payload["rows"] if item["generated_strategy_id"] == "qgs_e565b01bd0a162d0")
    row["code_hash"] = "deadbeef"
    _write_json(registry_path, payload)

    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["manifest_integrity"]["status"] == "STRATEGY_HASH_MISMATCH"
    assert result["terminal_outcome"] == "NO_SAFE_AUTOMATED_NEXT_ACTION"


def test_current_hypothesis_campaign_is_classified_without_fixture_or_historical_leakage(
    qre025_repo: Path,
) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["campaign_classification"] == {
        "current_hypothesis_campaigns_executed": 1,
        "new_empirical_campaigns_completed": 1,
        "historical_campaigns_consumed": 0,
        "fixture_campaigns_consumed": 0,
        "null_or_synthetic_campaigns_executed": 0,
    }


def test_oos_window_is_consumed_in_canonical_ledger(qre025_repo: Path) -> None:
    campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    ledger = _read_json(
        qre025_repo
        / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json"
    )
    oos_row = next(row for row in ledger["rows"] if row["window_id"] == "qwl_fixture_oos")
    assert oos_row["status"] == "CONSUMED"
    assert oos_row["consumption_evidence"]["campaign_cell_id"] == "qrcell_44aa81da7c2fc7c9"


def test_second_run_is_deterministic_for_manifest_and_closeout(qre025_repo: Path) -> None:
    first = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    second = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert first["closeout_identity"] == second["closeout_identity"]
    assert first["manifest_integrity"]["manifest_integrity_identity"] == second["manifest_integrity"]["manifest_integrity_identity"]


def test_oos_stage_uses_exact_frozen_window(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    assert result["oos_stage"]["oos_window_id"] == "qwl_fixture_oos"
    assert result["oos_stage"]["trade_count"] >= 3


def test_null_controls_execute_with_frozen_seed(qre025_repo: Path) -> None:
    result = campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    rows = result["null_controls"]["rows"]
    assert {row["control_class"] for row in rows} == {
        "permuted_cross_sectional_ranking",
    }
    assert all(row["deterministic_seed"] for row in rows)


def test_shuffled_signal_timing_uses_deterministic_rotation() -> None:
    index = pd.date_range("2026-01-01", periods=6, freq="D")
    position = pd.Series([0, 1, 1, 0, 0, 1], index=index, dtype=int)

    first = campaign._shuffled_signal_timing(position, "seed-alpha")
    second = campaign._shuffled_signal_timing(position, "seed-alpha")
    third = campaign._shuffled_signal_timing(position, "seed-beta")

    assert first.equals(second)
    assert sorted(first.tolist()) == sorted(position.tolist())
    assert not first.equals(position)
    assert not first.equals(third)


def test_campaign_execution_outputs_are_materialized(qre025_repo: Path) -> None:
    campaign.run_second_preregistered_campaign(repo_root=qre025_repo)
    for relative in (
        "generated_research/campaign_execution/manifest_integrity/second_campaign_manifest_integrity.v1.json",
        "generated_research/campaign_execution/stages/train_and_screening.v1.json",
        "generated_research/campaign_execution/stages/validation.v1.json",
        "generated_research/campaign_execution/stages/oos.v1.json",
        "generated_research/campaign_execution/stages/null_controls.v1.json",
        "generated_research/campaign_execution/evidence/evidence_reason_records.v1.json",
        "generated_research/campaign_execution/ledgers/oos_consumption.v1.json",
        "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
    ):
        assert (qre025_repo / relative).is_file(), relative
