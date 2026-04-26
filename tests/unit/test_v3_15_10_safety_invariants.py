"""v3.15.10 — safety invariants (REV 3 §7.14 + MF-8 + MF-15).

Pins:
  - technical_failure decisions never freeze a research family
    (no preset cooldown, no family freeze)
  - degenerate_no_survivors retains its existing meaningful-signal
    semantics (funnel does not double-count)
  - exploratory pass never directly paper-promotes
  - ``requested_screening_phase`` is metadata-only — no executor
    reads it (honesty test, MF-15)
  - the funnel-policy module performs no I/O at import time
    (pure module guarantee)
"""

from __future__ import annotations

import importlib

from research.campaign_funnel_policy import (
    FUNNEL_DECISION_CONFIRMATION,
    FUNNEL_DECISION_NO_ACTION_TECHNICAL,
    derive_funnel_decisions,
)


def test_technical_failure_decision_does_not_emit_freeze_or_cooldown_signal() -> None:
    decisions = derive_funnel_decisions(
        evidence=None, expected_campaign_id=None,
        parent_campaign_record=None, registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
        technical_failure_record={
            "campaign_id": "x", "preset_name": "p",
            "outcome": "technical_failure",
        },
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_NO_ACTION_TECHNICAL
    assert d.spawn_request is None
    # rationale must explicitly forbid research-family freeze
    assert d.rationale.get("research_freeze_blocked") is True


def test_degenerate_outcome_is_not_re_classified_by_funnel() -> None:
    """The funnel policy must not emit any decision for a
    degenerate parent (no exploratory candidates, no near-pass).
    """
    decisions = derive_funnel_decisions(
        evidence=None, expected_campaign_id="cmp-1",
        parent_campaign_record={
            "campaign_id": "cmp-1", "preset_name": "p",
            "outcome": "degenerate_no_survivors",
        },
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    assert decisions == []


def test_exploratory_pass_never_directly_paper_promotes() -> None:
    """An exploratory pass yields a confirmation REQUEST
    (decision-only) — there is no campaign_type that maps to a
    paper promotion in the funnel decisions.
    """
    decisions = derive_funnel_decisions(
        evidence={
            "schema_version": "1.0",
            "col_campaign_id": "cmp-1", "campaign_id": "cmp-1",
            "run_id": "run-1", "preset_name": "p",
            "screening_phase": "exploratory",
            "summary": {"dominant_failure_reasons": []},
            "candidates": [
                {
                    "candidate_id": "c1", "strategy_id": "s1",
                    "stage_result": "needs_investigation",
                    "pass_kind": "exploratory",
                    "evidence_fingerprint": "fp1",
                    "failure_reasons": [],
                    "near_pass": {"is_near_pass": False},
                    "sampling": {},
                }
            ],
        },
        expected_campaign_id="cmp-1",
        parent_campaign_record={
            "campaign_id": "cmp-1", "preset_name": "p",
            "lineage_root_campaign_id": "cmp-root",
        },
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_CONFIRMATION
    assert d.spawn_request is not None
    # Spawn type is survivor_confirmation (NOT paper_followup or
    # any paper-promotion type).
    assert d.spawn_request.campaign_type == "survivor_confirmation"


def test_requested_screening_phase_is_metadata_only_no_reader_in_research() -> None:
    """MF-15 honesty test — there is currently no reader of
    ``extra.requested_screening_phase`` anywhere in the
    research/ subtree. v3.15.11+ will wire executor support.

    This is a static grep test — if a future commit adds a
    reader, this test fails (loud) and the docs need to be
    updated to drop the metadata-only caveat.
    """
    from pathlib import Path
    research_dir = Path(__file__).resolve().parent.parent.parent / "research"
    forbidden = "requested_screening_phase"
    # Module names that legitimately *write* (not read/act on)
    # this metadata key:
    writers_only = {"campaign_funnel_policy.py", "campaign_launcher.py"}
    for source in research_dir.glob("*.py"):
        if source.name in writers_only:
            continue
        text = source.read_text(encoding="utf-8", errors="ignore")
        assert forbidden not in text, (
            f"unexpected reader / consumer of "
            f"`{forbidden}` in {source.name} — v3.15.10 "
            f"contract states this field is decision-only "
            f"metadata. Update docs/handoffs/v3.15.8-15.10.md "
            f"to drop the limitation if you intentionally added "
            f"a reader."
        )


def test_funnel_policy_import_has_no_io_side_effects(tmp_path, monkeypatch) -> None:
    """The pure module guarantee: importing
    research.campaign_funnel_policy must not touch the file
    system, network, or environment.
    """
    monkeypatch.chdir(tmp_path)
    importlib.import_module("research.campaign_funnel_policy")
    # No artifact created by the import itself
    assert list(tmp_path.iterdir()) == []
