from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from packages.qre_research import automated_campaign_readiness as acr
from packages.qre_research import autonomous_readiness_closure as arc


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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(repo_root: Path, relative: str, payload: dict) -> None:
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _patch_arc_paths(
    monkeypatch: pytest.MonkeyPatch,
    repo_root: Path,
) -> None:
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


def _build_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    directory_name: str,
) -> Path:
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
                    "content_hash": "sha256:aapl-1d",
                    "instrument": "AAPL",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "min_timestamp_utc": "2020-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 1500,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:msft-1d",
                    "instrument": "MSFT",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "min_timestamp_utc": "2020-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 1500,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:nvda-1d",
                    "instrument": "NVDA",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "min_timestamp_utc": "2020-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 1500,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:asml-1d",
                    "instrument": "ASML",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "min_timestamp_utc": "2020-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 1500,
                    "source": "yfinance",
                    "timeframe": "1d",
                },
                {
                    "content_hash": "sha256:asml-4h",
                    "instrument": "ASML",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "min_timestamp_utc": "2020-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 6000,
                    "source": "yfinance",
                    "timeframe": "4h",
                },
            ],
        },
    )
    monkeypatch.setattr(acr, "validate_write_target", lambda path: None)
    monkeypatch.setattr(arc, "validate_write_target", lambda path: None)
    _patch_arc_paths(monkeypatch, repo_root)
    return repo_root


@pytest.fixture
def readiness_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _build_repo(tmp_path, monkeypatch, directory_name="repo")


def test_run_autonomous_closure_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_repo = _build_repo(tmp_path, monkeypatch, directory_name="first")
    first = arc.run_autonomous_closure(repo_root=first_repo, max_iterations=8)
    second_repo = _build_repo(tmp_path, monkeypatch, directory_name="second")
    second = arc.run_autonomous_closure(repo_root=second_repo, max_iterations=8)
    assert first["closeout_identity"] == second["closeout_identity"]
    assert first["strategy_outcomes"] == second["strategy_outcomes"]


def test_cross_sectional_alias_resolves_to_authoritative_universe(
    readiness_repo: Path,
) -> None:
    arc.run_autonomous_closure(repo_root=readiness_repo, max_iterations=8)
    payload = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "identity_decisions"
        / "autonomous_universe_authority.v1.json"
    )
    row = next(
        item
        for item in payload["rows"]
        if item["generated_strategy_id"] == "qgs_e565b01bd0a162d0"
    )
    assert row["resolution_outcome"] == "RESOLVED_UNIQUE_AUTHORITATIVE"
    assert row["selected_universe_id"] != ""
    assert row["membership_snapshot_id"].startswith("qum_")
    assert len(row["included_members"]) >= 3


def test_multi_timeframe_strategy_splits_and_1h_fails_closed_on_data_capacity(
    readiness_repo: Path,
) -> None:
    result = arc.run_autonomous_closure(repo_root=readiness_repo, max_iterations=8)
    atr_rows = [
        row
        for row in result["strategy_outcomes"]
        if row["generated_strategy_id"] == "qgs_5af8f605ba82ae53"
    ]
    assert {row["timeframe"] for row in atr_rows} == {"1d", "4h", "1h"}
    outcomes_by_timeframe = {row["timeframe"]: row["terminal_outcome"] for row in atr_rows}
    assert outcomes_by_timeframe["1h"] == "DATA_CAPACITY_BLOCKED"
    assert outcomes_by_timeframe["1d"] == "INDEPENDENT_OOS_CAPACITY_BLOCKED"
    assert outcomes_by_timeframe["4h"] == "INDEPENDENT_OOS_CAPACITY_BLOCKED"


def test_upstream_data_blocker_suppresses_downstream_preset_blocker_for_1h_cell(
    readiness_repo: Path,
) -> None:
    arc.run_autonomous_closure(repo_root=readiness_repo, max_iterations=8)
    portfolio = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "campaigns"
        / "autonomous_portfolio_readiness.v1.json"
    )
    cell = next(
        row
        for row in portfolio["rows"]
        if row["generated_strategy_id"] == "qgs_5af8f605ba82ae53" and row["timeframe"] == "1h"
    )
    blockers = _read_json(
        readiness_repo
        / "generated_research"
        / "readiness"
        / "reports"
        / "autonomous_readiness_blockers.v1.json"
    )
    cell_blockers = [
        row["blocker_class"]
        for row in blockers["rows"]
        if row["affected_campaign_cell"] == cell["campaign_cell_id"]
    ]
    assert "DATA_COVERAGE_INSUFFICIENT" in cell_blockers
    assert "PRESET_INCOMPLETE" not in cell_blockers


def test_no_manifest_is_written_when_no_cells_are_ready(readiness_repo: Path) -> None:
    result = arc.run_autonomous_closure(repo_root=readiness_repo, max_iterations=8)
    assert result["summary"]["ready_for_preregistration_count"] == 0
    assert result["manifest"] == {}
    assert not (
        readiness_repo
        / "generated_research"
        / "readiness"
        / "campaigns"
        / "autonomous_second_campaign_manifest.v1.json"
    ).exists()
