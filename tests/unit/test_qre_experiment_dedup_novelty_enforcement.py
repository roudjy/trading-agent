from __future__ import annotations

import json
from pathlib import Path

from research import qre_experiment_dedup_novelty_enforcement as novelty


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_experiment_dedup_novelty_enforcement_surfaces_duplicates_and_novelty(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "suppressed_scopes": [{"scope_kind": "exact_failed_scope", "suppression_reason": "same_failed_scope_suppressed"}],
            "eligible_directions": [
                {
                    "direction_id": "behavior_rotation::momentum_continuation",
                    "direction_type": "different_behavior_family",
                    "route_status": "eligible_context_only",
                    "eligibility_reasons": ["materially_new_behavior_direction"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json",
        {"record": {"memory_record_id": "mem-1"}},
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "campaign_id": "cmp-1",
                    "campaign_type": "daily_primary",
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "parent_campaign_id": None,
                    "lineage_root_campaign_id": "cmp-1",
                    "input_artifact_fingerprint": "fp-1",
                    "state": "running",
                    "hypothesis_id": "hyp-1",
                    "strategy_family": "trend_pullback",
                    "asset_class": "equity",
                },
                "cmp-2": {
                    "campaign_id": "cmp-2",
                    "campaign_type": "daily_primary",
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "parent_campaign_id": None,
                    "lineage_root_campaign_id": "cmp-1",
                    "input_artifact_fingerprint": "fp-1",
                    "state": "pending",
                    "hypothesis_id": "hyp-1",
                    "strategy_family": "trend_pullback",
                    "asset_class": "equity",
                },
            }
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_campaign_throughput_bottleneck_intelligence" / "latest.json",
        {
            "bottlenecks": [
                {
                    "bottleneck_code": "duplicate_low_value_run_pressure",
                    "exact_next_action": "increase_duplicate_avoidance_review",
                    "evidence_refs": ["research/campaign_digest_latest.v1.json"],
                }
            ]
        },
    )

    report = novelty.build_experiment_dedup_novelty_enforcement(repo_root=tmp_path)

    assert report["summary"]["experiment_dedup_novelty_enforcement_ready"] is True
    assert report["summary"]["suppressed_scope_count"] == 1
    assert report["summary"]["active_duplicate_fingerprint_count"] == 1
    assert report["summary"]["active_scope_conflict_count"] == 1
    assert report["summary"]["eligible_novel_direction_count"] == 1
    assert report["summary"]["exact_next_action"] == "deduplicate_active_campaign_scope"


def test_write_outputs_stays_inside_allowlist(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_research_cycle_router" / "latest.json", {"suppressed_scopes": [], "eligible_directions": []})
    _write_json(tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json", {"record": {"memory_record_id": "mem-1"}})
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})

    report = novelty.build_experiment_dedup_novelty_enforcement(repo_root=tmp_path)
    paths = novelty.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_experiment_dedup_novelty_enforcement/latest.json",
        "operator_summary": "logs/qre_experiment_dedup_novelty_enforcement/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
