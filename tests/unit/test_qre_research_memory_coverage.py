from __future__ import annotations

import json
from pathlib import Path

from research import qre_research_memory_coverage as memory_coverage


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_complete_aapl_repo(tmp_path: Path) -> None:
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


def test_build_research_memory_coverage_indexes_baskets_failures_and_reason_records(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = memory_coverage.build_research_memory_coverage(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["summary"]["indexed_basket_count"] == 2
    assert report["summary"]["indexed_failure_action_count"] == 2
    assert report["summary"]["indexed_reason_record_count"] >= 3
    assert report["summary"]["indexed_candidate_count"] == 2
    assert report["summary"]["final_recommendation"] == "research_memory_coverage_ready"


def test_build_failure_retrieval_is_deterministic_for_blocked_failures(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json", {"coverage": []})
    _write_json(tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json", {"rows": []})
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    left_memory = memory_coverage.build_research_memory_coverage(
        repo_root=tmp_path,
        max_candidates=5,
    )
    right_memory = memory_coverage.build_research_memory_coverage(
        repo_root=tmp_path,
        max_candidates=5,
    )
    left = memory_coverage.build_failure_retrieval(left_memory)
    right = memory_coverage.build_failure_retrieval(right_memory)

    assert left == right
    assert left["summary"]["failure_subject_count"] >= 1
    assert left["summary"]["retrievable_failure_subject_count"] >= 1
    assert any(row["similar_failures"] for row in left["rows"])


def test_build_failure_retrieval_filters_out_ready_only_rows(tmp_path: Path) -> None:
    memory = {
        "entries": [
            {
                "artifact_id": "failure:cand-1",
                "record_kind": "failure_action",
                "subject_id": "cand-1",
                "title": "AAPL ready_for_readonly_research",
                "metadata": {
                    "blocker_code": "ready_for_readonly_research",
                    "recommended_action": "eligible_for_readonly_routing",
                    "behavior_family": "trend",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                },
            }
        ]
    }
    retrieval = memory_coverage.build_failure_retrieval(memory)

    assert retrieval["summary"]["failure_subject_count"] == 0
    assert retrieval["summary"]["final_recommendation"] == "failure_retrieval_not_ready"


def test_write_outputs_writes_memory_and_failure_sidecars(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    memory = memory_coverage.build_research_memory_coverage(
        repo_root=tmp_path,
        max_candidates=2,
    )
    retrieval = memory_coverage.build_failure_retrieval(memory)
    paths = memory_coverage.write_outputs(memory, retrieval, repo_root=tmp_path)

    assert paths["memory_latest"] == "logs/qre_research_memory_coverage/latest.json"
    assert paths["failure_latest"] == "logs/qre_failure_retrieval/latest.json"
