from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_funnel_threshold_audit as report


def _criterion(rows: list[dict[str, object]], criterion_id: str) -> dict[str, object]:
    for row in rows:
        if row["criterion_id"] == criterion_id:
            return row
    raise AssertionError(f"missing criterion row: {criterion_id}")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fixture_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path
    research = repo_root / "research"
    history_dir = research / "history" / "20260605T102349101321Z"

    _write_json(
        research / "run_filter_summary_latest.v1.json",
        {
            "summary": {
                "raw_candidate_count": 2,
                "fit_allowed_count": 2,
                "fit_discouraged_count": 0,
                "fit_blocked_count": 0,
                "deduplicated_candidate_count": 2,
                "duplicates_removed": 0,
                "eligible_candidate_count": 0,
                "eligibility_rejected_count": 2,
                "eligibility_rejection_reasons": {"data_unavailable": 2},
            }
        },
    )
    _write_json(
        research / "run_campaign_latest.v1.json",
        {
            "summary": {
                "validated_candidate_count": 2,
                "validation_error_count": 0,
            }
        },
    )
    _write_json(
        research / "campaign_level_evidence_latest.v1.json",
        {
            "interpretation": {"primary_limitation": "insufficient_trades"},
            "screening_evidence": {
                "counts": {
                    "total_candidates": 3,
                    "passed_screening": 2,
                    "rejected_screening": 1,
                }
            },
        },
    )
    _write_json(
        history_dir / "run_candidates.v1.json",
        {
            "candidates": [
                {"validation": {"evidence_status": "no_oos_trades"}},
                {"validation": {"evidence_status": "sufficient_oos_evidence"}},
            ]
        },
    )
    _write_json(
        research / "screening_evidence_latest.v1.json",
        {
            "summary": {
                "passed_screening": 2,
                "rejected_screening": 1,
                "sufficient_oos_evidence_candidates": 1,
            },
            "candidates": [
                {
                    "candidate_id": "cid-pass",
                    "hypothesis_id": "trend_pullback_v1",
                    "strategy_name": "trend_pullback_v1",
                    "preset_name": "trend_pullback_equities_4h",
                    "asset": "AAPL",
                    "interval": "4h",
                    "stage_result": "screening_pass",
                    "failure_reasons": [],
                    "promotion_guard": {
                        "blocked_by": [
                            "criteria_consistentie_failed",
                            "criteria_trades_per_maand_failed",
                        ]
                    },
                    "metrics": {
                        "expectancy": 0.02,
                        "profit_factor": 1.6,
                        "max_drawdown": 0.12,
                        "totaal_trades": 18.0,
                        "trades_per_maand": 1.4,
                        "win_rate": 0.55,
                    },
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 14,
                        "min_oos_trades": 10,
                    },
                },
                {
                    "candidate_id": "cid-near",
                    "hypothesis_id": "trend_pullback_v1",
                    "strategy_name": "trend_pullback_v1",
                    "preset_name": "trend_pullback_equities_4h",
                    "asset": "NVDA",
                    "interval": "4h",
                    "stage_result": "screening_pass",
                    "failure_reasons": [],
                    "promotion_guard": {
                        "blocked_by": [
                            "criteria_deflated_sharpe_failed",
                            "criteria_trades_per_maand_failed",
                        ]
                    },
                    "metrics": {
                        "expectancy": 0.004,
                        "profit_factor": 1.2,
                        "max_drawdown": 0.08,
                        "totaal_trades": 11.0,
                        "trades_per_maand": 0.8,
                        "win_rate": 0.6,
                    },
                    "validation_evidence": {
                        "status": "no_oos_trades",
                        "oos_trade_count": 0,
                        "min_oos_trades": 10,
                    },
                },
                {
                    "candidate_id": "cid-fail",
                    "hypothesis_id": "trend_pullback_v1",
                    "strategy_name": "trend_pullback_v1",
                    "preset_name": "trend_pullback_equities_4h",
                    "asset": "AMD",
                    "interval": "4h",
                    "stage_result": "screening_reject",
                    "failure_reasons": ["insufficient_trades"],
                    "promotion_guard": {
                        "blocked_by": [
                            "criteria_expectancy_above_zero_failed",
                            "criteria_profit_factor_at_or_above_floor_failed",
                            "criteria_sufficient_trades_failed",
                        ]
                    },
                    "metrics": {
                        "expectancy": 0.0,
                        "profit_factor": 0.8,
                        "max_drawdown": 0.1,
                        "totaal_trades": 4.0,
                        "trades_per_maand": 0.2,
                        "win_rate": 0.25,
                    },
                    "validation_evidence": {
                        "status": "",
                        "oos_trade_count": None,
                        "min_oos_trades": None,
                    },
                },
            ],
        },
    )
    _write_json(
        research / "run_screening_candidates_latest.v1.json",
        {
            "candidates": [
                {
                    "sample_diagnostics_summary": {"best_sample_index": 0},
                    "sample_diagnostics": [
                        {
                            "trend_break_bar_path_threshold_comparison_summary": {
                                "matched_trade_count": 3,
                                "rules": {
                                    "mae_gt_2pct_mfe_lt_025pct": {
                                        "triggered_trade_count": 1,
                                        "triggered_trend_break_trades": 1,
                                        "triggered_pullback_resolved_trades": 0,
                                        "triggered_other_trades": 0,
                                        "avoided_loss": 0.05,
                                        "sacrificed_profit": 0.01,
                                        "other_pnl_delta": 0.0,
                                        "net_pnl_delta": 0.04,
                                    }
                                },
                            }
                        }
                    ],
                }
            ]
        },
    )
    return repo_root


