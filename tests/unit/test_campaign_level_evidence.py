"""Tests for campaign-level evidence materialization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research import campaign_level_evidence as cle

CAMPAIGN_ID = "col-1"


def _statuses() -> dict[str, dict[str, str]]:
    return {
        name: {"path": path.as_posix(), "status": "present"}
        for name, path in cle.ARTIFACT_PATHS.items()
    }


def _artifacts() -> dict:
    return {
        "campaign_registry": {
            "campaigns": {
                CAMPAIGN_ID: {
                    "campaign_id": CAMPAIGN_ID,
                    "state": "completed",
                    "outcome": "completed_no_survivor",
                    "preset_name": "trend_pullback_equities_4h",
                    "strategy_family": "trend_pullback",
                    "asset_class": "equities",
                    "finished_at_utc": "2026-06-05T10:26:32Z",
                    "extra": {
                        "gate_diagnostics": {
                            "classification": "promotion_gate_rejected_all",
                            "stage": "promotion",
                            "source_run_id": "run-1",
                            "source_artifact_fingerprint": "fingerprint-1",
                            "counts": {
                                "total_candidates": 15,
                                "passed_screening": 6,
                                "rejected_screening": 9,
                                "promotion_grade_candidates": 0,
                                "exploratory_passes": 0,
                                "near_passes": 0,
                                "sufficient_oos_evidence_candidates": 1,
                            },
                            "dominant_failure_reasons": ["insufficient_trades"],
                        }
                    },
                }
            }
        },
        "screening_evidence": {
            "campaign_id": CAMPAIGN_ID,
            "col_campaign_id": CAMPAIGN_ID,
            "run_id": "run-1",
            "artifact_fingerprint": "fingerprint-1",
            "summary": {
                "total_candidates": 15,
                "passed_screening": 6,
                "rejected_screening": 9,
                "promotion_grade_candidates": 0,
                "sufficient_oos_evidence_candidates": 1,
                "dominant_failure_reasons": ["insufficient_trades"],
            },
        },
        "research_state": {
            "failure_attribution": {
                "state": "gate_rejection_attributed",
                "attributed": True,
                "missing": [],
            },
            "next_allowed_actions": ["collect_campaign_level_evidence"],
            "next_best_test": "collect_campaign_level_evidence",
            "synthesis_gate": "not_allowed_yet",
        },
        "research_action_plan": {
            "next_best_action": {"action_id": "collect_campaign_level_evidence"}
        },
        "campaign_evidence_ledger": [],
    }


def test_builds_owned_attributed_campaign_evidence() -> None:
    payload = cle.build_campaign_level_evidence_payload(
        artifacts=_artifacts(),
        artifact_status=_statuses(),
        generated_at_utc=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
    )

    assert payload["evidence_status"] == "attributed"
    assert payload["campaign"]["campaign_id"] == CAMPAIGN_ID
    assert payload["screening_evidence"]["owner_verified"] is True
    assert payload["screening_evidence"]["classification"] == "promotion_gate_rejected_all"
    assert payload["screening_evidence"]["counts"]["total_candidates"] == 15
    assert payload["screening_evidence"]["counts"]["passed_screening"] == 6
    assert payload["screening_evidence"]["counts"]["promotion_grade_candidates"] == 0
    assert payload["interpretation"]["primary_limitation"] == ("insufficient_trades")
    assert payload["safety_invariants"]["runs_campaign"] is False


def test_mismatched_screening_owner_fails_closed() -> None:
    artifacts = _artifacts()
    artifacts["campaign_registry"]["campaigns"][CAMPAIGN_ID]["extra"] = {}
    artifacts["screening_evidence"]["col_campaign_id"] = "col-other"

    payload = cle.build_campaign_level_evidence_payload(
        artifacts=artifacts,
        artifact_status=_statuses(),
    )

    assert payload["screening_evidence"]["owner_verified"] is False
    assert payload["screening_evidence"]["counts"]["total_candidates"] == 0
    assert payload["evidence_status"] == "incomplete_unattributed"


def test_missing_ledger_is_reported_without_blocking_attribution() -> None:
    statuses = _statuses()
    statuses["campaign_evidence_ledger"]["status"] = "missing"

    payload = cle.build_campaign_level_evidence_payload(
        artifacts=_artifacts(),
        artifact_status=statuses,
    )

    assert payload["evidence_status"] == "attributed_with_artifact_gaps"
    assert "campaign_evidence_ledger" in payload["missing_or_malformed_artifacts"]
    assert payload["ledger_summary"]["ledger_present"] is False


def test_no_completed_campaign_returns_unavailable() -> None:
    artifacts = _artifacts()
    artifacts["campaign_registry"] = {"campaigns": {}}

    payload = cle.build_campaign_level_evidence_payload(
        artifacts=artifacts,
        artifact_status=_statuses(),
    )

    assert payload["evidence_status"] == "unavailable"
    assert payload["campaign"] is None
    assert payload["safety_invariants"]["runs_campaign"] is False


def test_cli_writes_json_and_markdown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    research_dir = tmp_path / "research"
    research_dir.mkdir()

    artifacts = _artifacts()

    for name, relative_path in cle.ARTIFACT_PATHS.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)

        if name == "campaign_evidence_ledger":
            path.write_text("", encoding="utf-8")
        else:
            path.write_text(
                json.dumps(artifacts[name]),
                encoding="utf-8",
            )

    rc = cle.main(
        [
            "--from-current-artifacts",
            "--report-json",
            str(tmp_path / "campaign-evidence.json"),
            "--report-md",
            str(tmp_path / "campaign-evidence.md"),
        ]
    )

    assert rc == 0

    written = json.loads((tmp_path / "campaign-evidence.json").read_text(encoding="utf-8"))
    assert written["campaign"]["campaign_id"] == CAMPAIGN_ID
    assert written["screening_evidence"]["owner_verified"] is True
    assert (tmp_path / "campaign-evidence.md").exists()
