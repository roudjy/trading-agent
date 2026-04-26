"""v3.15.9 — identity fallback resilience (REV 3 §6.4 / MF-6 / MF-19).

The builder MUST NOT assert on a malformed candidate dict. A
missing/empty candidate_id triggers a deterministic
``fb_<sha1prefix>`` fallback id, the per-candidate record sets
``identity_fallback_used=True``, and the run-level summary
counts the fallback so operators can spot real upstream defects.
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.screening_evidence import build_screening_evidence_payload


def _build(candidate: dict) -> dict:
    return build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[candidate],
        screening_records=[],
        screening_pass_kinds={},
        paper_blocked_index={},
    )


def test_missing_candidate_id_does_not_crash() -> None:
    payload = _build({"strategy_name": "x", "asset": "BTC", "interval": "1h"})
    assert len(payload["candidates"]) == 1
    assert payload["candidates"][0]["identity_fallback_used"] is True


def test_empty_candidate_id_string_uses_fallback() -> None:
    payload = _build({
        "candidate_id": "",
        "strategy_name": "x",
        "asset": "BTC",
        "interval": "1h",
    })
    assert payload["candidates"][0]["identity_fallback_used"] is True


def test_whitespace_only_candidate_id_uses_fallback() -> None:
    payload = _build({
        "candidate_id": "   ",
        "strategy_name": "x",
        "asset": "BTC",
        "interval": "1h",
    })
    assert payload["candidates"][0]["identity_fallback_used"] is True


def test_fallback_id_is_deterministic_for_same_inputs() -> None:
    seed = {"strategy_name": "trend_pullback", "asset": "BTC", "interval": "1h"}
    a = _build(dict(seed))["candidates"][0]["candidate_id"]
    b = _build(dict(seed))["candidates"][0]["candidate_id"]
    assert a == b
    assert a.startswith("fb_")
    # 16 hex chars after the "fb_" prefix
    hex_part = a.split("_", 1)[1]
    assert len(hex_part) == 16
    int(hex_part, 16)


def test_fallback_id_differs_for_different_inputs() -> None:
    base = {"strategy_name": "trend_pullback", "asset": "BTC", "interval": "1h"}
    other = dict(base, asset="ETH")
    a = _build(base)["candidates"][0]["candidate_id"]
    b = _build(other)["candidates"][0]["candidate_id"]
    assert a != b


def test_summary_counts_identity_fallbacks() -> None:
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[
            {"candidate_id": "ok", "strategy_name": "good", "asset": "BTC", "interval": "1h"},
            {"strategy_name": "no_id_a", "asset": "BTC", "interval": "1h"},
            {"strategy_name": "no_id_b", "asset": "ETH", "interval": "1h"},
        ],
        screening_records=[],
        screening_pass_kinds={},
        paper_blocked_index={},
    )
    assert payload["summary"]["identity_fallbacks"] == 2
    assert payload["summary"]["total_candidates"] == 3


def test_identity_fallback_used_is_per_record() -> None:
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[
            {"candidate_id": "ok", "strategy_name": "good", "asset": "BTC", "interval": "1h"},
            {"strategy_name": "broken", "asset": "BTC", "interval": "1h"},
        ],
        screening_records=[],
        screening_pass_kinds={},
        paper_blocked_index={},
    )
    flags = [r["identity_fallback_used"] for r in payload["candidates"]]
    assert flags == [False, True]
