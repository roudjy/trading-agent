from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_basket_evidence_density_materialization as density
from research import qre_real_basket_evidence_coverage as coverage


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_read_only_inputs(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "coverage": [
                {"instrument": "AAPL", "timeframe": "1d", "ready": True},
                {"instrument": "ASML", "timeframe": "1d", "ready": True},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [
                {"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"},
                {"instrument": "ASML", "timeframe": "1d", "quality_status": "ready"},
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "candidate_id": "candidate-aapl",
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_v1",
                    "qre_validation_linkage_status": "linked_catalog_active_discovery",
                    "validation_evidence": {
                        "status": "no_oos_trades",
                        "oos_trade_count": 0,
                    },
                },
                {
                    "candidate_id": "candidate-asml",
                    "asset": "ASML",
                    "hypothesis_id": "trend_pullback_v1",
                    "qre_validation_linkage_status": "linked_catalog_active_discovery",
                    "validation_evidence": {
                        "status": None,
                        "oos_trade_count": None,
                    },
                },
            ]
        },
    )
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})


def test_density_materialization_links_local_screening_and_oos_rows(tmp_path: Path) -> None:
    _seed_read_only_inputs(tmp_path)

    report = density.build_basket_evidence_density_materialization(repo_root=tmp_path, max_candidates=2)
    paths = density.write_outputs(report, repo_root=tmp_path)
    coverage_report = coverage.build_real_basket_evidence_coverage(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["report_kind"] == "qre_basket_evidence_density_materialization"
    assert report["summary"]["screening_evidence_present_count"] == 2
    assert report["summary"]["oos_evidence_known_count"] == 1
    assert paths["latest"] == "logs/qre_basket_evidence_density_materialization/latest.json"
    assert paths["operator_summary"] == "logs/qre_basket_evidence_density_materialization/operator_summary.md"

    rows = {row["symbol"]: row for row in coverage_report["rows"]}
    aapl = rows["AAPL"]
    asml = rows["ASML"]
    assert aapl["evidence_counts"]["screening_rows"] == 1
    assert "screening_evidence_missing" not in aapl["missing_evidence_taxonomy"]
    assert "oos_evidence_missing" not in aapl["missing_evidence_taxonomy"]
    assert aapl["validation_evidence_status_counts"] == {"no_oos_trades": 1}
    assert asml["evidence_counts"]["screening_rows"] == 1
    assert "screening_evidence_missing" not in asml["missing_evidence_taxonomy"]
    assert "oos_evidence_missing" not in asml["missing_evidence_taxonomy"]
    assert coverage_report["summary"]["screening_evidence_rows_total"] == 2
    assert coverage_report["summary"]["evidence_backed_zero_screening"] is False


def test_density_materialization_preserves_asmi_identity_blocker(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = density.build_basket_evidence_density_materialization(repo_root=tmp_path, max_candidates=5)
    rows = {row["symbol"]: row for row in report["rows"]}

    assert rows["ASMI"]["source_identity_status"] == "candidate_alias_only"
    assert rows["ASMI"]["source_identity_blocker"] == "source_identity_candidate_alias_unverified"
    assert rows["ASMI"]["screening_evidence_rows"] == 0
    assert rows["ASMI"]["oos_evidence_status"] == "oos_evidence_missing"
    assert report["summary"]["source_identity_blocked_count"] == 1


def test_density_write_outputs_writes_only_allowlisted_paths(tmp_path: Path) -> None:
    _seed_read_only_inputs(tmp_path)
    report = density.build_basket_evidence_density_materialization(repo_root=tmp_path, max_candidates=2)
    paths = density.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_basket_evidence_density_materialization/latest.json"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
    with pytest.raises(ValueError):
        density.write_outputs(report, repo_root=tmp_path, output_dir=Path("outside"))
