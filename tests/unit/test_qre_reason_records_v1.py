from __future__ import annotations

import json
from pathlib import Path

from research import qre_reason_records_v1 as records_v1


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo(tmp_path: Path) -> None:
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


def test_build_reason_records_snapshot_emits_records_for_basket_routing_sampling(
    tmp_path: Path,
) -> None:
    _seed_repo(tmp_path)

    snapshot = records_v1.build_reason_records_snapshot(repo_root=tmp_path, max_candidates=1)

    assert snapshot["meta"]["record_count"] == 3
    assert snapshot["meta"]["records_by_surface"] == {
        "basket_diagnosis": 1,
        "routing_readiness": 1,
        "sampling_readiness": 1,
    }
    for record in snapshot["records"]:
        assert record["evidence_refs"]
        assert record["reason_codes"]
        assert record["reason_text"]


def test_build_reason_records_snapshot_fails_closed_when_refs_missing(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": []},
    )
    _write_json(tmp_path / "research" / "screening_evidence_latest.v1.json", {"candidates": []})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "candidate_registry_latest.v1.json", {"candidates": []})

    original = records_v1._basket_evidence_refs
    try:
        records_v1._basket_evidence_refs = lambda row: []  # type: ignore[assignment]
        snapshot = records_v1.build_reason_records_snapshot(repo_root=tmp_path, max_candidates=1)
    finally:
        records_v1._basket_evidence_refs = original  # type: ignore[assignment]

    assert snapshot["meta"]["skipped_missing_refs_count"] >= 1
    assert snapshot["meta"]["final_recommendation"] == "reason_records_v1_fail_closed_missing_refs"


def test_write_outputs_writes_jsonl_and_meta(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    snapshot = records_v1.build_reason_records_snapshot(repo_root=tmp_path, max_candidates=1)
    paths = records_v1.write_outputs(snapshot, repo_root=tmp_path)

    assert paths["latest_jsonl"] == "logs/qre_reason_records/latest.jsonl"
    assert paths["latest_meta"] == "logs/qre_reason_records/latest.meta.json"
    jsonl_lines = (tmp_path / paths["latest_jsonl"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(jsonl_lines) == 3
    meta = json.loads((tmp_path / paths["latest_meta"]).read_text(encoding="utf-8"))
    assert meta["meta"]["record_count"] == 3
