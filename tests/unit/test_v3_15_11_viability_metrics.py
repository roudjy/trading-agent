"""v3.15.11 — viability metrics unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research._sidecar_io import serialize_canonical
from research.viability_metrics import (
    VERDICT_COMMERCIALLY_QUESTIONABLE,
    VERDICT_INSUFFICIENT,
    VERDICT_PROMISING,
    VERDICT_STOP_OR_PIVOT,
    VERDICT_WEAK,
    VIABILITY_LARGE_WINDOW,
    VIABILITY_MIN_CAMPAIGNS,
    VIABILITY_SCHEMA_VERSION,
    build_viability_payload,
    write_viability_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"hypothesis_evidence": rows}


def _row(
    *,
    campaign_count: int,
    rejection_count: int = 0,
    technical_failure_count: int = 0,
    promotion_candidate_count: int = 0,
    paper_ready_count: int = 0,
    exploratory_pass_count: int = 0,
) -> dict[str, Any]:
    return {
        "campaign_count": campaign_count,
        "rejection_count": rejection_count,
        "technical_failure_count": technical_failure_count,
        "promotion_candidate_count": promotion_candidate_count,
        "paper_ready_count": paper_ready_count,
        "exploratory_pass_count": exploratory_pass_count,
        "degenerate_count": 0,
    }


def test_insufficient_campaigns_yields_insufficient_data() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([_row(campaign_count=5)]),
    )
    assert payload["verdict"]["status"] == VERDICT_INSUFFICIENT


def test_high_meaningful_rate_yields_promising() -> None:
    history = [
        {"information_gain": {"is_meaningful_campaign": True}}
        for _ in range(VIABILITY_MIN_CAMPAIGNS)
    ]
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([_row(campaign_count=VIABILITY_MIN_CAMPAIGNS)]),
        information_gain_history=history,
    )
    assert payload["verdict"]["status"] == VERDICT_PROMISING


def test_candidate_present_yields_promising_even_without_history() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _row(
                campaign_count=VIABILITY_MIN_CAMPAIGNS,
                promotion_candidate_count=1,
            )
        ]),
    )
    assert payload["verdict"]["status"] == VERDICT_PROMISING


def test_low_info_high_failure_no_candidate_yields_questionable() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _row(
                campaign_count=VIABILITY_MIN_CAMPAIGNS,
                rejection_count=VIABILITY_MIN_CAMPAIGNS,  # 100% rejection
            )
        ]),
        information_gain_history=[
            {"information_gain": {"is_meaningful_campaign": False}}
            for _ in range(VIABILITY_MIN_CAMPAIGNS)
        ],
    )
    assert payload["verdict"]["status"] == VERDICT_COMMERCIALLY_QUESTIONABLE


def test_large_window_no_info_no_candidate_yields_stop_or_pivot() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _row(
                campaign_count=VIABILITY_LARGE_WINDOW,
                rejection_count=10,  # below the questionable threshold
            )
        ]),
        information_gain_history=[
            {"information_gain": {"is_meaningful_campaign": False}}
            for _ in range(VIABILITY_LARGE_WINDOW)
        ],
    )
    assert payload["verdict"]["status"] == VERDICT_STOP_OR_PIVOT


def test_weak_when_some_learning_no_candidate() -> None:
    """Some exploratory passes (medium IG-ish) but no candidate: weak."""
    history = [
        {"information_gain": {"is_meaningful_campaign": i < 5}}
        for i in range(VIABILITY_MIN_CAMPAIGNS)
    ]
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _row(campaign_count=VIABILITY_MIN_CAMPAIGNS, exploratory_pass_count=5)
        ]),
        information_gain_history=history,
    )
    assert payload["verdict"]["status"] == VERDICT_WEAK


def test_cost_divisions_handle_zero_denominators() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([_row(campaign_count=VIABILITY_MIN_CAMPAIGNS)]),
        estimated_compute_cost=100.0,
    )
    metrics = payload["metrics"]
    # No candidates / no paper_ready / no near → all per-X costs collapse to None.
    assert metrics["cost_per_candidate"] is None
    assert metrics["cost_per_paper_ready_candidate"] is None
    assert metrics["cost_per_near_candidate"] is None


def test_no_compute_cost_yields_null_cost_metrics() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _row(campaign_count=VIABILITY_MIN_CAMPAIGNS, promotion_candidate_count=2)
        ]),
        estimated_compute_cost=None,
    )
    metrics = payload["metrics"]
    assert metrics["estimated_compute_cost"] is None
    assert metrics["cost_per_meaningful_campaign"] is None
    assert metrics["cost_per_candidate"] is None


def test_dead_zone_count_passes_through() -> None:
    payload = build_viability_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([_row(campaign_count=VIABILITY_MIN_CAMPAIGNS)]),
        dead_zones=[{"zone_status": "dead"}, {"zone_status": "alive"}],
    )
    assert payload["metrics"]["dead_zone_count"] == 1


def test_byte_identical_payload(tmp_path: Path) -> None:
    led = _ledger([_row(campaign_count=VIABILITY_MIN_CAMPAIGNS, promotion_candidate_count=1)])
    p1 = build_viability_payload(
        run_id="r", as_of_utc=_AS_OF, git_revision="x", evidence_ledger=led
    )
    p2 = build_viability_payload(
        run_id="r", as_of_utc=_AS_OF, git_revision="x", evidence_ledger=led
    )
    assert serialize_canonical(p1) == serialize_canonical(p2)
    assert p1["schema_version"] == VIABILITY_SCHEMA_VERSION
    out = tmp_path / "research" / "campaigns" / "evidence" / "v.json"
    write_viability_artifact(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=led,
        output_path=out,
    )
    assert out.exists()
