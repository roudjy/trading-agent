from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from packages.qre_research import automated_campaign_readiness as acr
from packages.qre_research import automated_data_window_capacity as adwc
from packages.qre_research import autonomous_readiness_closure as arc
from packages.qre_research import generated_strategy_paths as gsp

REPO_ROOT = Path(__file__).resolve().parents[2]

_COPIED_INPUTS = (
    "generated_research/registry/generated_strategy_registry.v1.json",
    "generated_research/presets/generated_research_presets.v1.json",
    "generated_research/lineage/generated_null_controls.v1.json",
    "generated_research/lineage/generated_campaign_lineage.v1.json",
    "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
    "generated_research/hypotheses/registry/resolved_thesis_catalog.v1.json",
    "generated_research/specs/qsp_16800d656bf28677.json",
    "generated_research/specs/qsp_28cdbc0005ae7c93.json",
    "artifacts/identity/instrument_identity_latest.v1.json",
    "artifacts/universe/equity_universe_catalog_latest.v1.json",
)


def _copy(repo_root: Path, relative: str) -> None:
    source = REPO_ROOT / relative
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    target.chmod(0o666)


def _write_json(repo_root: Path, relative: str, payload: dict) -> None:
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _patch_paths(monkeypatch: pytest.MonkeyPatch, repo_root: Path) -> None:
    readiness_root = repo_root / "generated_research" / "readiness"
    monkeypatch.setattr(arc, "GENERATED_READINESS_ROOT", readiness_root)
    monkeypatch.setattr(arc, "BLOCKERS_PATH", readiness_root / "reports" / "autonomous_readiness_blockers.v1.json")
    monkeypatch.setattr(arc, "ITERATION_LEDGER_PATH", readiness_root / "reports" / "autonomous_readiness_iteration_ledger.v1.json")
    monkeypatch.setattr(arc, "UNIVERSE_AUTHORITY_PATH", readiness_root / "identity_decisions" / "autonomous_universe_authority.v1.json")
    monkeypatch.setattr(arc, "TIMEFRAME_RESOLUTION_PATH", readiness_root / "reports" / "autonomous_timeframe_resolution.v1.json")
    monkeypatch.setattr(arc, "PRESET_COMPLETION_PATH", readiness_root / "presets" / "autonomous_completed_presets.v1.json")
    monkeypatch.setattr(arc, "DATA_BINDING_PATH", readiness_root / "data_bindings" / "autonomous_strategy_data_bindings.v1.json")
    monkeypatch.setattr(arc, "WINDOW_CAPACITY_PATH", readiness_root / "window_capacity" / "autonomous_window_capacity.v1.json")
    monkeypatch.setattr(arc, "NULL_CONTROL_PATH", readiness_root / "null_controls" / "autonomous_null_control_readiness.v1.json")
    monkeypatch.setattr(arc, "CAMPAIGN_METADATA_PATH", readiness_root / "campaigns" / "autonomous_campaign_metadata.v1.json")
    monkeypatch.setattr(arc, "CAMPAIGN_LINEAGE_PATH", readiness_root / "campaigns" / "autonomous_campaign_lineage.v1.json")
    monkeypatch.setattr(arc, "PORTFOLIO_PATH", readiness_root / "campaigns" / "autonomous_portfolio_readiness.v1.json")
    monkeypatch.setattr(arc, "MANIFEST_PATH", readiness_root / "campaigns" / "autonomous_second_campaign_manifest.v1.json")
    monkeypatch.setattr(arc, "CLOSEOUT_JSON_PATH", readiness_root / "reports" / "autonomous_readiness_closeout.v1.json")
    monkeypatch.setattr(arc, "CLOSEOUT_MD_PATH", readiness_root / "reports" / "autonomous_readiness_closeout.v1.md")

    monkeypatch.setattr(adwc, "GENERATED_READINESS_ROOT", readiness_root)
    monkeypatch.setattr(adwc, "DATA_CAPACITY_DIR", readiness_root / "data_capacity")
    monkeypatch.setattr(adwc, "SNAPSHOTS_DIR", readiness_root / "snapshots")
    monkeypatch.setattr(adwc, "WINDOW_LEDGER_DIR", readiness_root / "window_ledger")
    monkeypatch.setattr(adwc, "CAMPAIGNS_DIR", readiness_root / "campaigns")
    monkeypatch.setattr(adwc, "REPORTS_DIR", readiness_root / "reports")
    monkeypatch.setattr(adwc, "DATA_DIAGNOSIS_PATH", readiness_root / "data_capacity" / "strategy_data_capacity_diagnosis.v1.json")
    monkeypatch.setattr(adwc, "DATA_AUTHORITY_PATH", readiness_root / "data_capacity" / "canonical_data_cache_authority.v1.json")
    monkeypatch.setattr(adwc, "MATERIALIZED_CACHE_ROWS_PATH", readiness_root / "data_capacity" / "materialized_cache_rows.v1.json")
    monkeypatch.setattr(adwc, "QUALITY_PATH", readiness_root / "data_capacity" / "strategy_data_quality_coverage.v1.json")
    monkeypatch.setattr(adwc, "SNAPSHOTS_PATH", readiness_root / "snapshots" / "immutable_strategy_snapshots.v1.json")
    monkeypatch.setattr(adwc, "WINDOW_POLICY_PATH", readiness_root / "window_capacity" / "authoritative_window_policy.v1.json")
    monkeypatch.setattr(adwc, "WINDOW_LEDGER_PATH", readiness_root / "window_ledger" / "canonical_window_ledger.v1.json")
    monkeypatch.setattr(adwc, "WINDOW_ASSIGNMENTS_PATH", readiness_root / "window_capacity" / "authoritative_window_assignments.v1.json")
    monkeypatch.setattr(adwc, "INDEPENDENCE_PATH", readiness_root / "window_capacity" / "oos_independence_proof.v1.json")
    monkeypatch.setattr(adwc, "PIT_UNIVERSE_PATH", readiness_root / "window_capacity" / "point_in_time_universe_validation.v1.json")
    monkeypatch.setattr(adwc, "SIGNAL_CAPACITY_PATH", readiness_root / "window_capacity" / "signal_density_capacity.v1.json")
    monkeypatch.setattr(adwc, "PORTFOLIO_PATH", readiness_root / "campaigns" / "automated_portfolio_readiness.v1.json")
    monkeypatch.setattr(adwc, "MANIFEST_PATH", readiness_root / "campaigns" / "generated_second_campaign_manifest.v1.json")
    monkeypatch.setattr(adwc, "ITERATION_LEDGER_PATH", readiness_root / "reports" / "automated_data_window_iteration_ledger.v1.json")
    monkeypatch.setattr(adwc, "CLOSEOUT_JSON_PATH", readiness_root / "reports" / "automated_data_window_capacity_closeout.v1.json")
    monkeypatch.setattr(adwc, "CLOSEOUT_MD_PATH", readiness_root / "reports" / "automated_data_window_capacity_closeout.v1.md")


