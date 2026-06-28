from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_repeated_independent_oos as repeated


FROZEN = "2026-06-28T15:00:00Z"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _registry_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_behavior_thesis_registry",
        "rows": [
            {
                "thesis_id": "qbt_alpha",
                "source_hypothesis_id": "alpha_v0",
                "title": "Alpha",
                "behavior_family": "trend",
                "strategy_family": "alpha",
                "status": "draft",
                "provenance_refs": ["registry:alpha"],
            },
            {
                "thesis_id": "qbt_trend",
                "source_hypothesis_id": "trend_pullback_v1",
                "title": "Trend Pullback",
                "behavior_family": "pullback",
                "strategy_family": "trend_pullback",
                "status": "research_ready",
                "provenance_refs": ["registry:trend"],
            },
        ],
    }


def _operator_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_operator_decision_report",
        "summary": {
            "decision_counts": {
                "SUPPORTED_FOR_REVIEW": 0,
                "REJECTED": 1,
                "INSUFFICIENT_EVIDENCE": 0,
                "BLOCKED": 1,
            }
        },
        "rows": [
            {
                "source_hypothesis_id": "alpha_v0",
                "final_decision": "BLOCKED",
                "next_action": "establish_campaign_lineage_for_thesis",
                "oos": {
                    "accepted_oos_count": None,
                    "accepted_window_count": None,
                    "closure_status": "",
                    "independence_visible": False,
                    "positive_oos_trade_count_total": None,
                },
                "contradictions": {"decay_contradiction_state": "contradicting_evidence_visible"},
                "null_controls": {"status": "null_controls_not_visible"},
                "provenance_refs": ["operator:alpha"],
            },
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "final_decision": "REJECTED",
                "next_action": "reject_hypothesis",
                "oos": {
                    "accepted_oos_count": 0,
                    "accepted_window_count": 0,
                    "closure_status": "all_windows_no_oos_trades",
                    "independence_visible": False,
                    "positive_oos_trade_count_total": 0,
                },
                "contradictions": {"decay_contradiction_state": "contradicting_evidence_visible"},
                "null_controls": {
                    "status": "controls_incomplete",
                    "missing_control_ids": ["null_preregistered_holdout"],
                    "recommended_next_action": "materialize_missing_preregistered_controls",
                },
                "provenance_refs": ["operator:trend"],
            },
        ],
    }


def _lineage_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_contradiction_hypothesis_lineage",
        "rows": [
            {
                "source_hypothesis_id": "alpha_v0",
                "lineage_complete": False,
                "missing_lineage_fields": ["campaign_identity", "data_snapshot_identity"],
                "graph_nodes": {
                    "campaign": [],
                    "data_snapshot": [],
                    "source": [],
                },
                "provenance_refs": ["lineage:alpha"],
            },
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "lineage_complete": True,
                "missing_lineage_fields": [],
                "graph_nodes": {
                    "campaign": ["campaign::trend"],
                    "data_snapshot": ["evidence::historical_accounting_foundation"],
                    "source": ["evidence::source_lifecycle_quality_gate"],
                },
                "provenance_refs": ["lineage:trend"],
            },
        ],
    }


def _replay_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_same_input_replay",
        "replay_assessment_identity": "qrab_fixture",
        "source_manifest_identity": "qcm_fixture",
        "source_execution_identity": "qcy_fixture",
        "summary": {
            "blocker_reasons": [
                "no_approved_single_class_change_visible",
                "same_input_control_confirmation_only",
                "zero_executable_cells_visible",
                "zero_oos_acceptance_visible",
            ]
        },
    }


def _run_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_preregistered_multiwindow_evidence_run",
        "campaign_scope": {
            "hypothesis_id": "trend_pullback_v1",
            "campaign_id": "campaign-trend",
            "preset_name": "trend_pullback_equities_4h",
        },
        "window_results": [
            {
                "bounded_input_window": {"start": "2024-07-01", "end": "2025-06-17"},
                "oos_window": {"start": "2025-03-05", "end": "2025-06-17"},
                "accepted_oos_count": 0,
                "positive_oos_trade_count_total": 0,
            },
            {
                "bounded_input_window": {"start": "2025-06-18", "end": "2026-06-04"},
                "oos_window": {"start": "2026-02-20", "end": "2026-06-04"},
                "accepted_oos_count": 0,
                "positive_oos_trade_count_total": 0,
            },
        ],
    }