def test_collect_snapshot_surfaces_funnel_counts_and_recommendations(tmp_path: Path) -> None:
    snapshot = report.collect_snapshot(
        repo_root=_fixture_repo(tmp_path),
        frozen_utc="2026-06-26T00:20:00Z",
    )

    assert snapshot["report_kind"] == "qre_funnel_threshold_audit"
    assert snapshot["funnel_counts"]["raw_candidate_count"] == 2
    assert snapshot["funnel_counts"]["screening_pass_count"] == 2
    assert snapshot["funnel_counts"]["screening_reject_count"] == 1
    assert snapshot["funnel_counts"]["oos_accepted_count"] == 1
    assert snapshot["rejection_reason_counts"]["eligibility_rejection_reasons"] == {
        "data_unavailable": 2
    }
    assert snapshot["summary"]["all_criteria_have_exactly_one_recommendation"] is True

    sufficient_trades = _criterion(snapshot["criterion_rows"], "sufficient_trades")
    assert sufficient_trades["threshold_value"] == 10.0
    assert sufficient_trades["fail_count"] == 1
    assert sufficient_trades["recommendation"] == "insufficient_evidence_to_change"

    drawdown = _criterion(snapshot["criterion_rows"], "drawdown_within_limit")
    assert drawdown["threshold_value"] == 0.45
    assert drawdown["recommendation"] == "keep"


def test_collect_snapshot_is_deterministic_with_frozen_timestamp(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path)
    a = report.collect_snapshot(
        repo_root=repo_root,
        frozen_utc="2026-06-26T00:20:00Z",
    )
    b = report.collect_snapshot(
        repo_root=repo_root,
        frozen_utc="2026-06-26T00:20:00Z",
    )

    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert a["snapshot_identity"]["snapshot_id"] == b["snapshot_identity"]["snapshot_id"]


def test_write_outputs_writes_latest_history_and_doc(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path / "repo")
    snapshot = report.collect_snapshot(
        repo_root=repo_root,
        frozen_utc="2026-06-26T00:20:00Z",
    )

    output_dir = tmp_path / "logs" / "qre_funnel_threshold_audit"
    doc_path = tmp_path / "docs" / "governance" / "qre_funnel_threshold_audit.md"
    paths = report.write_outputs(
        snapshot,
        output_dir=output_dir,
        doc_path=doc_path,
        repo_root=tmp_path,
    )

    assert paths["latest"].endswith("logs/qre_funnel_threshold_audit/latest.json")
    assert paths["history"].endswith("logs/qre_funnel_threshold_audit/history.jsonl")
    assert paths["doc"].endswith("docs/governance/qre_funnel_threshold_audit.md")
    assert (output_dir / "latest.json").is_file()
    assert (output_dir / "history.jsonl").is_file()
    assert "# QRE Funnel Census and Threshold-Distance Audit" in doc_path.read_text(
        encoding="utf-8"
    )


def test_write_outputs_refuses_writes_outside_allowlist(tmp_path: Path) -> None:
    repo_root = _fixture_repo(tmp_path / "repo")
    snapshot = report.collect_snapshot(
        repo_root=repo_root,
        frozen_utc="2026-06-26T00:20:00Z",
    )

    try:
        report.write_outputs(
            snapshot,
            output_dir=tmp_path / "elsewhere",
            doc_path=tmp_path / "docs" / "governance" / "qre_funnel_threshold_audit.md",
            repo_root=tmp_path,
        )
    except ValueError as exc:
        assert "refusing write outside allowlist" in str(exc)
    else:
        raise AssertionError("expected allowlist failure")
