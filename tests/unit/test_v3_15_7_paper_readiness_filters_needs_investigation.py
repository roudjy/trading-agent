"""v3.15.7 — paper readiness must not promote needs_investigation.

Exploratory passes are downgraded to ``status="needs_investigation"``
in ``candidate_registry_latest.v1.json`` by
``promotion.classify_candidate``. Paper readiness only reaches a
``ready_for_paper_promotion`` verdict when:

- there are no blocking reasons, AND
- the timestamped returns sidecar has at least
  ``MIN_PAPER_OOS_DAYS`` observations, AND
- the ledger has at least one event.

A ``needs_investigation`` candidate produces no ledger events and
no timestamped returns (those are only built for survivors), so the
gate naturally falls through to ``insufficient_evidence``. This
test pins that invariant by constructing a minimal input that
mirrors a needs_investigation flow.
"""

from __future__ import annotations

from research.paper_readiness import (
    MIN_PAPER_OOS_DAYS,
    PaperReadinessInput,
    _classify_status,
    compute_readiness_entry,
)


def _empty_input() -> PaperReadinessInput:
    """An input shape that mirrors a needs_investigation candidate
    flow — no ledger events, no timestamped returns.
    """
    return PaperReadinessInput(
        candidate_id="needs-investigation-strategy",
        asset_type="equity",
        sleeve_id=None,
        timestamped_returns=None,
        ledger_event_count=0,
        projected_insufficient_event_count=0,
        divergence_entry=None,
        paper_sharpe_proxy=None,
    )


def test_classify_status_returns_insufficient_evidence_on_empty():
    status = _classify_status(blocking_reasons=[], input_=_empty_input())
    assert status == "insufficient_evidence"


def test_classify_status_never_returns_ready_with_zero_ledger():
    """With ledger_event_count=0, ready_for_paper_promotion is
    impossible regardless of any optional sharpe.
    """
    status = _classify_status(blocking_reasons=[], input_=_empty_input())
    assert status != "ready_for_paper_promotion"


def test_compute_readiness_entry_on_empty_path_is_not_ready():
    entry = compute_readiness_entry(_empty_input())
    assert entry.readiness_status != "ready_for_paper_promotion"
    assert entry.readiness_status in ("insufficient_evidence", "blocked")


def test_min_paper_oos_days_is_strict_floor():
    """If timestamped returns has 0 obs (needs_investigation default),
    the gate cannot pass.
    """
    assert MIN_PAPER_OOS_DAYS > 0