def _build_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, directory_name: str) -> Path:
    repo_root = tmp_path / directory_name
    for relative in _COPIED_INPUTS:
        _copy(repo_root, relative)
    _write_json(
        repo_root,
        "logs/qre_identity_ambiguity_resolution/latest.json",
        {
            "report_kind": "qre_identity_ambiguity_resolution",
            "rows": [
                {
                    "dataset_identity": "equity-ohlcv-us-v1",
                    "instrument_identity": "ASML",
                    "resolution_state": "RESOLVED",
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                },
                {
                    "dataset_identity": "equity-ohlcv-us-v1",
                    "instrument_identity": "AAPL",
                    "resolution_state": "RESOLVED",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                },
                {
                    "dataset_identity": "equity-ohlcv-us-v1",
                    "instrument_identity": "MSFT",
                    "resolution_state": "RESOLVED",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                },
                {
                    "dataset_identity": "equity-ohlcv-us-v1",
                    "instrument_identity": "NVDA",
                    "resolution_state": "RESOLVED",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                },
                {
                    "dataset_identity": "equity-ohlcv-us-v1",
                    "instrument_identity": "AMD",
                    "resolution_state": "RESOLVED",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                },
            ],
        },
    )
    _write_json(
        repo_root,
        "artifacts/cache/cache_coverage_latest.v1.json",
        {
            "report_kind": "qre_cache_coverage",
            "coverage": [
                {
                    "content_hash": "sha256:asml-1d",
                    "instrument": "ASML",
                    "max_timestamp_utc": "2026-05-22T00:00:00Z",
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "ready": True,
                    "row_count": 2315,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:asml-4h",
                    "instrument": "ASML",
                    "max_timestamp_utc": "2026-04-24T17:30:00Z",
                    "min_timestamp_utc": "2024-05-28T13:30:00Z",
                    "ready": True,
                    "row_count": 952,
                    "source": "yfinance",
                    "timeframe": "4h",
                },
                {
                    "content_hash": "sha256:aapl-1d",
                    "instrument": "AAPL",
                    "max_timestamp_utc": "2026-05-22T00:00:00Z",
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "ready": True,
                    "row_count": 2380,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:amd-1d",
                    "instrument": "AMD",
                    "max_timestamp_utc": "2026-05-22T00:00:00Z",
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "ready": True,
                    "row_count": 2270,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:msft-1d",
                    "instrument": "MSFT",
                    "max_timestamp_utc": "2026-05-22T00:00:00Z",
                    "min_timestamp_utc": "2026-04-08T00:00:00Z",
                    "ready": True,
                    "row_count": 2325,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:nvda-1d",
                    "instrument": "NVDA",
                    "max_timestamp_utc": "2026-05-22T00:00:00Z",
                    "min_timestamp_utc": "2026-04-06T00:00:00Z",
                    "ready": True,
                    "row_count": 2425,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
            ],
        },
    )
    _write_json(
        repo_root,
        "logs/qre_data_cache_manifest/latest.json",
        {
            "report_kind": "qre_data_cache_manifest",
            "coverage": [
                {
                    "content_hash": "sha256:aapl-1d-fresh",
                    "instrument": "AAPL",
                    "max_timestamp_utc": "2026-06-30T00:00:00Z",
                    "min_timestamp_utc": "2025-10-01T00:00:00Z",
                    "ready": True,
                    "row_count": 3200,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:amd-1d-fresh",
                    "instrument": "AMD",
                    "max_timestamp_utc": "2026-06-30T00:00:00Z",
                    "min_timestamp_utc": "2025-10-01T00:00:00Z",
                    "ready": True,
                    "row_count": 3180,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:msft-1d-fresh",
                    "instrument": "MSFT",
                    "max_timestamp_utc": "2026-06-30T00:00:00Z",
                    "min_timestamp_utc": "2025-10-01T00:00:00Z",
                    "ready": True,
                    "row_count": 3210,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:nvda-1d-fresh",
                    "instrument": "NVDA",
                    "max_timestamp_utc": "2026-06-30T00:00:00Z",
                    "min_timestamp_utc": "2025-10-01T00:00:00Z",
                    "ready": True,
                    "row_count": 3300,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
            ],
            "files": [],
        },
    )
    monkeypatch.setattr(acr, "validate_write_target", lambda path: None)
    monkeypatch.setattr(arc, "validate_write_target", lambda path: None)
    monkeypatch.setattr(adwc, "validate_write_target", lambda path: None)
    _patch_paths(monkeypatch, repo_root)
    return repo_root


@pytest.fixture
def readiness_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _build_repo(tmp_path, monkeypatch, directory_name="repo")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_strategy_paths_allow_a24_surfaces() -> None:
    for relative in (
        "generated_research/readiness/data_capacity/sample.json",
        "generated_research/readiness/snapshots/sample.json",
        "generated_research/readiness/window_ledger/sample.json",
    ):
        gsp.validate_write_target(gsp.REPO_ROOT / Path(relative))


def test_run_data_window_closure_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first_repo = _build_repo(tmp_path, monkeypatch, directory_name="first")
    first = adwc.run_data_window_closure(repo_root=first_repo)
    second_repo = _build_repo(tmp_path, monkeypatch, directory_name="second")
    second = adwc.run_data_window_closure(repo_root=second_repo)
    assert first["data_capacity_closeout_id"] == second["data_capacity_closeout_id"]
    assert first["portfolio_rows"] == second["portfolio_rows"]


def test_missing_1h_cache_row_stays_fail_closed(readiness_repo: Path) -> None:
    adwc.run_data_window_closure(repo_root=readiness_repo)
    payload = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "data_capacity"
        / "strategy_data_capacity_diagnosis.v1.json"
    )
    row = next(
        item
        for item in payload["rows"]
        if item["campaign_cell_id"] == "qrcell_d5ded3130f132558"
    )
    assert row["status"] == "CACHE_ROW_MISSING"


def test_4h_asml_cell_becomes_ready_and_manifest_is_created(readiness_repo: Path) -> None:
    result = adwc.run_data_window_closure(repo_root=readiness_repo)
    row = next(
        item
        for item in result["portfolio_rows"]
        if item["campaign_cell_id"] == "qrcell_fdd68e20fd2724dd"
    )
    assert row["status"] == "READY_FOR_PREREGISTRATION"
    assert result["overall_outcome"] == "READY_FOR_SECOND_CAMPAIGN"
    manifest = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "campaigns"
        / "generated_second_campaign_manifest.v1.json"
    )
    assert manifest["campaign_manifest_identity"].startswith("qcm_")
    assert any(item["campaign_cell_id"] == "qrcell_fdd68e20fd2724dd" for item in manifest["rows"])


