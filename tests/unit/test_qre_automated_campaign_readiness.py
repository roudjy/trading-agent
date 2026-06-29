from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from packages.qre_research import automated_campaign_readiness as acr
from packages.qre_research import generated_strategy_paths as gsp


REPO_ROOT = Path(__file__).resolve().parents[2]


def _copy(repo_root: Path, relative: str) -> None:
    source = REPO_ROOT / relative
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _write_json(repo_root: Path, relative: str, payload: dict) -> None:
    target = repo_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def readiness_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative in (
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
    ):
        _copy(tmp_path, relative)
    _write_json(
        tmp_path,
        "logs/qre_identity_ambiguity_resolution/latest.json",
        {
            "report_kind": "qre_identity_ambiguity_resolution",
            "rows": [
                {
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                    "instrument_identity": "ASML",
                    "dataset_identity": "ready",
                    "resolution_state": "RESOLVED",
                },
                {
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                    "instrument_identity": "",
                    "dataset_identity": "",
                    "resolution_state": "MISSING",
                },
            ],
        },
    )
    _write_json(
        tmp_path,
        "logs/qre_data_cache_manifest/latest.json",
        {
            "report_kind": "qre_data_cache_manifest",
            "rows": [
                {
                    "instrument": "ASML",
                    "source": "yfinance",
                    "timeframe": "1d",
                    "content_hash": "sha256:test-asml-1d",
                    "min_timestamp_utc": "2024-01-01T00:00:00Z",
                    "max_timestamp_utc": "2026-01-01T00:00:00Z",
                    "ready": True,
                    "row_count": 500,
                }
            ],
        },
    )
    monkeypatch.setattr(acr, "validate_write_target", lambda path: None)
    return tmp_path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_strategy_paths_allow_readiness_surface() -> None:
    path = gsp.REPO_ROOT / "generated_research" / "readiness" / "gaps" / "sample.json"
    gsp.validate_write_target(path)


def test_run_readiness_remediation_is_deterministic(readiness_repo: Path) -> None:
    first = acr.run_readiness_remediation(repo_root=readiness_repo)
    second = acr.run_readiness_remediation(repo_root=readiness_repo)
    assert first["closeout_identity"] == second["closeout_identity"]
    assert first["strategy_summaries"] == second["strategy_summaries"]


def test_cross_sectional_strategy_decomposes_identity_blocker_exact_fields(
    readiness_repo: Path,
) -> None:
    acr.run_readiness_remediation(repo_root=readiness_repo)
    payload = _read_json(readiness_repo / acr.READINESS_GAPS_PATH.relative_to(acr.REPO_ROOT))
    row = next(
        item for item in payload["rows"] if item["generated_strategy_id"] == "qgs_e565b01bd0a162d0"
    )
    assert row["aggregate_blocker"] == "identity_not_resolved"
    assert "universe" in row["unresolved_fields"]
    assert "instrument" in row["unresolved_fields"]
    assert "dataset" in row["unresolved_fields"]
    assert "snapshot" in row["unresolved_fields"]


def test_cross_sectional_universe_alias_is_not_accepted_as_final_authority(
    readiness_repo: Path,
) -> None:
    acr.run_readiness_remediation(repo_root=readiness_repo)
    payload = _read_json(readiness_repo / acr.IDENTITY_DECISIONS_PATH.relative_to(acr.REPO_ROOT))
    row = next(
        item
        for item in payload["rows"]
        if item["generated_strategy_id"] == "qgs_e565b01bd0a162d0"
        and item["identity_class"] == "universe"
    )
    assert row["resolution_outcome"] == "BLOCKED_NON_AUTHORITATIVE_ONLY"
    assert row["selected_identity"] == ""


def test_single_instrument_strategy_blocks_on_timeframe_and_preset(
    readiness_repo: Path,
) -> None:
    acr.run_readiness_remediation(repo_root=readiness_repo)
    gaps = _read_json(readiness_repo / acr.READINESS_GAPS_PATH.relative_to(acr.REPO_ROOT))
    atr_row = next(
        item for item in gaps["rows"] if item["generated_strategy_id"] == "qgs_5af8f605ba82ae53"
    )
    timeframe_field = next(field for field in atr_row["fields"] if field["field_name"] == "timeframe")
    assert timeframe_field["state"] == "AMBIGUOUS"
    portfolio = _read_json(readiness_repo / acr.PORTFOLIO_PATH.relative_to(acr.REPO_ROOT))
    portfolio_row = next(
        item for item in portfolio["rows"] if item["generated_strategy_id"] == "qgs_5af8f605ba82ae53"
    )
    assert portfolio_row["status"] == "BLOCKED_WINDOWS"


def test_no_prereg_manifest_written_when_no_ready_cells(readiness_repo: Path) -> None:
    closeout = acr.run_readiness_remediation(repo_root=readiness_repo)
    assert closeout["summary"]["campaign_ready_cells"] == 0
    assert closeout["overall_outcome"] == "IDENTITY_RESOLUTION_BLOCKED"
    assert not (readiness_repo / acr.PREREG_MANIFEST_PATH.relative_to(acr.REPO_ROOT)).exists()
