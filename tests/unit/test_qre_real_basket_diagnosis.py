from __future__ import annotations

import json
from pathlib import Path

from research import qre_real_basket_diagnosis as diagnosis


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_real_basket_diagnosis_classifies_baskets_conservatively(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "summary": {"research_ready": True},
            "coverage": [
                {
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "ready": True,
                },
                {
                    "instrument": "TTE",
                    "timeframe": "1d",
                    "ready": True,
                },
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "summary": {"research_ready": True},
            "rows": [
                {
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "quality_status": "ready",
                },
                {
                    "instrument": "TTE",
                    "timeframe": "1d",
                    "quality_status": "blocked",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                        "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {"status": "sufficient_oos_evidence"},
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                        "preset_name": "trend_pullback_continuation_daily_v1",
                        "hypothesis_id": "trend_pullback_behavior_v1",
                        "state": "completed",
                    }
                }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {
            "candidates": [{"asset": "AAPL", "status": "candidate"}]
        },
    )

    report = diagnosis.build_real_basket_diagnosis(repo_root=tmp_path, max_candidates=2)

    assert report["report_kind"] == "qre_real_basket_diagnosis"
    assert report["summary"]["basket_inventory_count"] == 2
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["AAPL"]["diagnosis_class"] == "diagnosable"
    assert rows["AAPL"]["reason_code"] == "source_and_cache_evidence_available"
    assert rows["AAPL"]["current_evidence"]["screening_rows"] == 1
    assert rows["AAPL"]["current_evidence"]["campaign_rows"] == 1
    assert rows["AAPL"]["current_evidence"]["candidate_rows"] == 1
    assert rows["ASML"]["diagnosis_class"] == "deferred"
    assert rows["ASML"]["reason_code"] == "no_matching_real_basket_evidence"


def test_build_real_basket_diagnosis_blocks_candidate_alias_only_symbols(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"summary": {"research_ready": True}, "coverage": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"summary": {"research_ready": True}, "rows": []},
    )

    report = diagnosis.build_real_basket_diagnosis(repo_root=tmp_path, max_candidates=5)

    rows = {row["symbol"]: row for row in report["rows"]}
    row = rows["ASMI"]
    assert row["diagnosis_class"] == "blocked"
    assert row["reason_code"] == "source_identity_candidate_alias_unverified"
    assert row["follow_up"] == "resolve_source_identity"


def test_build_real_basket_diagnosis_fails_closed_when_supporting_artifacts_are_missing(
    tmp_path: Path,
) -> None:
    report = diagnosis.build_real_basket_diagnosis(repo_root=tmp_path, max_candidates=2)

    row = report["rows"][0]
    assert row["diagnosis_class"] == "unknown_fail_closed"
    assert row["reason_code"] == "supporting_artifacts_missing"
    assert report["summary"]["artifact_availability"]["cache_manifest"] is False
    assert report["summary"]["fail_closed"] is True


def test_render_operator_summary_includes_counts_and_rows(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "summary": {"research_ready": True},
            "coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "summary": {"research_ready": True},
            "rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}],
        },
    )
    report = diagnosis.build_real_basket_diagnosis(repo_root=tmp_path, max_candidates=2)

    markdown = diagnosis.render_operator_summary(report)

    assert "# QRE Real Basket Diagnosis" in markdown
    assert "## 2. Diagnosis counts" in markdown
    assert "## 3. Basket diagnosis" in markdown
    assert "| AAPL | trend_pullback_continuation_daily_v1 | 1d | diagnosable | source_and_cache_evidence_available | 1 | 1 | 0 | eligible_for_readonly_diagnosis |" in markdown
    assert "| ASML | trend_continuation_daily_v1 | 1d | deferred | no_matching_real_basket_evidence | 0 | 0 | 0 | collect_cache_or_screening_evidence |" in markdown


def test_write_outputs_writes_only_inside_allowlisted_log_dir(tmp_path: Path) -> None:
    report = diagnosis.build_real_basket_diagnosis(repo_root=tmp_path, max_candidates=1)

    paths = diagnosis.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_real_basket_diagnosis/latest.json"
    assert paths["operator_summary"] == "logs/qre_real_basket_diagnosis/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
