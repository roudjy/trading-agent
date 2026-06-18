from __future__ import annotations

import json
from pathlib import Path

from research import qre_approved_bounded_evidence_diagnostics as diagnostics


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _approval() -> dict[str, object]:
    return {
        "approval_id": "approval-001",
        "scope": {
            "symbols": ["AAA", "BBB"],
            "preset_id": "trend_pullback_continuation_daily_v1",
            "timeframe": "daily_v1",
        },
        "external_fetch_allowed": False,
    }


def _approved_run() -> dict[str, object]:
    return {
        "source_payload": {
            "source_ref": "logs/qre_controlled_validation_adapter_results/source_artifacts/approval-001.v1.json",
            "oos_records": [
                {
                    "oos_window": {"start": "2026-01-01", "end": "2026-01-31"},
                    "oos_metric_fields": {"oos_trade_count": 0, "oos_return_pct": 0.0},
                    "cost_slippage_assumption_refs": ["cost-001"],
                }
            ],
        }
    }


def _verifier() -> dict[str, object]:
    return {
        "report_kind": "qre_bounded_generation_artifact_acceptance_verifier",
        "rows": [
            {
                "relative_path": "logs/qre_controlled_validation_adapter_results/latest.json",
                "accepted_for_campaign_lineage": True,
                "accepted_for_oos_evidence": False,
                "accepted_lineage_records": [
                    {
                        "candidate_id": "cand-001",
                        "preset_id": "trend_pullback_continuation_daily_v1",
                        "timeframe": "daily_v1",
                        "request_ref": "req-001",
                    }
                ],
                "accepted_oos_records": [],
                "oos_rejection_reasons": ["non_positive_oos_trade_count"],
            }
        ],
    }


def _closure() -> dict[str, object]:
    return {
        "report_kind": "qre_evidence_complete_basket_closure",
        "rows": [
            {
                "candidate_id": "cand-001",
                "symbol": "AAA",
                "preset_id": "trend_pullback_continuation_daily_v1",
                "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"],
                "failure_action": {"timeframes": ["1d"]},
            }
        ],
    }


def test_detects_non_positive_oos_trade_count(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    report = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert "oos_rejected_non_positive_trade_count" in report["diagnostic_statuses"]
    assert "approved_source_has_no_oos_trades" in report["diagnostic_statuses"]
    assert report["oos_trade_count"] == [0]


def test_preserves_exact_oos_rejection_reason(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    report = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert report["exact_oos_rejection_reasons"] == ["non_positive_oos_trade_count"]


def test_detects_accepted_lineage_but_closure_scope_mismatch(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    report = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert report["lineage_scope_match"] is False
    assert "timeframe_alias_mismatch_between_verifier_and_closure" in report["unmatched_lineage_reasons"]
    assert "lineage_accepted_but_scope_mismatch" in report["diagnostic_statuses"]


def test_detects_accepted_lineage_but_blocker_not_cleared(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    report = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert "lineage_accepted_but_closure_not_cleared" in report["diagnostic_statuses"]
    assert report["closure_blockers_before_after"][0]["campaign_lineage_missing_present"] is True


def test_does_not_clear_blockers_or_create_evidence(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    report = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert report["accepted_oos_count"] == 0
    assert report["blocker_clearance_eligibility"] is False


def test_output_is_deterministic(tmp_path: Path) -> None:
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVAL_PATH, _approval())
    _write_json(tmp_path / diagnostics.DEFAULT_APPROVED_RUN_PATH, _approved_run())
    _write_json(tmp_path / diagnostics.DEFAULT_VERIFIER_PATH, _verifier())
    _write_json(tmp_path / diagnostics.DEFAULT_CLOSURE_PATH, _closure())

    first = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)
    second = diagnostics.build_approved_bounded_evidence_diagnostics(repo_root=tmp_path)

    assert first == second
    assert first["hash"] == diagnostics.compute_diagnostics_hash(first)


def test_core_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_approved_bounded_evidence_diagnostics.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
