"""v3.15.10 regression — pin DIGEST_SCHEMA_VERSION at "1.1" and
the new ``funnel_decisions`` top-level key. Backward-load test
for v1.0 fixtures lives in
``test_v3_15_10_digest_v1_0_legacy_loadable.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.campaign_budget import BudgetState
from research.campaign_digest import (
    DIGEST_ARTIFACT_PATH,
    DIGEST_SCHEMA_VERSION,
    DigestInputs,
    build_digest_payload,
)


def _digest(events) -> dict:
    return build_digest_payload(
        DigestInputs(
            registry={"campaigns": {}},
            events=events,
            budget=BudgetState(
                date="2026-04-26",
                daily_compute_budget_seconds=86400,
                reserved_for_followups_seconds=0,
                max_low_value_reruns_per_day=0,
                tier1_fairness_cap=0,
            ),
            preset_states={},
            previous_digest=None,
            max_concurrent_campaigns=2,
        ),
        generated_at_utc=datetime(2026, 4, 26, tzinfo=UTC),
    )


def test_digest_schema_version_pinned_at_1_1() -> None:
    assert DIGEST_SCHEMA_VERSION == "1.1"
    payload = _digest([])
    assert payload["schema_version"] == "1.1"


def test_digest_payload_contains_funnel_decisions_top_level_key() -> None:
    payload = _digest([])
    assert "funnel_decisions" in payload
    assert payload["funnel_decisions"] == {}


def test_digest_artifact_path_unchanged() -> None:
    """Backward-compatible read for the existing two readers
    (campaign_launcher.load_previous_digest and
    dashboard/api_campaigns.py): the file path must NOT change.
    """
    assert str(DIGEST_ARTIFACT_PATH).replace("\\", "/") == (
        "research/campaign_digest_latest.v1.json"
    )


def test_funnel_decisions_aggregates_emitted_events_for_today() -> None:
    today_iso = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC).isoformat()
    events = [
        {"event_type": "funnel_decision_emitted",
         "at_utc": today_iso,
         "extra": {"decision_code": "confirmation_from_exploratory_pass"}},
        {"event_type": "funnel_decision_emitted",
         "at_utc": today_iso,
         "extra": {"decision_code": "follow_up_from_near_pass"}},
        {"event_type": "funnel_decision_emitted",
         "at_utc": today_iso,
         "extra": {"decision_code": "confirmation_from_exploratory_pass"}},
    ]
    payload = _digest(events)
    assert payload["funnel_decisions"] == {
        "confirmation_from_exploratory_pass": 2,
        "follow_up_from_near_pass": 1,
    }


def test_funnel_decisions_ignores_other_event_types() -> None:
    today_iso = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC).isoformat()
    events = [
        {"event_type": "campaign_completed", "at_utc": today_iso, "extra": {}},
        {"event_type": "funnel_evidence_stale_or_mismatched",
         "at_utc": today_iso, "extra": {"decision_code": "ignored"}},
    ]
    payload = _digest(events)
    assert payload["funnel_decisions"] == {}


def test_funnel_decisions_block_is_alphabetically_sorted() -> None:
    today_iso = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC).isoformat()
    events = [
        {"event_type": "funnel_decision_emitted", "at_utc": today_iso,
         "extra": {"decision_code": "zeta_decision"}},
        {"event_type": "funnel_decision_emitted", "at_utc": today_iso,
         "extra": {"decision_code": "alpha_decision"}},
        {"event_type": "funnel_decision_emitted", "at_utc": today_iso,
         "extra": {"decision_code": "mu_decision"}},
    ]
    payload = _digest(events)
    assert list(payload["funnel_decisions"].keys()) == [
        "alpha_decision", "mu_decision", "zeta_decision",
    ]