def _closure_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_multiwindow_evidence_closure",
        "closure_status": "all_windows_no_oos_trades",
        "hypothesis_disposition": "fail_closed_rejected",
    }


def test_collect_snapshot_fails_closed_when_only_rejected_campaign_has_oos_windows(tmp_path: Path) -> None:
    snapshot = repeated.collect_snapshot(
        registry_path=_write_json(tmp_path / "registry.json", _registry_payload()),
        operator_path=_write_json(tmp_path / "operator.json", _operator_payload()),
        lineage_path=_write_json(tmp_path / "lineage.json", _lineage_payload()),
        replay_path=_write_json(tmp_path / "replay.json", _replay_payload()),
        run_path=_write_json(tmp_path / "run.json", _run_payload()),
        closure_path=_write_json(tmp_path / "closure.json", _closure_payload()),
        generated_at_utc=FROZEN,
    )

    assert snapshot["decision"] == "INSUFFICIENT_EVIDENCE"
    assert snapshot["summary"]["independent_ready_count"] == 0
    assert snapshot["summary"]["consumed_window_count"] == 2
    assert snapshot["summary"]["status_counts"]["BLOCKED_MISSING_CAMPAIGN_LINEAGE"] == 1
    assert snapshot["summary"]["status_counts"]["BLOCKED_REJECTED_NO_ACCEPTED_OOS"] == 1
    assert snapshot["summary"]["final_recommendation"] == "no_valid_independent_oos_path_materialized"

    trend_row = next(row for row in snapshot["rows"] if row["source_hypothesis_id"] == "trend_pullback_v1")
    assert trend_row["independent_oos_status"] == "BLOCKED_REJECTED_NO_ACCEPTED_OOS"
    assert trend_row["independent_oos_decision"] == "INSUFFICIENT_EVIDENCE"
    assert trend_row["consumed_window_count"] == 2
    assert trend_row["consumed_oos_windows"][0]["oos_window"]["start"] == "2025-03-05"
    assert trend_row["consumed_oos_windows"][1]["oos_window"]["start"] == "2026-02-20"
    assert trend_row["consumed_oos_windows"][0]["window_identity_visible"] is False
    assert "window_identity_not_materialized_in_source_artifact" in trend_row["consumed_oos_windows"][0]["window_identity_blockers"]
    assert "operator_decision_rejected" in trend_row["independent_window_assessment"]["blocker_reasons"]

    blocked_row = next(row for row in snapshot["rows"] if row["source_hypothesis_id"] == "alpha_v0")
    assert blocked_row["independent_oos_status"] == "BLOCKED_MISSING_CAMPAIGN_LINEAGE"
    assert blocked_row["lineage_update"]["lineage_complete"] is False
    assert blocked_row["next_action"] == "establish_campaign_lineage_for_thesis"


def test_collect_snapshot_is_deterministic(tmp_path: Path) -> None:
    kwargs = {
        "registry_path": _write_json(tmp_path / "registry.json", _registry_payload()),
        "operator_path": _write_json(tmp_path / "operator.json", _operator_payload()),
        "lineage_path": _write_json(tmp_path / "lineage.json", _lineage_payload()),
        "replay_path": _write_json(tmp_path / "replay.json", _replay_payload()),
        "run_path": _write_json(tmp_path / "run.json", _run_payload()),
        "closure_path": _write_json(tmp_path / "closure.json", _closure_payload()),
        "generated_at_utc": FROZEN,
    }
    first = repeated.collect_snapshot(**kwargs)
    second = repeated.collect_snapshot(**kwargs)

    assert first == second
    assert first["independent_oos_identity"].startswith("qrao_")
    for row in first["rows"]:
        assert row["independent_oos_status"] in repeated.ROW_STATUS_VOCAB
        assert row["independent_oos_decision"] in repeated.DECISION_VOCAB


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        repeated._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(repeated.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token
