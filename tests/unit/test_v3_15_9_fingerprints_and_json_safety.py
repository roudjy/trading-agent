"""v3.15.9 — fingerprints are deterministic and use ``allow_nan=False``.

NaN/inf in metrics MUST be coerced to None upstream by
``to_json_safe_float``; a direct unsanitised NaN reaching the
canonical dump raises ``ValueError`` (proves the guard is in
effect).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pytest

from research.screening_evidence import (
    _canonical_dump,
    artifact_fingerprint,
    build_screening_evidence_payload,
    candidate_evidence_fingerprint,
    to_json_safe_float,
)


def _payload(records=None) -> dict:
    candidate = {
        "candidate_id": "c1",
        "strategy_id": "s1",
        "strategy_name": "s1",
        "asset": "BTC",
        "interval": "1h",
    }
    record = {
        "candidate_id": "c1",
        "final_status": "passed",
        "decision": "promoted_to_validation",
        "reason_code": None,
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {
            "expectancy": 0.001, "profit_factor": 1.5,
            "win_rate": 0.4, "max_drawdown": 0.2,
        },
        "sampling": {"grid_size": 4, "sampled_count": 4,
                     "coverage_pct": 1.0,
                     "sampling_policy": "full_coverage",
                     "sampled_parameter_digest": "abc",
                     "coverage_warning": None},
    }
    return build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc123",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[candidate],
        screening_records=records or [record],
        screening_pass_kinds={"s1": "exploratory"},
        paper_blocked_index={},
    )


def test_artifact_fingerprint_is_stable_across_calls() -> None:
    payloads = [_payload() for _ in range(5)]
    fingerprints = {p["artifact_fingerprint"] for p in payloads}
    assert len(fingerprints) == 1


def test_canonical_dump_rejects_unsanitised_nan() -> None:
    with pytest.raises(ValueError):
        _canonical_dump({"x": float("nan")})


def test_canonical_dump_rejects_unsanitised_inf() -> None:
    with pytest.raises(ValueError):
        _canonical_dump({"x": float("inf")})


def test_to_json_safe_float_coerces_nan_inf_to_none() -> None:
    assert to_json_safe_float(math.nan) is None
    assert to_json_safe_float(math.inf) is None
    assert to_json_safe_float(-math.inf) is None


def test_to_json_safe_float_passes_finite_values() -> None:
    for value in (0, 1, -1, 0.5, 1.5, "3.14"):
        assert to_json_safe_float(value) == float(value)


def test_to_json_safe_float_returns_none_for_unconvertible() -> None:
    assert to_json_safe_float(None) is None
    assert to_json_safe_float({"x": 1}) is None


def test_metrics_with_nan_are_sanitised_before_payload_writes() -> None:
    record = {
        "candidate_id": "c1",
        "final_status": "rejected",
        "reason_code": "expectancy_not_positive",
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {
            "expectancy": math.nan,
            "profit_factor": math.inf,
            "win_rate": 0.4,
            "max_drawdown": 0.2,
        },
        "sampling": {"grid_size": 1, "sampled_count": 1,
                     "coverage_pct": 1.0,
                     "sampling_policy": "full_coverage",
                     "sampled_parameter_digest": "abc",
                     "coverage_warning": None},
    }
    payload = _payload(records=[record])
    serialised = json.dumps(payload, allow_nan=False)
    assert "NaN" not in serialised
    assert "Infinity" not in serialised
    assert payload["candidates"][0]["metrics"]["expectancy"] is None
    assert payload["candidates"][0]["metrics"]["profit_factor"] is None


def test_evidence_fingerprint_changes_when_metrics_change() -> None:
    record_a = {
        "candidate_id": "c1",
        "final_status": "passed",
        "decision": "promoted_to_validation",
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {"expectancy": 0.001, "profit_factor": 1.5,
                               "win_rate": 0.4, "max_drawdown": 0.2},
        "sampling": {"grid_size": 1, "sampled_count": 1, "coverage_pct": 1.0,
                     "sampling_policy": "full_coverage",
                     "sampled_parameter_digest": "abc",
                     "coverage_warning": None},
    }
    record_b = dict(record_a)
    record_b["diagnostic_metrics"] = {"expectancy": 0.002,
                                       "profit_factor": 1.5,
                                       "win_rate": 0.4,
                                       "max_drawdown": 0.2}
    fp_a = _payload(records=[record_a])["candidates"][0]["evidence_fingerprint"]
    fp_b = _payload(records=[record_b])["candidates"][0]["evidence_fingerprint"]
    assert fp_a != fp_b


def test_artifact_fingerprint_excludes_itself() -> None:
    payload = _payload()
    snapshot = dict(payload)
    snapshot["artifact_fingerprint"] = "DIFFERENT"
    assert artifact_fingerprint(snapshot) == payload["artifact_fingerprint"]


def test_candidate_evidence_fingerprint_excludes_itself() -> None:
    payload = _payload()
    record = dict(payload["candidates"][0])
    saved = record.pop("evidence_fingerprint")
    new_fp = candidate_evidence_fingerprint(record)
    assert new_fp == saved
