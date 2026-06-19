from __future__ import annotations

import json
from pathlib import Path

from research import qre_campaign_throughput_bottleneck_intelligence as throughput_intel


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_campaign_throughput_bottleneck_intelligence_surfaces_divergence_and_pressure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "campaign_id": "cmp-1",
                    "state": "running",
                    "outcome": None,
                },
                "cmp-2": {
                    "campaign_id": "cmp-2",
                    "state": "failed",
                    "outcome": "technical_failure",
                },
            }
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_queue_latest.v1.json",
        {"queue": [{"campaign_id": "cmp-3", "state": "pending"}]},
    )
    _write_json(
        tmp_path / "research" / "campaign_digest_latest.v1.json",
        {
            "queue_depth": 1,
            "campaigns_completed": 0,
            "campaigns_failed": 1,
            "meaningful_campaigns_total": 0,
            "meaningful_by_classification": {"duplicate_low_value_run": 2},
            "top_failure_reasons": [{"reason_code": "technical_failure", "count": 1}],
        },
    )
    monkeypatch.setattr(
        throughput_intel.cache_throughput,
        "read_throughput_status",
        lambda **_: {
            "status": "not_ready",
            "research_ready": False,
            "path": "logs/qre_cache_throughput_manifest/latest.json",
            "fails_closed": True,
        },
    )
    monkeypatch.setattr(
        throughput_intel.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {
            "summary": {
                "artifact_freshness_status": "stale_or_missing",
                "exact_next_safe_action": "reconcile_stale_or_mismatched_run_artifacts",
            }
        },
    )

    report = throughput_intel.build_campaign_throughput_bottleneck_intelligence(
        repo_root=tmp_path
    )

    assert report["summary"]["campaign_throughput_bottleneck_intelligence_ready"] is True
    assert report["summary"]["queue_registry_divergence_count"] == 2
    assert report["summary"]["duplicate_low_value_run_count"] == 2
    assert report["summary"]["cache_throughput_ready"] is False
    assert report["summary"]["exact_next_action"] == "reconcile_campaign_queue_from_registry"
    codes = [row["bottleneck_code"] for row in report["bottlenecks"]]
    assert "queue_registry_divergence" in codes
    assert "cache_throughput_not_ready" in codes
    assert "stale_run_artifact_pressure" in codes
    assert "duplicate_low_value_run_pressure" in codes


def test_write_outputs_stays_inside_allowlist(tmp_path: Path, monkeypatch) -> None:
    _write_json(tmp_path / "research" / "campaign_registry_latest.v1.json", {"campaigns": {}})
    _write_json(tmp_path / "research" / "campaign_queue_latest.v1.json", {"queue": []})
    _write_json(
        tmp_path / "research" / "campaign_digest_latest.v1.json",
        {
            "queue_depth": 0,
            "campaigns_completed": 1,
            "campaigns_failed": 0,
            "meaningful_campaigns_total": 1,
            "meaningful_by_classification": {},
        },
    )
    monkeypatch.setattr(
        throughput_intel.cache_throughput,
        "read_throughput_status",
        lambda **_: {
            "status": "ready",
            "research_ready": True,
            "path": "logs/qre_cache_throughput_manifest/latest.json",
            "fails_closed": False,
        },
    )
    monkeypatch.setattr(
        throughput_intel.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {
            "summary": {
                "artifact_freshness_status": "fresh",
                "exact_next_safe_action": "preserve_terminal_run_and_compare_before_rerun",
            }
        },
    )

    report = throughput_intel.build_campaign_throughput_bottleneck_intelligence(
        repo_root=tmp_path
    )
    paths = throughput_intel.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_campaign_throughput_bottleneck_intelligence/latest.json",
        "operator_summary": "logs/qre_campaign_throughput_bottleneck_intelligence/operator_summary.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
