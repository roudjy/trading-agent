"""Tests for research.screening_failure_attribution sidecars."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research import screening_failure_attribution as sfa


def _statuses(screening_status: str = "present") -> dict[str, dict[str, str]]:
    return {
        name: {
            "path": path.as_posix(),
            "status": screening_status if name == "screening_evidence" else "present",
        }
        for name, path in sfa.ARTIFACT_PATHS.items()
    }


def _base_artifacts(**overrides) -> dict:
    artifacts = {
        "screening_evidence": {},
        "run_filter_summary": {},
        "run_screening_candidates": {},
        "empty_run_diagnostics": {},
        "run_campaign": {},
        "controlled_eval": {},
        "campaign_registry": {"campaigns": {}},
        "campaign_evidence_ledger": [],
        "research_state": {},
        "policy_filter_diagnostics": {},
    }
    artifacts.update(overrides)
    return artifacts


def _payload(artifacts: dict, statuses: dict[str, dict[str, str]] | None = None) -> dict:
    return sfa.build_screening_failure_attribution_payload(
        artifacts=artifacts,
        artifact_status=statuses or _statuses(),
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def _row(payload: dict, classification: str) -> dict:
    return next(
        row for row in payload["classifications"] if row["classification"] == classification
    )


def test_screening_evidence_failure_reasons_are_classified() -> None:
    payload = _payload(
        _base_artifacts(
            screening_evidence={
                "summary": {"dominant_failure_reasons": ["insufficient_trades"]},
                "candidates": [
                    {
                        "candidate_id": "c1",
                        "strategy_name": "s",
                        "asset": "BTC-USD",
                        "interval": "4h",
                        "stage_result": "screening_reject",
                        "failure_reasons": ["insufficient_trades"],
                    },
                    {
                        "candidate_id": "c2",
                        "stage_result": "screening_reject",
                        "failure_reasons": ["no_oos_samples"],
                    },
                ],
            }
        )
    )

    assert _row(payload, "insufficient_trades")["count"] == 2
    assert _row(payload, "no_oos_returns")["count"] == 1
    assert payload["summary"]["primary_classification"] == "insufficient_trades"
    assert payload["summary"]["attributed"] is True


def test_timeout_and_strict_gate_rejections_are_classified_from_filter_summary() -> None:
    payload = _payload(
        _base_artifacts(
            run_filter_summary={
                "screening_rejection_reasons": {
                    "candidate_budget_exceeded": 1,
                    "screening_criteria_not_met": 2,
                }
            }
        )
    )

    assert _row(payload, "timeout")["count"] == 1
    assert _row(payload, "strict_gate_rejection")["count"] == 2
    assert payload["summary"]["primary_classification"] == "strict_gate_rejection"


def test_data_coverage_and_no_oos_are_classified_from_empty_run_diagnostics() -> None:
    payload = _payload(
        _base_artifacts(
            empty_run_diagnostics={
                "summary": {
                    "primary_drop_reasons": ["empty_dataset"],
                    "evaluations_count": 3,
                    "evaluations_with_oos_daily_returns": 0,
                },
                "pairs": [
                    {
                        "asset": "BTC-USD",
                        "interval": "1h",
                        "status": "dropped",
                        "drop_reason": "data_unavailable",
                    }
                ],
            }
        )
    )

    assert _row(payload, "data_coverage_gap")["count"] == 2
    assert _row(payload, "no_oos_returns")["count"] == 1


def test_parameter_instability_and_cost_sensitivity_are_supported() -> None:
    payload = _payload(
        _base_artifacts(
            campaign_registry={
                "campaigns": {
                    "col-1": {
                        "campaign_id": "col-1",
                        "failure_reasons": [
                            "unstable_parameter_neighborhood",
                            "cost_sensitivity_flag",
                        ],
                    }
                }
            }
        )
    )

    assert _row(payload, "parameter_instability")["count"] == 1
    assert _row(payload, "cost_sensitivity")["count"] == 1


def test_missing_diagnostics_is_reported_when_state_needs_drop_reasons() -> None:
    payload = _payload(
        _base_artifacts(
            screening_evidence=None,
            research_state={
                "failure_attribution": {
                    "state": "screening_evaluability_unattributed",
                    "missing": ["screening_drop_reasons"],
                }
            },
        ),
        _statuses(screening_status="missing"),
    )

    assert _row(payload, "missing_diagnostics")["count"] >= 1
    assert payload["summary"]["primary_classification"] == "missing_diagnostics"
    assert payload["summary"]["attributed"] is False


def test_missing_all_screening_artifacts_is_handled_gracefully_with_cli(
    tmp_path: Path,
) -> None:
    statuses = {
        name: {"path": path.as_posix(), "status": "missing"}
        for name, path in sfa.ARTIFACT_PATHS.items()
    }
    payload = _payload(_base_artifacts(screening_evidence=None), statuses)

    assert payload["summary"]["primary_classification"] == "missing_diagnostics"
    assert _row(payload, "missing_diagnostics")["status"] == "observed"

    rc = sfa.main(
        [
            "--from-current-artifacts",
            "--report-json",
            str(tmp_path / "screening.json"),
            "--report-md",
            str(tmp_path / "screening.md"),
        ]
    )

    assert rc == 0
    written = json.loads((tmp_path / "screening.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == "1.0"
    assert (tmp_path / "screening.md").exists()
