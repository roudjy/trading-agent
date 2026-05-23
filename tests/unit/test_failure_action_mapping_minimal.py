"""Tests for ``reporting.failure_action_mapping_minimal``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import failure_action_mapping_minimal as fam


def _f(
    *,
    subject_id: str,
    failure_code: str = "insufficient_trades",
    severity: str = "medium",
    evidence_count: int = 3,
) -> dict[str, Any]:
    return {
        "subject_id": subject_id,
        "failure_code": failure_code,
        "severity": severity,
        "evidence_count": evidence_count,
    }


def test_closed_taxonomies_are_pinned() -> None:
    assert fam.FAILURE_CODES == (
        "insufficient_trades",
        "high_drawdown",
        "weak_stability",
        "low_win_rate",
        "negative_expectancy",
        "technical_failure",
        "no_oos_samples",
        "cost_gate_fail",
        "entropy_regime_incompatible",
        "tail_fragility_high",
        "unknown_failure",
    )
    assert fam.NEXT_ACTIONS == (
        "increase_timeframe",
        "apply_volatility_filter",
        "segment_by_regime",
        "preserve_negative_result",
        "collect_more_evidence",
        "review_data_pipeline",
        "review_cost_assumptions",
        "hold_no_action",
    )
    assert fam.SCREENING_CLASSIFICATION_TO_FAILURE_CODE["data_coverage_gap"] == (
        "technical_failure"
    )
    assert fam.SCREENING_CLASSIFICATION_TO_FAILURE_CODE["unknown_screening_failure"] == (
        "unknown_failure"
    )


def test_schema_keys_are_pinned() -> None:
    assert fam.INPUT_FAILURE_KEYS == (
        "subject_id",
        "failure_code",
        "severity",
        "evidence_count",
    )
    assert fam.OUTPUT_ITEM_KEYS == (
        "subject_id",
        "failure_code",
        "severity",
        "evidence_count",
        "recommended_action",
        "rank",
        "reason_record",
    )
    assert fam.REASON_RECORD_KEYS == (
        "record_id",
        "record_kind",
        "schema_version",
        "subject_id",
        "failure_code",
        "recommended_action",
        "reason_codes",
        "reason_text",
        "inputs_digest",
    )


def test_failures_must_be_list_or_tuple() -> None:
    with pytest.raises(ValueError, match="list/tuple"):
        fam.validate_failures({"subject_id": "x"})  # type: ignore[arg-type]


def test_too_many_failures_rejected() -> None:
    failures = [_f(subject_id=f"s_{i:04d}") for i in range(fam.MAX_FAILURES + 1)]
    with pytest.raises(ValueError, match="too many"):
        fam.validate_failures(failures)


def test_missing_field_rejected() -> None:
    bad = _f(subject_id="x")
    del bad["failure_code"]
    with pytest.raises(ValueError, match="missing fields"):
        fam.validate_failures([bad])


def test_unknown_failure_code_rejected() -> None:
    with pytest.raises(ValueError, match="closed taxonomy"):
        fam.validate_failures([_f(subject_id="x", failure_code="not_canonical")])


def test_unknown_severity_rejected() -> None:
    with pytest.raises(ValueError, match="severity"):
        fam.validate_failures([_f(subject_id="x", severity="critical")])


def test_duplicate_subject_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        fam.validate_failures([_f(subject_id="x"), _f(subject_id="x")])


@pytest.mark.parametrize(
    ("failure_code", "expected_action"),
    [
        ("insufficient_trades", "increase_timeframe"),
        ("high_drawdown", "apply_volatility_filter"),
        ("weak_stability", "segment_by_regime"),
        ("low_win_rate", "preserve_negative_result"),
        ("negative_expectancy", "preserve_negative_result"),
        ("technical_failure", "review_data_pipeline"),
        ("no_oos_samples", "collect_more_evidence"),
        ("cost_gate_fail", "review_cost_assumptions"),
        ("entropy_regime_incompatible", "segment_by_regime"),
        ("tail_fragility_high", "apply_volatility_filter"),
        ("unknown_failure", "hold_no_action"),
    ],
)
def test_failure_codes_map_to_bounded_actions(failure_code: str, expected_action: str) -> None:
    snap = fam.collect_snapshot(
        [_f(subject_id="s1", failure_code=failure_code)],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert snap["items"][0]["recommended_action"] == expected_action
    assert expected_action in fam.NEXT_ACTIONS


def test_technical_failure_reason_is_not_research_action() -> None:
    snap = fam.collect_snapshot(
        [_f(subject_id="s1", failure_code="technical_failure")],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    record = snap["items"][0]["reason_record"]
    assert snap["items"][0]["recommended_action"] == "review_data_pipeline"
    assert "technical_not_research" in record["reason_codes"]


def test_low_evidence_adds_insufficient_reason() -> None:
    snap = fam.collect_snapshot(
        [_f(subject_id="s1", evidence_count=1)],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert "evidence_insufficient" in snap["items"][0]["reason_record"]["reason_codes"]


def test_negative_result_preservation_is_explicit() -> None:
    snap = fam.collect_snapshot(
        [_f(subject_id="s1", failure_code="negative_expectancy")],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    record = snap["items"][0]["reason_record"]
    assert snap["items"][0]["recommended_action"] == "preserve_negative_result"
    assert "negative_result_preserved" in record["reason_codes"]


def test_ranking_orders_by_severity_then_failure_then_subject() -> None:
    snap = fam.collect_snapshot(
        [
            _f(subject_id="z", failure_code="weak_stability", severity="low"),
            _f(subject_id="b", failure_code="high_drawdown", severity="high"),
            _f(subject_id="a", failure_code="high_drawdown", severity="high"),
            _f(subject_id="m", failure_code="cost_gate_fail", severity="medium"),
        ],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert [item["subject_id"] for item in snap["items"]] == [
        "a",
        "b",
        "m",
        "z",
    ]
    assert [item["rank"] for item in snap["items"]] == [0, 1, 2, 3]


def test_reason_record_ids_are_deterministic() -> None:
    inputs = [_f(subject_id="s1", failure_code="high_drawdown")]
    a = fam.collect_snapshot(inputs, frozen_utc="2026-05-21T00:00:00Z")
    b = fam.collect_snapshot(inputs, frozen_utc="2026-05-21T00:00:00Z")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert (
        a["items"][0]["reason_record"]["record_id"] == b["items"][0]["reason_record"]["record_id"]
    )


def test_record_ids_change_when_inputs_change() -> None:
    a = fam.collect_snapshot(
        [_f(subject_id="s1", evidence_count=3)],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    b = fam.collect_snapshot(
        [_f(subject_id="s1", evidence_count=4)],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert (
        a["items"][0]["reason_record"]["record_id"] != b["items"][0]["reason_record"]["record_id"]
    )


def test_empty_snapshot_is_safe_and_not_actionable() -> None:
    snap = fam.collect_snapshot([], frozen_utc="2026-05-21T00:00:00Z")
    assert snap["counts"]["total"] == 0
    assert snap["safe_to_execute"] is False
    assert snap["mode"] == "dry-run"
    assert snap["final_recommendation"] == "nothing_actionable"


def test_screening_attribution_adapter_maps_non_strategy_classes_only() -> None:
    payload = {
        "summary": {"primary_classification": "data_coverage_gap"},
        "classifications": [
            {
                "classification": "data_coverage_gap",
                "status": "observed",
                "count": 2,
            },
            {
                "classification": "strict_gate_rejection",
                "status": "observed",
                "count": 3,
            },
            {
                "classification": "unknown_screening_failure",
                "status": "observed",
                "count": 1,
            },
        ],
    }

    failures = fam.screening_attribution_failures(payload)

    assert failures == [
        {
            "subject_id": "screening:data_coverage_gap",
            "failure_code": "technical_failure",
            "severity": "medium",
            "evidence_count": 2,
        },
        {
            "subject_id": "screening:unknown_screening_failure",
            "failure_code": "unknown_failure",
            "severity": "high",
            "evidence_count": 1,
        },
    ]


def test_collect_from_screening_attribution_preserves_read_only_action_snapshot() -> None:
    payload = {
        "summary": {"primary_classification": "missing_metric_field"},
        "classifications": [
            {
                "classification": "missing_metric_field",
                "status": "observed",
                "count": 4,
            }
        ],
    }

    snap = fam.collect_from_screening_attribution(
        payload,
        frozen_utc="2026-05-22T00:00:00Z",
    )

    assert snap["source_report_kind"] == "screening_failure_attribution"
    assert snap["source_primary_classification"] == "missing_metric_field"
    assert snap["items"][0]["recommended_action"] == "review_data_pipeline"
    assert snap["safe_to_execute"] is False


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "failure_action_mapping_minimal"
    snap = fam.collect_snapshot(
        [_f(subject_id="s1")],
        frozen_utc="2026-05-21T00:00:00Z",
    )
    out = fam.write_outputs(snap, artifact_dir=base)
    assert (base / "latest.json").is_file()
    assert "failure_action_mapping_minimal" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        fam._validate_write_target(tmp_path / "evil" / "latest.json")


def test_cli_status_returns_not_available(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fam,
        "ARTIFACT_LATEST",
        tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json",
    )
    rc = fam.main(["--status"])
    parsed = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert parsed["final_recommendation"] == "not_available"


def test_cli_no_write_does_not_write(capsys: pytest.CaptureFixture[str]) -> None:
    rc = fam.main(["--no-write", "--frozen-utc", "2026-05-21T00:00:00Z"])
    parsed = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert parsed["counts"]["total"] == 0
    assert parsed["safe_to_execute"] is False


def test_module_is_stdlib_only_in_source() -> None:
    src = Path(fam.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
    )
    for needle in forbidden:
        assert needle not in src


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(fam.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "agent.execution",
        "agent.risk",
        "automation.live",
        "automation.broker",
        "broker.",
        "execution.live",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert needle not in src
