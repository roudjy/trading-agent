"""Unit tests for A8 — Autonomous Development Operating Queue Foundation.

Synthetic deterministic fixtures only. No runtime ``/tmp`` baselines
committed. The module is read-only; tests assert the schema, the
closed vocabularies, archive-path rejection, false-positive
suppression for plain headings, deterministic output, and the
absence of any subprocess / network / gh / git / forbidden-package
import.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _seed_path(tmp_path: Path) -> Path:
    return tmp_path / "seed.jsonl"


def _write_seed(tmp_path: Path, lines: list[str]) -> Path:
    p = _seed_path(tmp_path)
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


def _valid_item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "title": "Document A8 governance",
        "source_document": "docs/roadmap/autonomous_development.txt",
        "source_section_or_anchor": "A8.1",
        "roadmap_track": "autonomous_development",
        "category": "docs",
        "required_agent_role": "implementation_agent",
        "supporting_agent_roles": ["test_agent"],
        "status": "ready",
        "human_needed": False,
        "human_needed_reason": "none",
        "blocked_by": [],
        "priority": 3,
        "risk_level": "LOW",
        "protected_surface": False,
        "acceptance_criteria": ["Doc page lands"],
        "validation_requirements": ["Lints clean"],
        "notes": "scoped item",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Vocabulary integrity
# ---------------------------------------------------------------------------


def test_agent_roles_vocabulary_is_closed_and_ordered() -> None:
    assert dwq.AGENT_ROLES == (
        "product_owner",
        "strategic_advisor",
        "quant_research_architect",
        "planner",
        "architecture_guardian",
        "ci_guardian",
        "implementation_agent",
        "frontend_agent",
        "test_agent",
        "determinism_guardian",
        "evidence_verifier",
        "observability_guardian",
        "deployment_safety_agent",
        "adversarial_reviewer",
        "release_gate_agent",
        "human_operator",
    )
    assert len(dwq.AGENT_ROLES) == 16
    assert "human_operator" in dwq.AGENT_ROLES


def test_statuses_vocabulary_is_closed_and_ordered() -> None:
    assert dwq.STATUSES == (
        "proposed",
        "triaged",
        "planned",
        "ready",
        "in_progress",
        "blocked",
        "human_needed",
        "review_needed",
        "validation_needed",
        "done",
        "rejected",
        "archived",
    )
    assert len(dwq.STATUSES) == 12


def test_categories_vocabulary_is_closed_and_ordered() -> None:
    assert dwq.CATEGORIES == (
        "governance",
        "reporting",
        "frontend",
        "test",
        "docs",
        "ci",
        "deployment",
        "release",
        "observability",
        "refactor",
    )
    assert len(dwq.CATEGORIES) == 10


def test_human_needed_reasons_vocabulary_is_closed_with_none_terminator() -> None:
    assert dwq.HUMAN_NEEDED_REASONS == (
        "architecture_crossroads",
        "protected_governance_change",
        "frozen_contract_change",
        "risk_policy_change",
        "capital_or_live_execution_related",
        "destructive_or_irreversible_action",
        "priority_conflict",
        "ambiguous_scope",
        "missing_acceptance_criteria",
        "repeated_validation_failure",
        "none",
    )
    # Eleven entries: ten real reasons plus the explicit "none" sentinel.
    assert len(dwq.HUMAN_NEEDED_REASONS) == 11
    assert "none" in dwq.HUMAN_NEEDED_REASONS


def test_roadmap_tracks_vocabulary_is_closed() -> None:
    assert dwq.ROADMAP_TRACKS == (
        "autonomous_development",
        "qre_feature_build",
        "sidecar_seed",
    )


def test_risk_levels_match_execution_authority() -> None:
    """Risk levels are reused verbatim from the classifier — never
    redefined here."""
    assert dwq.RISK_LEVELS == ea.RISK_CLASSES


def test_canonical_roadmap_paths_match_execution_authority_doctrine() -> None:
    assert set(dwq.CANONICAL_ROADMAP_PATHS) == {
        "docs/roadmap/autonomous_development.txt",
        "docs/roadmap/Roadmap v6.md",
    }


def test_item_schema_keys_are_exact_and_ordered() -> None:
    assert dwq.ITEM_SCHEMA_KEYS == (
        "item_id",
        "title",
        "source_document",
        "source_section_or_anchor",
        "roadmap_track",
        "category",
        "required_agent_role",
        "supporting_agent_roles",
        "execution_authority",
        "status",
        "human_needed",
        "human_needed_reason",
        "blocked_by",
        "priority",
        "risk_level",
        "protected_surface",
        "acceptance_criteria",
        "validation_requirements",
        "created_at_placeholder",
        "updated_at_placeholder",
        "notes",
    )


# ---------------------------------------------------------------------------
# Artifact path
# ---------------------------------------------------------------------------


def test_artifact_path_is_under_logs_not_research() -> None:
    assert dwq.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in dwq.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dwq._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys_when_seed_absent(tmp_path: Path) -> None:
    seed = tmp_path / "missing.jsonl"
    snap = dwq.collect_snapshot(seed_path=seed)
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "source_document_paths",
        "seed_path",
        "seed_present",
        "source_available",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "items",
        "execution_authority_module_version",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_work_queue"
    assert snap["source_available"] is True
    assert snap["seed_present"] is False
    assert snap["note"] == dwq.NOTE_SEED_FILE_ABSENT
    assert snap["items"] == []
    assert snap["counts"]["total"] == 0


def test_empty_seed_yields_zero_items_with_clear_note(tmp_path: Path) -> None:
    """A seed file with only blank lines (strict JSONL) reports
    `seed_file_empty`. There are no comment lines in JSONL."""
    seed = _write_seed(tmp_path, ["", "", ""])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["seed_present"] is True
    assert snap["items"] == []
    assert snap["note"] == dwq.NOTE_SEED_FILE_EMPTY


def test_zero_byte_seed_file_yields_zero_items(tmp_path: Path) -> None:
    """The committed `seed.jsonl` is a zero-byte file. The parser
    must handle that without raising."""
    seed = _seed_path(tmp_path)
    seed.write_bytes(b"")
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["seed_present"] is True
    assert snap["items"] == []
    assert snap["note"] == dwq.NOTE_SEED_FILE_EMPTY


def test_default_seed_file_in_repo_carries_minimal_v3_15_x_active_queue() -> None:
    """The committed seed file under `docs/development_work_queue/`
    carries the operator-declared minimal Roadmap v6 active queue
    rebuilt on 2026-05-21 per ADR-018 (roadmap execution reset).

    State progression pinned by this test (after v3.15.17 PR):

    * Item 1 (sprint) — ``done`` (deliverables merged in PR #264 and
      PR #267).
    * Item 2 (Minimal v3.15.16 Intelligent Routing slice) — ``done``
      (shipped in PR #268, merge d9ad118).
    * Item 3 (Minimal v3.15.17 Sampling Intelligence slice) —
      ``in_progress`` (shipping in this PR).
    * Items 4, 5 (Minimal v3.15.18, v3.15.19 slices) — ``blocked``.
    * Item 6 (STOP / operator review gate) — ``blocked`` and
      ``human_needed`` with reason ``architecture_crossroads``.

    Strengthened from the prior pin to track the v3.15.17 state.
    """
    snap = dwq.collect_snapshot()
    assert snap["counts"]["total"] == 6
    assert snap["note"] == dwq.NOTE_ITEMS_PRESENT
    assert snap["validation_warnings"] == []
    titles = [it["title"] for it in snap["items"]]
    # Ordering is by item_id ascending (deterministic), so assert
    # membership rather than position.
    expected_titles = {
        "Research-Quality Hardening Sprint",
        "Minimal v3.15.16 Intelligent Routing slice",
        "Minimal v3.15.17 Sampling Intelligence slice",
        "Minimal v3.15.18 Research Observability Expansion slice",
        "Minimal v3.15.19 Hypothesis Discovery Engine slice",
        "STOP - operator review gate after minimal v3.15.19",
    }
    assert set(titles) == expected_titles
    # State progression as of this PR:
    # items 1, 2 done; item 3 in_progress; items 4-6 blocked.
    by_status = snap["counts"]["by_status"]
    assert by_status["done"] == 2
    assert by_status["in_progress"] == 1
    assert by_status["blocked"] == 3
    assert by_status["ready"] == 0
    # Title-specific state assertions.
    by_title = {it["title"]: it for it in snap["items"]}
    assert (
        by_title["Research-Quality Hardening Sprint"]["status"]
        == "done"
    )
    assert (
        by_title["Minimal v3.15.16 Intelligent Routing slice"]["status"]
        == "done"
    )
    assert (
        by_title["Minimal v3.15.17 Sampling Intelligence slice"]["status"]
        == "in_progress"
    )
    assert (
        by_title["Minimal v3.15.18 Research Observability Expansion slice"][
            "status"
        ]
        == "blocked"
    )
    assert (
        by_title["Minimal v3.15.19 Hypothesis Discovery Engine slice"][
            "status"
        ]
        == "blocked"
    )
    assert (
        by_title["STOP - operator review gate after minimal v3.15.19"][
            "status"
        ]
        == "blocked"
    )
    # Exactly one item requires explicit human action (the STOP gate).
    human_needed_items = [it for it in snap["items"] if it["human_needed"]]
    assert len(human_needed_items) == 1
    assert human_needed_items[0]["title"].startswith("STOP")
    assert human_needed_items[0]["human_needed_reason"] == "architecture_crossroads"
    # No item touches a protected surface.
    assert all(it["protected_surface"] is False for it in snap["items"])
    # Risk is bounded to LOW / MEDIUM. No HIGH / UNKNOWN at this stage.
    assert {it["risk_level"] for it in snap["items"]} <= {"LOW", "MEDIUM"}


def test_committed_repo_seed_file_is_strict_jsonl_no_comments() -> None:
    """`docs/development_work_queue/seed.jsonl` must be valid JSONL —
    every non-blank line must parse as JSON. No `#`-prefixed comment
    lines are allowed in the canonical file."""
    seed_file = dwq.DEFAULT_SEED_PATH
    assert seed_file.is_file(), f"committed seed.jsonl missing at {seed_file}"
    raw = seed_file.read_text(encoding="utf-8")
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        assert not s.startswith("#"), (
            "JSONL must not contain `#` comment lines"
        )
        json.loads(s)


# ---------------------------------------------------------------------------
# Plain headings must NOT become items
# ---------------------------------------------------------------------------


def test_plain_h2_h3_headings_in_seed_do_not_become_items(tmp_path: Path) -> None:
    """The seed parser only consumes JSON object lines. Plain headings
    are non-JSON and must be reported as `invalid_json` warnings, not
    promoted to queue items."""
    seed = _write_seed(
        tmp_path,
        [
            "## A8 Operating Queue",
            "### Sub-section",
            "Some prose explaining the section.",
        ],
    )
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        w.startswith("seed_line_") and w.endswith("_invalid_json")
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Item parsing
# ---------------------------------------------------------------------------


def test_valid_seed_item_round_trips(tmp_path: Path) -> None:
    item = _valid_item()
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["counts"]["total"] == 1
    parsed = snap["items"][0]
    assert set(parsed.keys()) == set(dwq.ITEM_SCHEMA_KEYS)
    assert parsed["title"] == item["title"]
    assert parsed["source_document"] == item["source_document"]
    assert parsed["roadmap_track"] == "autonomous_development"
    assert parsed["status"] == "ready"
    assert parsed["execution_authority"] == ea.DECISION_NEEDS_HUMAN
    # autonomous_development.txt is canonical_roadmap → NEEDS_HUMAN.


def test_item_id_is_deterministic(tmp_path: Path) -> None:
    item = _valid_item(title="t", source_section_or_anchor="s")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap_a = dwq.collect_snapshot(seed_path=seed)
    snap_b = dwq.collect_snapshot(seed_path=seed)
    assert snap_a["items"][0]["item_id"] == snap_b["items"][0]["item_id"]
    assert snap_a["items"][0]["item_id"].startswith("dwq_")


def test_item_carries_deterministic_timestamp_placeholders(tmp_path: Path) -> None:
    seed = _write_seed(tmp_path, [json.dumps(_valid_item())])
    snap = dwq.collect_snapshot(seed_path=seed)
    item = snap["items"][0]
    assert item["created_at_placeholder"] == dwq.ITEM_TIME_PLACEHOLDER
    assert item["updated_at_placeholder"] == dwq.ITEM_TIME_PLACEHOLDER


def test_archive_path_source_document_is_rejected(tmp_path: Path) -> None:
    item = _valid_item(
        source_document="docs/roadmap/archive/qre_roadmap_v6_1.md",
        roadmap_track="qre_feature_build",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        "archive_path_rejected" in w for w in snap["validation_warnings"]
    )


def test_non_canonical_source_document_is_rejected_for_roadmap_tracks(
    tmp_path: Path,
) -> None:
    item = _valid_item(
        source_document="docs/some/other/file.md",
        roadmap_track="autonomous_development",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        "non_canonical_source_document" in w for w in snap["validation_warnings"]
    )


def test_sidecar_seed_track_accepts_sidecar_source(tmp_path: Path) -> None:
    item = _valid_item(
        source_document="sidecar_seed",
        roadmap_track="sidecar_seed",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["counts"]["total"] == 1


def test_qre_feature_build_track_requires_canonical_roadmap_path(
    tmp_path: Path,
) -> None:
    item = _valid_item(
        source_document="docs/roadmap/Roadmap v6.md",
        roadmap_track="qre_feature_build",
        risk_level="LOW",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["counts"]["total"] == 1
    assert snap["items"][0]["roadmap_track"] == "qre_feature_build"


def test_invalid_roadmap_track_rejected(tmp_path: Path) -> None:
    item = _valid_item(roadmap_track="completely_made_up_track")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any("invalid_roadmap_track" in w for w in snap["validation_warnings"])


def test_invalid_status_rejected(tmp_path: Path) -> None:
    item = _valid_item(status="not_a_status")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any("invalid_status" in w for w in snap["validation_warnings"])


def test_invalid_role_rejected(tmp_path: Path) -> None:
    item = _valid_item(required_agent_role="not_an_agent")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        "invalid_required_agent_role" in w
        for w in snap["validation_warnings"]
    )


def test_invalid_category_rejected(tmp_path: Path) -> None:
    item = _valid_item(category="not_a_category")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any("invalid_category" in w for w in snap["validation_warnings"])


def test_invalid_risk_level_rejected(tmp_path: Path) -> None:
    item = _valid_item(risk_level="EXTREME")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any("invalid_risk_level" in w for w in snap["validation_warnings"])


def test_human_needed_true_requires_non_none_reason(tmp_path: Path) -> None:
    item = _valid_item(human_needed=True, human_needed_reason="none")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        "human_needed_true_but_reason_none" in w
        for w in snap["validation_warnings"]
    )


def test_human_needed_false_requires_reason_none(tmp_path: Path) -> None:
    item = _valid_item(human_needed=False, human_needed_reason="ambiguous_scope")
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == []
    assert any(
        "human_needed_false_but_reason_not_none" in w
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Cross-validation against execution_authority
# ---------------------------------------------------------------------------


def test_doc_non_policy_low_risk_yields_auto_allowed(tmp_path: Path) -> None:
    """A LOW-risk edit to a non-policy doc path classifies as
    AUTO_ALLOWED. The queue surfaces this as the
    ``execution_authority`` field on the item."""
    item = _valid_item(
        source_document="docs/operator/notes.md",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"][0]["execution_authority"] == ea.DECISION_AUTO_ALLOWED


def test_bare_sidecar_seed_source_falls_through_to_needs_human(
    tmp_path: Path,
) -> None:
    """An item declaring `sidecar_seed` as both track and source —
    i.e. naming no concrete target path — must classify as
    NEEDS_HUMAN under the fail-safe rule. The classifier maps any
    unrecognised path to `other`, and `other` + modify is gated.
    Operators must point items at a concrete target to obtain
    AUTO_ALLOWED."""
    item = _valid_item(
        source_document="sidecar_seed",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"][0]["execution_authority"] == ea.DECISION_NEEDS_HUMAN


def test_canonical_policy_doc_yields_needs_human(tmp_path: Path) -> None:
    """An item naming a canonical_policy_doc as its source must
    produce a NEEDS_HUMAN authority decision regardless of risk
    level."""
    item = _valid_item(
        source_document="docs/governance/execution_authority.md",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"][0]["execution_authority"] == ea.DECISION_NEEDS_HUMAN


def test_authority_auto_allowed_with_human_needed_true_emits_warning(
    tmp_path: Path,
) -> None:
    item = _valid_item(
        source_document="docs/operator/notes.md",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
        human_needed=True,
        human_needed_reason="ambiguous_scope",
    )
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert any(
        "human_needed_true_but_authority_auto_allowed" in w
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_and_close_vocabularies(tmp_path: Path) -> None:
    a = _valid_item(
        title="A",
        source_document="docs/operator/notes.md",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
        status="ready",
        human_needed=False,
        human_needed_reason="none",
        category="reporting",
        required_agent_role="implementation_agent",
    )
    b = _valid_item(
        title="B",
        source_document="docs/governance/execution_authority.md",
        roadmap_track="sidecar_seed",
        risk_level="HIGH",
        status="human_needed",
        human_needed=True,
        human_needed_reason="protected_governance_change",
        category="governance",
        required_agent_role="human_operator",
        protected_surface=True,
    )
    c = _valid_item(
        title="C",
        source_document="sidecar_seed",
        roadmap_track="sidecar_seed",
        risk_level="LOW",
        status="blocked",
        human_needed=False,
        human_needed_reason="none",
        category="test",
        required_agent_role="test_agent",
        blocked_by=["dwq_deadbeef0000"],
    )
    seed = _write_seed(
        tmp_path, [json.dumps(a), json.dumps(b), json.dumps(c)]
    )
    snap = dwq.collect_snapshot(seed_path=seed)
    counts = snap["counts"]
    assert counts["total"] == 3
    assert sum(counts["by_status"].values()) == 3
    assert sum(counts["by_role"].values()) == 3
    assert sum(counts["by_category"].values()) == 3
    assert counts["human_needed"] == 1
    assert counts["blocked"] == 1
    assert counts["protected_surface"] == 1
    # Item A is AUTO_ALLOWED + ready + not human_needed → ready_for_autonomous_action.
    assert counts["ready_for_autonomous_action"] >= 1
    # Item B is human_needed + NEEDS_HUMAN → requiring_human_operator.
    assert counts["requiring_human_operator"] >= 1
    # Vocabularies in by_status / by_role / by_category cover all keys.
    assert set(counts["by_status"]) == set(dwq.STATUSES)
    assert set(counts["by_role"]) == set(dwq.AGENT_ROLES)
    assert set(counts["by_category"]) == set(dwq.CATEGORIES)


# ---------------------------------------------------------------------------
# Determinism + sorted JSON output
# ---------------------------------------------------------------------------


def test_artifact_bytes_are_deterministic_with_injected_timestamp(
    tmp_path: Path,
) -> None:
    """The pure generator is byte-stable across repeated calls when
    the same `generated_at_utc` is injected. This confirms the only
    non-deterministic field is the wrapper timestamp; everything
    else (item ids, ordering, counts, vocabularies) is pinned."""
    item_a = _valid_item(title="alpha", source_section_or_anchor="A.1")
    item_b = _valid_item(title="bravo", source_section_or_anchor="A.2")
    seed = _write_seed(tmp_path, [json.dumps(item_a), json.dumps(item_b)])

    fixed_ts = "2026-05-07T00:00:00Z"
    snap_a = dwq.collect_snapshot(seed_path=seed, generated_at_utc=fixed_ts)
    snap_b = dwq.collect_snapshot(seed_path=seed, generated_at_utc=fixed_ts)

    bytes_a = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    bytes_b = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert bytes_a == bytes_b
    assert snap_a["generated_at_utc"] == fixed_ts


def test_runtime_timestamp_changes_between_calls(tmp_path: Path) -> None:
    """When `generated_at_utc` is *not* injected, the wrapper carries
    the runtime UTC clock — and is therefore not byte-identical
    across different wall-clock seconds. The pure generator is
    byte-stable only with injected `generated_at_utc`."""
    seed = _write_seed(tmp_path, [json.dumps(_valid_item())])
    snap = dwq.collect_snapshot(seed_path=seed)
    # The runtime timestamp is a non-empty UTC string.
    assert isinstance(snap["generated_at_utc"], str)
    assert snap["generated_at_utc"].endswith("Z")
    # Items are byte-stable regardless of the wrapper timestamp.
    snap2 = dwq.collect_snapshot(seed_path=seed)
    assert snap["items"] == snap2["items"]


def test_items_sort_by_priority_then_id(tmp_path: Path) -> None:
    high_pri = _valid_item(
        title="high",
        source_section_or_anchor="X",
        priority=1,
        source_document="sidecar_seed",
        roadmap_track="sidecar_seed",
    )
    low_pri = _valid_item(
        title="low",
        source_section_or_anchor="Y",
        priority=5,
        source_document="sidecar_seed",
        roadmap_track="sidecar_seed",
    )
    seed = _write_seed(tmp_path, [json.dumps(low_pri), json.dumps(high_pri)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert [it["title"] for it in snap["items"]] == ["high", "low"]


# ---------------------------------------------------------------------------
# Bounded scalars / no body content
# ---------------------------------------------------------------------------


def test_long_title_is_bounded(tmp_path: Path) -> None:
    long = "x" * (dwq.MAX_TITLE_LEN * 4)
    item = _valid_item(title=long)
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert snap["counts"]["total"] == 1
    assert len(snap["items"][0]["title"]) <= dwq.MAX_TITLE_LEN


def test_long_notes_field_is_bounded(tmp_path: Path) -> None:
    long_notes = "z" * (dwq.MAX_NOTES_LEN * 3)
    item = _valid_item(notes=long_notes)
    seed = _write_seed(tmp_path, [json.dumps(item)])
    snap = dwq.collect_snapshot(seed_path=seed)
    assert len(snap["items"][0]["notes"]) <= dwq.MAX_NOTES_LEN


def test_priority_is_clamped_to_1_5(tmp_path: Path) -> None:
    too_high = _valid_item(title="too_high", priority=99)
    too_low = _valid_item(title="too_low", priority=-3)
    bogus = _valid_item(title="bogus", priority="not_a_number")
    seed = _write_seed(
        tmp_path,
        [json.dumps(too_high), json.dumps(too_low), json.dumps(bogus)],
    )
    snap = dwq.collect_snapshot(seed_path=seed)
    by_title = {it["title"]: it["priority"] for it in snap["items"]}
    assert by_title["too_high"] == 5
    assert by_title["too_low"] == 1
    assert by_title["bogus"] == 3


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source(mod_path_attr: str = "__file__") -> str:
    p = Path(getattr(dwq, mod_path_attr))
    return p.read_text(encoding="utf-8")


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in ("import socket", "import urllib", "import http.client", "import requests"):
        assert forbidden not in src
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src
    assert "from requests" not in src


def test_no_dashboard_or_live_path_imports() -> None:
    src = _module_source()
    for forbidden in (
        "import dashboard",
        "from dashboard",
        "import automation",
        "from automation",
        "import broker",
        "from broker",
        "import agent.risk",
        "import agent.execution",
        "from agent.risk",
        "from agent.execution",
        "from research",
        "import research",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    """Re-import the module to confirm no startup side-effects."""
    importlib.reload(dwq)
    assert callable(dwq.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(dwq.SCHEMA_VERSION, str) and dwq.SCHEMA_VERSION
    assert isinstance(dwq.MODULE_VERSION, str) and dwq.MODULE_VERSION
    assert "A8" in dwq.MODULE_VERSION
