from pathlib import Path

import pytest

from research.qre_sampling_calibration_report import (
    build_sampling_calibration_report,
    render_operator_summary,
    write_outputs,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_evidence_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [
                {
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "quality_status": "ready",
                    "manifest_status": "ready",
                    "identity_confidence": "high",
                    "source": "yfinance",
                    "blocking_reasons": [],
                    "operator_explanation": "ready source quality evidence",
                    "path": "data/cache/market/aapl.parquet",
                },
                {
                    "instrument": "ASML",
                    "timeframe": "1d",
                    "quality_status": "blocked",
                    "manifest_status": "blocked",
                    "identity_confidence": "low",
                    "source": "yfinance",
                    "blocking_reasons": ["identity_ambiguous"],
                    "operator_explanation": "blocked source quality evidence",
                    "path": "data/cache/market/asml.parquet",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {
            "coverage": [
                {
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "ready": True,
                    "row_count": 5,
                    "file_count": 1,
                    "source": "yfinance",
                    "cache_kind": "market",
                    "content_hash": "sha256:aapl",
                    "status_counts": {"ready": 1},
                },
                {
                    "instrument": "ASML",
                    "timeframe": "1d",
                    "ready": False,
                    "row_count": 0,
                    "file_count": 0,
                    "source": "yfinance",
                    "cache_kind": "market",
                    "content_hash": "sha256:asml",
                    "status_counts": {"blocked": 1},
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_null_model_baseline" / "latest.json",
        {
            "sample_comparisons": [
                {
                    "candidate_id": "sample:below",
                    "baseline_type": "median_candidate",
                    "candidate_metric": -0.01,
                    "baseline_metric": 0.0,
                    "delta_vs_baseline": -0.01,
                    "comparison_state": "candidate_below_baseline",
                    "explanation": "Deterministic metric-vs-baseline comparison; context only, not authority.",
                },
                {
                    "candidate_id": "sample:above",
                    "baseline_type": "median_candidate",
                    "candidate_metric": 0.02,
                    "baseline_metric": 0.0,
                    "delta_vs_baseline": 0.02,
                    "comparison_state": "candidate_above_baseline",
                    "explanation": "Deterministic metric-vs-baseline comparison; context only, not authority.",
                },
            ],
            "suite_comparisons": [
                {
                    "candidate_id": "sample:below",
                    "family": "random_walk",
                    "candidate_metric": -0.01,
                    "baseline_metric": -0.005,
                    "delta_vs_baseline": -0.005,
                    "comparison_state": "candidate_below_baseline",
                    "explanation": "Deterministic metric-vs-baseline comparison; context only, not authority.",
                },
                {
                    "candidate_id": "sample:above",
                    "family": "random_walk",
                    "candidate_metric": 0.02,
                    "baseline_metric": -0.03,
                    "delta_vs_baseline": 0.05,
                    "comparison_state": "candidate_above_baseline",
                    "explanation": "Deterministic metric-vs-baseline comparison; context only, not authority.",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_state_transition_diagnostics" / "latest.json",
        {
            "diagnostics": [
                {
                    "subject_id": "sample:progress",
                    "prior_state": "candidate_discovered",
                    "new_state": "screened",
                    "transition_reason": "criteria_passed",
                    "transition_state": "positive_progress_transition",
                    "artifact_ref": "logs/qre_state_transition_diagnostics/latest.json",
                },
                {
                    "subject_id": "sample:blocked",
                    "prior_state": "screened",
                    "new_state": "blocked",
                    "transition_reason": "data_readiness_blocked",
                    "blocker_class": "missing_required_field",
                    "transition_state": "terminal_negative_transition",
                    "artifact_ref": "logs/qre_state_transition_diagnostics/latest.json",
                },
            ],
            "sequence_diagnostics": [
                {
                    "subject_id": "sample:progress",
                    "sequence_state": "ready",
                    "dwell_state": "validated",
                    "dwell_steps": 1,
                    "regime_duration_steps": 4,
                    "sparse_data": False,
                    "explanation": "sequence ready",
                },
                {
                    "subject_id": "sample:blocked",
                    "sequence_state": "blocked",
                    "dwell_state": "fail_closed",
                    "dwell_steps": 1,
                    "regime_duration_steps": 3,
                    "sparse_data": False,
                    "explanation": "sequence blocked",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_tail_entropy_hardening" / "latest.json",
        {
            "diagnostics": [
                {
                    "subject_id": "sample:balanced",
                    "risk_state": "tail_entropy_clear",
                    "density_state": "density_ready",
                    "evidence_ref_count": 2,
                    "null_challenge_count": 2,
                    "explanation": "tail entropy clear",
                },
                {
                    "subject_id": "sample:insufficient",
                    "risk_state": "insufficient_return_data",
                    "density_state": "missing_density",
                    "evidence_ref_count": 0,
                    "null_challenge_count": 1,
                    "explanation": "insufficient evidence",
                },
            ]
        },
    )


def test_sampling_calibration_report_is_ready_and_context_only(tmp_path: Path):
    _seed_evidence_artifacts(tmp_path)

    report = build_sampling_calibration_report(repo_root=tmp_path)

    assert report["schema_version"] == "1.0"
    assert report["report_kind"] == "qre_sampling_calibration_report"
    assert report["summary"]["sampling_calibration_ready"] is True
    assert report["summary"]["final_recommendation"] == "sampling_calibration_evidence_ready"

    safety = report["safety_invariants"]
    assert safety["read_only"] is True
    assert safety["uses_network"] is False
    assert safety["uses_external_data"] is False
    assert safety["mutates_candidates"] is False
    assert safety["mutates_campaigns"] is False
    assert safety["mutates_strategies"] is False
    assert safety["mutates_presets"] is False
    assert safety["mutates_frozen_contracts"] is False
    assert safety["promotion_forbidden"] is True
    assert safety["campaign_mutation_forbidden"] is True
    assert safety["paper_shadow_live_forbidden"] is True
    assert safety["broker_risk_execution_forbidden"] is True
    assert safety["evidence_backed_context_only"] is True


def test_sampling_calibration_report_uses_evidence_artifacts(tmp_path: Path):
    _seed_evidence_artifacts(tmp_path)

    report = build_sampling_calibration_report(repo_root=tmp_path)

    assert report["summary"]["input_row_count"] == 14
    assert report["summary"]["calibration_count"] == 14
    assert report["summary"]["null_model_backed_count"] >= 1
    assert report["summary"]["evidence_support_state_counts"]["evidence_backed"] >= 1
    assert report["summary"]["evidence_category_counts"]["null"] >= 1
    assert report["summary"]["evidence_category_counts"]["regime"] >= 1
    assert report["summary"]["evidence_category_counts"]["source"] >= 1
    assert report["summary"]["evidence_category_counts"]["data"] >= 1

    decision_counts = report["summary"]["sampling_decision_counts"]
    assert decision_counts["prefer_sampling"] >= 1
    assert "allow_sampling" in decision_counts or "deprioritize_sampling" in decision_counts


def test_sampling_calibration_report_accepts_custom_rows():
    report = build_sampling_calibration_report(
        rows=[
            {
                "subject_id": "candidate:custom",
                "asset_class": "fundamental_equity",
                "research_scope": "target_equity_research",
                "readiness_state": "ready",
                "comparison_state": "candidate_above_baseline",
                "title": "Europe factor source_manifest null_model regime",
                "evidence_presence": {
                    "source_quality_ready": True,
                    "null_model_ready": True,
                    "regime_ready": True,
                },
                "evidence_refs": ["logs/custom/latest.json"],
            }
        ]
    )

    assert report["summary"]["input_row_count"] == 1
    assert report["calibrations"][0]["sampling_decision"] in {"prefer_sampling", "allow_sampling"}
    assert report["calibrations"][0]["evidence_support_state"] in {"partial_evidence", "evidence_backed"}


def test_sampling_calibration_operator_summary_renders(tmp_path: Path):
    _seed_evidence_artifacts(tmp_path)

    report = build_sampling_calibration_report(repo_root=tmp_path)
    text = render_operator_summary(report)

    assert "# QRE Sampling Calibration" in text
    assert "null_model_backed_count" in text
    assert "sampling_calibration_evidence_ready" in text


def test_sampling_calibration_write_outputs_stays_in_allowlist(tmp_path: Path):
    _seed_evidence_artifacts(tmp_path)

    report = build_sampling_calibration_report(repo_root=tmp_path)
    paths = write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_sampling_calibration/latest.json"
    assert paths["operator_summary"] == "logs/qre_sampling_calibration/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_sampling_calibration_write_rejects_non_allowlisted_path(monkeypatch, tmp_path: Path):
    from research import qre_sampling_calibration_report as report_module

    monkeypatch.setattr(report_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    _seed_evidence_artifacts(tmp_path)
    report = build_sampling_calibration_report(repo_root=tmp_path)

    with pytest.raises(ValueError):
        write_outputs(report, repo_root=tmp_path)
