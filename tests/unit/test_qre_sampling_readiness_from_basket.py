from __future__ import annotations

import json
from pathlib import Path

from research import qre_sampling_readiness_from_basket as sampling


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_sampling_readiness_marks_ready_only_after_routing_ready(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
                    },
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
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )

    report = sampling.build_sampling_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )
    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["sampling_readiness_state"] == "ready"
    assert aapl["sampling_ready"] is True
    assert aapl["primary_reason_code"] == "sampling_ready_for_readonly_requirements"


def test_build_sampling_readiness_keeps_blocked_source_identity(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = sampling.build_sampling_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=5,
    )
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["ASMI"]["sampling_readiness_state"] == "blocked"
    assert rows["ASMI"]["sampling_ready"] is False


def test_build_sampling_readiness_proves_zero_ready_is_evidence_backed(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = sampling.build_sampling_readiness_from_basket(
        repo_root=tmp_path,
        max_candidates=2,
    )
    assert report["summary"]["sampling_ready_count"] == 0
    assert report["summary"]["evidence_backed_zero_ready"] is True
    assert report["summary"]["final_recommendation"] == "nothing_sampling_ready_evidence_backed"


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    report = sampling.build_sampling_readiness_from_basket(repo_root=tmp_path, max_candidates=1)
    markdown = sampling.render_operator_summary(report)
    paths = sampling.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Sampling Readiness From Basket Evidence" in markdown
    assert "## 2. Sampling readiness counts" in markdown
    assert paths["latest"] == "logs/qre_sampling_readiness_from_basket/latest.json"
    assert paths["operator_summary"] == "logs/qre_sampling_readiness_from_basket/operator_summary.md"
