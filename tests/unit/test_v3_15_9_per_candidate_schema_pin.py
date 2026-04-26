"""v3.15.9 — pin the per-candidate evidence record schema.

Closed key set per record. Includes ``identity_fallback_used``
(MF-19) and ``evidence_fingerprint`` (used by v3.15.10 dedupe).
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.screening_evidence import (
    PER_CANDIDATE_KEYS,
    build_screening_evidence_payload,
)


def _payload_with_one_candidate() -> dict:
    candidate = {
        "candidate_id": "c1",
        "strategy_id": "s1",
        "strategy_name": "s1",
        "asset": "BTC",
        "interval": "1h",
        "hypothesis_id": "h1",
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
        "sampling": {
            "grid_size": 4, "sampled_count": 4, "coverage_pct": 1.0,
            "sampling_policy": "full_coverage",
            "sampled_parameter_digest": "abc",
            "coverage_warning": None,
        },
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
        screening_records=[record],
        screening_pass_kinds={"s1": "exploratory"},
        paper_blocked_index={},
    )


def test_per_candidate_keys_are_closed_set() -> None:
    payload = _payload_with_one_candidate()
    record = payload["candidates"][0]
    assert set(record.keys()) == PER_CANDIDATE_KEYS


def test_metrics_block_keys_are_complete() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    expected = {
        "win_rate", "expectancy", "profit_factor", "max_drawdown",
        "totaal_trades", "trades_per_maand", "deflated_sharpe",
        "consistentie",
    }
    assert set(record["metrics"].keys()) == expected


def test_criteria_block_has_three_lists() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    assert set(record["criteria"].keys()) == {"passed", "failed", "diagnostic_only"}


def test_near_pass_block_has_three_keys() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    assert set(record["near_pass"].keys()) == {
        "is_near_pass", "distance", "nearest_failed_criterion",
    }


def test_promotion_guard_block_has_two_keys() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    assert set(record["promotion_guard"].keys()) == {"promotion_allowed", "blocked_by"}


def test_evidence_fingerprint_is_hex_sha1() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    fp = record["evidence_fingerprint"]
    assert isinstance(fp, str) and len(fp) == 40
    int(fp, 16)


def test_identity_fallback_used_is_false_when_id_present() -> None:
    record = _payload_with_one_candidate()["candidates"][0]
    assert record["identity_fallback_used"] is False
