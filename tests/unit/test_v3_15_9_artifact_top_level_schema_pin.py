"""v3.15.9 — pin the top-level schema of
``research/screening_evidence_latest.v1.json``.

Closed key set; new top-level keys MUST come with a
schema_version bump. Field-set pin (no byte-stable fixture)
following ``tests/regression/test_v312_sidecar_schema_stability.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.screening_evidence import (
    SCREENING_EVIDENCE_SCHEMA_VERSION,
    TOP_LEVEL_KEYS,
    build_screening_evidence_payload,
)


def _empty_payload() -> dict:
    return build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc123",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[],
        screening_records=[],
        screening_pass_kinds={},
        paper_blocked_index={},
    )


def test_schema_version_is_1_0() -> None:
    assert SCREENING_EVIDENCE_SCHEMA_VERSION == "1.0"
    payload = _empty_payload()
    assert payload["schema_version"] == "1.0"


def test_top_level_keys_are_closed_set() -> None:
    payload = _empty_payload()
    assert set(payload.keys()) == TOP_LEVEL_KEYS


def test_summary_keys_are_present() -> None:
    payload = _empty_payload()
    summary = payload["summary"]
    expected = {
        "total_candidates",
        "passed_screening",
        "rejected_screening",
        "needs_investigation",
        "promotion_grade_candidates",
        "exploratory_passes",
        "near_passes",
        "coverage_warnings",
        "identity_fallbacks",
        "dominant_failure_reasons",
    }
    assert set(summary.keys()) == expected


def test_artifact_fingerprint_is_hex_sha1() -> None:
    payload = _empty_payload()
    fp = payload["artifact_fingerprint"]
    assert isinstance(fp, str) and len(fp) == 40
    int(fp, 16)


def test_ownership_fields_present_and_redundant_in_v1() -> None:
    payload = _empty_payload()
    # In v3.15.9 we deliberately write both fields and they are
    # equal aliases. v3.15.10 ownership lookup tests this contract.
    assert payload["campaign_id"] == "cmp-1"
    assert payload["col_campaign_id"] == "cmp-1"
    assert payload["run_id"] == "run-1"


def test_generated_at_utc_is_iso_in_utc() -> None:
    payload = _empty_payload()
    assert payload["generated_at_utc"].endswith("+00:00")