def test_short_span_single_instrument_1d_cell_stays_window_blocked(readiness_repo: Path) -> None:
    result = adwc.run_data_window_closure(repo_root=readiness_repo)
    row = next(
        item
        for item in result["portfolio_rows"]
        if item["campaign_cell_id"] == "qrcell_41d3efbcaa2aeddb"
    )
    assert row["status"] == "BLOCKED_WINDOWS"
    assert row["blockers"] == ["usable_history_below_minimum_policy_span"]


def test_fresher_manifest_coverage_overrides_stale_artifact_for_cross_sectional_cell(
    readiness_repo: Path,
) -> None:
    result = adwc.run_data_window_closure(repo_root=readiness_repo)
    row = next(
        item
        for item in result["portfolio_rows"]
        if item["campaign_cell_id"] == "qrcell_44aa81da7c2fc7c9"
    )
    assert row["status"] == "READY_FOR_PREREGISTRATION"
    assert row["blockers"] == []
    manifest = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "campaigns"
        / "generated_second_campaign_manifest.v1.json"
    )
    assert any(item["campaign_cell_id"] == "qrcell_44aa81da7c2fc7c9" for item in manifest["rows"])


def test_window_ledger_reserves_windows_for_ready_cell(readiness_repo: Path) -> None:
    adwc.run_data_window_closure(repo_root=readiness_repo)
    ledger = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "window_ledger"
        / "canonical_window_ledger.v1.json"
    )
    ready_rows = [
        row
        for row in ledger["rows"]
        if row["campaign_cell_id"] == "qrcell_fdd68e20fd2724dd"
    ]
    assert {row["purpose"] for row in ready_rows} == {"TRAIN", "VALIDATION", "OOS"}
    assert all(row["status"] == "RESERVED" for row in ready_rows)
