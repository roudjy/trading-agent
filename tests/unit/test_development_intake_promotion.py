"""Unit tests for A16a — Intake Candidate Promotion Staging.

Synthetic deterministic fixtures only. The pure projector consumes
``logs/development_roadmap_intake/latest.json`` (read-only) and emits
``logs/development_intake_promotion/latest.json`` — never mutating
any seed file.

Hard guarantees pinned here:

* Closed vocabularies (`DECISION_STATES`, `VALIDATION_WARNINGS`,
  `PROMOTION_TARGETS`, `PROMOTION_SCHEMA_KEYS`) are byte-exact.
* The current real candidate
  ``qre_v3_15_16_addendum_source_manifest_001`` becomes
  ``decision_state="eligible"`` with ``promotion_target="none"``.
* Non-eligible upstream statuses never become ``eligible``.
* Classification drift forces ``blocked`` + warning.
* Already-in-seed and already-in-delegation dedupe to
  ``already_promoted``.
* Module does not open seed files for writing.
* No subprocess / socket / urllib / requests / httpx / aiohttp / gh /
  git in the module.
* No imports of dashboard / frontend / automation / broker /
  agent.risk / agent.execution / research /
  reporting.intelligent_routing / live / paper / shadow / trading.
* Importing the module does not flip Step 5 invariants.
* Atomic write refuses any path outside
  ``logs/development_intake_promotion/``.
* Doc states no seed writes and A16b is operator-gated.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_intake_promotion as dip
from reporting import development_roadmap_intake as dri
from reporting import execution_authority as ea
from reporting import notification_event as ne


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _eligible_candidate(
    *, candidate_id: str = "syn_eligible_001", source_kind: str = "operating_manual"
) -> dict[str, Any]:
    return {
        "acceptance_criteria": ["candidate appears in promotion latest.json"],
        "candidate_id": candidate_id,
        "candidate_kind": "docs",
        "category": "docs",
        "execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "execution_authority_reason": "low_risk_docs_non_policy",
        "human_needed": False,
        "human_needed_reason": "none",
        "intake_status": "eligible",
        "notes": "",
        "promotion_target": "none",
        "required_agent_role": "planner",
        "risk_level": "LOW",
        "roadmap_phase": "v3.15.16",
        "source_anchor": "marker_1",
        "source_document": "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        "source_kind": source_kind,
        "target_path": "docs/governance/agent_run_summaries/syn.md",
        "title": "Synthetic eligible candidate",
        "validation_requirements": [],
    }


def _intake_artifact(*, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "module_version": dri.MODULE_VERSION,
        "report_kind": "development_roadmap_intake",
        "generated_at_utc": "2026-05-08T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "canonical_source_paths": list(dri.DEFAULT_SOURCE_PATHS),
        "source_paths_used": [],
        "source_paths_missing": [],
        "note": "intake_candidates_present" if candidates else "no_explicit_intake_candidates",
        "validation_warnings": [],
        "vocabularies": {
            "source_kinds": list(dri.SOURCE_KINDS),
            "candidate_kinds": list(dri.CANDIDATE_KINDS),
            "intake_statuses": list(dri.INTAKE_STATUSES),
            "promotion_targets": list(dri.PROMOTION_TARGETS),
        },
        "counts": {"total": len(candidates)},
        "candidates": candidates,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": "v0",
        "discipline_invariants": {},
    }


def _write_intake_artifact(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


def _write_seed(
    tmp_path: Path, name: str, lines: list[dict[str, Any]]
) -> Path:
    p = tmp_path / "docs" / "development_work_queue" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(line, sort_keys=True) for line in lines)
    p.write_text(body + ("\n" if lines else ""), encoding="utf-8")
    return p


def _empty_history(tmp_path: Path) -> Path:
    return tmp_path / "logs" / "development_intake_promotion" / "history.jsonl"


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_decision_states_pinned_exactly() -> None:
    assert dip.DECISION_STATES == (
        "pending",
        "eligible",
        "human_needed",
        "blocked",
        "rejected",
        "already_promoted",
    )


def test_validation_warnings_pinned_exactly() -> None:
    assert dip.VALIDATION_WARNINGS == (
        "intake_artifact_absent",
        "intake_artifact_unparseable",
        "classification_drift",
        "duplicate_candidate_id_in_cycle",
        "duplicate_unchanged_history_entry",
        "candidate_missing_target_path",
        "candidate_invalid_risk_level",
        "candidate_invalid_intake_status",
    )


def test_promotion_targets_pinned_exactly() -> None:
    assert dip.PROMOTION_TARGETS == (
        "none",
        "development_work_queue",
        "development_delegation",
    )


def test_promotion_schema_keys_pinned_exactly_and_ordered() -> None:
    assert dip.PROMOTION_SCHEMA_KEYS == (
        "candidate_id",
        "title",
        "source_document",
        "source_kind",
        "roadmap_phase",
        "candidate_kind",
        "required_agent_role",
        "risk_level",
        "target_path",
        "upstream_intake_status",
        "upstream_execution_authority_decision",
        "reclassified_execution_authority_decision",
        "reclassified_execution_authority_reason",
        "classification_drift",
        "human_needed",
        "human_needed_reason",
        "acceptance_criteria",
        "evidence_hash",
        "notification_event_kind",
        "notification_event_severity",
        "already_in_seed_jsonl",
        "already_in_delegation_seed",
        "duplicate_of_history_entry",
        "decision_state",
        "promotion_target",
        "notes",
    )


def test_artifact_paths_under_logs_only() -> None:
    assert dip.ARTIFACT_RELATIVE_PATH.startswith(
        "logs/development_intake_promotion/"
    )
    assert "research/" not in dip.ARTIFACT_RELATIVE_PATH
    assert dip.HISTORY_RELATIVE_PATH.startswith(
        "logs/development_intake_promotion/"
    )


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_step5_invariants_pinned() -> None:
    assert dip.step5_implementation_allowed is False
    assert dip.STEP5_ENABLED_SUBSTAGE == "none"


def test_snapshot_carries_step5_invariants(tmp_path: Path) -> None:
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["step5_enabled_substage"] == "none"
    assert snap["step5_implementation_allowed"] is False


def test_discipline_invariants_present(tmp_path: Path) -> None:
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"
    assert inv["uses_subprocess_or_network"] is False
    assert inv["calls_llm_or_external_api"] is False


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "intake_artifact_path",
        "intake_artifact_available",
        "seed_path",
        "seed_present",
        "delegation_seed_path",
        "delegation_seed_present",
        "history_path",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "execution_authority_module_version",
        "intake_module_version",
        "notification_event_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_intake_promotion"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_promotion_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        dip._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = (
        tmp_path
        / "logs"
        / "development_roadmap_intake"
        / "latest.json"
    )
    with pytest.raises(ValueError):
        dip._atomic_write_json(bad, {"x": 1})


def test_history_append_refuses_non_promotion_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "history.jsonl"
    with pytest.raises(ValueError):
        dip._append_history(bad, [{"candidate_id": "x", "evidence_hash": "y"}])


# ---------------------------------------------------------------------------
# Eligible happy path — current real candidate
# ---------------------------------------------------------------------------


def _real_eligible_candidate() -> dict[str, Any]:
    """Mirrors the live A15 candidate (PR #160) verbatim — the
    target_path and risk_level reclassify cleanly to AUTO_ALLOWED."""
    return {
        "acceptance_criteria": [
            "Candidate appears in logs/development_roadmap_intake/latest.json",
            "Execution Authority classifies target path AUTO_ALLOWED at LOW risk",
            "Step 5.0 dry-run can plan from this candidate after operator promotion",
        ],
        "candidate_id": "qre_v3_15_16_addendum_source_manifest_001",
        "candidate_kind": "docs",
        "category": "docs",
        "execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "execution_authority_reason": "low_risk_docs_non_policy",
        "human_needed": False,
        "human_needed_reason": "none",
        "intake_status": "eligible",
        "notes": "",
        "promotion_target": "none",
        "required_agent_role": "planner",
        "risk_level": "LOW",
        "roadmap_phase": "v3.15.16",
        "source_anchor": "marker_1",
        "source_document": (
            "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md"
        ),
        "source_kind": "operating_manual",
        "target_path": (
            "docs/governance/agent_run_summaries/"
            "qre_addendum_source_manifest_001.md"
        ),
        "title": (
            "Draft diagnostic-source manifest operating surface for "
            "Roadmap v6 Addendum §9.3 fields"
        ),
        "validation_requirements": [],
    }


def test_real_a15_candidate_becomes_eligible_with_promotion_target_none(
    tmp_path: Path,
) -> None:
    intake = _write_intake_artifact(
        tmp_path, _intake_artifact(candidates=[_real_eligible_candidate()])
    )
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["counts"]["total"] == 1
    row = snap["rows"][0]
    assert set(row.keys()) == set(dip.PROMOTION_SCHEMA_KEYS)
    assert row["candidate_id"] == "qre_v3_15_16_addendum_source_manifest_001"
    assert row["decision_state"] == "eligible"
    assert row["promotion_target"] == "none"
    assert row["reclassified_execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED
    assert row["classification_drift"] is False
    assert row["already_in_seed_jsonl"] is False
    assert row["already_in_delegation_seed"] is False
    # N1 mapping for an eligible candidate.
    assert row["notification_event_kind"] == "intake_candidate_eligible"
    assert row["notification_event_severity"] == "push_info"


def test_synthetic_eligible_candidate_eligibility(tmp_path: Path) -> None:
    intake = _write_intake_artifact(
        tmp_path, _intake_artifact(candidates=[_eligible_candidate()])
    )
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    row = snap["rows"][0]
    assert row["decision_state"] == "eligible"
    assert row["promotion_target"] == "none"
    assert snap["counts"]["eligible"] == 1


# ---------------------------------------------------------------------------
# Non-eligible never promotes
# ---------------------------------------------------------------------------


def test_human_needed_upstream_status_never_eligible(tmp_path: Path) -> None:
    cand = _eligible_candidate()
    cand["intake_status"] = "human_needed"
    cand["human_needed"] = True
    cand["human_needed_reason"] = "architecture_crossroads"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["rows"][0]["decision_state"] == "human_needed"
    assert snap["counts"]["eligible"] == 0


def test_blocked_upstream_status_never_eligible(tmp_path: Path) -> None:
    cand = _eligible_candidate()
    cand["intake_status"] = "blocked"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["rows"][0]["decision_state"] == "blocked"


def test_rejected_upstream_status_stays_rejected(tmp_path: Path) -> None:
    cand = _eligible_candidate()
    cand["intake_status"] = "rejected"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["rows"][0]["decision_state"] == "rejected"


def test_proposed_upstream_status_does_not_become_eligible(
    tmp_path: Path,
) -> None:
    cand = _eligible_candidate()
    cand["intake_status"] = "proposed"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["rows"][0]["decision_state"] != "eligible"


def test_human_needed_true_overrides_auto_allowed(tmp_path: Path) -> None:
    """Operator-explicit human_needed=true forces human_needed even if
    AUTO_ALLOWED."""
    cand = _eligible_candidate()
    cand["human_needed"] = True
    cand["human_needed_reason"] = "architecture_crossroads"
    cand["intake_status"] = "human_needed"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["rows"][0]["decision_state"] == "human_needed"


# ---------------------------------------------------------------------------
# Classification drift
# ---------------------------------------------------------------------------


def test_classification_drift_forces_blocked(tmp_path: Path) -> None:
    """Upstream claims AUTO_ALLOWED; we re-classify the same target
    against a HIGH risk-class — the result should be NEEDS_HUMAN, so
    drift fires and the row is blocked."""
    cand = _eligible_candidate()
    cand["risk_level"] = "HIGH"  # forces NEEDS_HUMAN reclass on a docs target
    cand["execution_authority_decision"] = ea.DECISION_AUTO_ALLOWED  # upstream lie
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert row["classification_drift"] is True
    assert any(
        "classification_drift" in w for w in snap["validation_warnings"]
    )


def test_permanently_denied_target_blocks(tmp_path: Path) -> None:
    cand = _eligible_candidate()
    cand["target_path"] = "research/research_latest.json"  # frozen contract
    cand["risk_level"] = "HIGH"
    cand["execution_authority_decision"] = ea.DECISION_PERMANENTLY_DENIED
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert row["reclassified_execution_authority_decision"] == ea.DECISION_PERMANENTLY_DENIED


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


def test_already_in_seed_jsonl_dedupes(tmp_path: Path) -> None:
    cand = _eligible_candidate(candidate_id="dup_seed_001")
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    seed_p = _write_seed(
        tmp_path,
        "seed.jsonl",
        [{"item_id": "dup_seed_001", "title": "already there"}],
    )
    delegation_p = _write_seed(tmp_path, "delegation_seed.jsonl", [])
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=seed_p,
        delegation_seed_path=delegation_p,
        history_path=_empty_history(tmp_path),
    )
    row = snap["rows"][0]
    assert row["decision_state"] == "already_promoted"
    assert row["already_in_seed_jsonl"] is True


def test_already_in_delegation_seed_dedupes(tmp_path: Path) -> None:
    cand = _eligible_candidate(candidate_id="dup_deleg_001")
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    seed_p = _write_seed(tmp_path, "seed.jsonl", [])
    delegation_p = _write_seed(
        tmp_path,
        "delegation_seed.jsonl",
        [{"delegation_id": "dup_deleg_001", "title": "already there"}],
    )
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=seed_p,
        delegation_seed_path=delegation_p,
        history_path=_empty_history(tmp_path),
    )
    row = snap["rows"][0]
    assert row["decision_state"] == "already_promoted"
    assert row["already_in_delegation_seed"] is True


def test_history_dedupe_skips_unchanged_evidence_hash(tmp_path: Path) -> None:
    cand = _eligible_candidate(candidate_id="hist_001")
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap1 = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    eh = snap1["rows"][0]["evidence_hash"]
    # Pre-seed history with the same (cid, evidence_hash) pair.
    history_p = tmp_path / "logs" / "development_intake_promotion" / "history.jsonl"
    history_p.parent.mkdir(parents=True, exist_ok=True)
    history_p.write_text(
        json.dumps({"candidate_id": "hist_001", "evidence_hash": eh})
        + "\n",
        encoding="utf-8",
    )
    snap2 = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=history_p,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    row = snap2["rows"][0]
    assert row["duplicate_of_history_entry"] is True
    assert any(
        "duplicate_unchanged_history_entry" in w
        for w in snap2["validation_warnings"]
    )


def test_duplicate_candidate_id_in_cycle_dedupes(tmp_path: Path) -> None:
    cand = _eligible_candidate(candidate_id="dup_cycle_001")
    intake = _write_intake_artifact(
        tmp_path, _intake_artifact(candidates=[dict(cand), dict(cand)])
    )
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert snap["counts"]["total"] == 1
    assert any(
        "duplicate_candidate_id_in_cycle" in w
        for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    cand = _eligible_candidate()
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    seed = _write_seed(tmp_path, "seed.jsonl", [])
    delegation = _write_seed(tmp_path, "delegation_seed.jsonl", [])
    history = _empty_history(tmp_path)
    snap_a = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=seed,
        delegation_seed_path=delegation,
        history_path=history,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_b = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=seed,
        delegation_seed_path=delegation,
        history_path=history,
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    a_bytes = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    b_bytes = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert a_bytes == b_bytes


def test_rows_sort_deterministically(tmp_path: Path) -> None:
    cands = [
        _eligible_candidate(candidate_id="z_03", source_kind="phase_prompt"),
        _eligible_candidate(candidate_id="a_01", source_kind="phase_prompt"),
        _eligible_candidate(candidate_id="m_02", source_kind="operating_manual"),
    ]
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=cands))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    keys = [(r["source_kind"], r["candidate_id"]) for r in snap["rows"]]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_by_decision_state(tmp_path: Path) -> None:
    cands = [
        _eligible_candidate(candidate_id="a"),
        _eligible_candidate(candidate_id="b"),
    ]
    cands[1]["intake_status"] = "human_needed"
    cands[1]["human_needed"] = True
    cands[1]["human_needed_reason"] = "architecture_crossroads"
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=cands))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    counts = snap["counts"]
    assert counts["total"] == 2
    assert counts["eligible"] == 1
    assert counts["human_needed"] == 1
    assert counts["by_decision_state"]["eligible"] == 1
    assert counts["by_decision_state"]["human_needed"] == 1
    assert sum(counts["by_decision_state"].values()) == 2
    # N1 severities present.
    assert sum(counts["by_notification_event_severity"].values()) == 2


# ---------------------------------------------------------------------------
# N1 integration
# ---------------------------------------------------------------------------


def test_uses_notification_event_route_for_only(tmp_path: Path) -> None:
    """Sanity check: the row's notification_event_severity must be a
    valid N1 severity, and the kind must be a valid N1 kind."""
    cand = _eligible_candidate()
    intake = _write_intake_artifact(tmp_path, _intake_artifact(candidates=[cand]))
    snap = dip.collect_snapshot(
        intake_artifact_path=intake,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    row = snap["rows"][0]
    assert row["notification_event_kind"] in ne.EVENT_KINDS
    assert row["notification_event_severity"] in ne.EVENT_SEVERITIES


# ---------------------------------------------------------------------------
# Intake artefact absent / unparseable
# ---------------------------------------------------------------------------


def test_intake_artifact_absent_yields_warning(tmp_path: Path) -> None:
    missing = (
        tmp_path
        / "logs"
        / "development_roadmap_intake"
        / "latest.json"
    )
    snap = dip.collect_snapshot(
        intake_artifact_path=missing,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["intake_artifact_available"] is False
    assert "intake_artifact_absent" in snap["validation_warnings"]
    assert snap["rows"] == []


def test_unparseable_intake_artifact_yields_warning(tmp_path: Path) -> None:
    bad = (
        tmp_path
        / "logs"
        / "development_roadmap_intake"
        / "latest.json"
    )
    bad.parent.mkdir(parents=True)
    # Write parseable JSON but with a wrong shape.
    bad.write_text(json.dumps({"candidates": "not a list"}), encoding="utf-8")
    snap = dip.collect_snapshot(
        intake_artifact_path=bad,
        seed_path=_write_seed(tmp_path, "seed.jsonl", []),
        delegation_seed_path=_write_seed(
            tmp_path, "delegation_seed.jsonl", []
        ),
        history_path=_empty_history(tmp_path),
    )
    assert "intake_artifact_unparseable" in snap["validation_warnings"]
    assert snap["rows"] == []


# ---------------------------------------------------------------------------
# Seed files are read-only
# ---------------------------------------------------------------------------


def test_module_does_not_open_seed_jsonl_for_writing() -> None:
    """The module source must not contain a write/append-mode open
    against either operator-authored seed file."""
    src = (Path(dip.__file__)).read_text(encoding="utf-8")
    forbidden_substrings = (
        "seed.jsonl\", \"w",
        "seed.jsonl', 'w",
        "seed.jsonl\", \"a",
        "seed.jsonl', 'a",
        "delegation_seed.jsonl\", \"w",
        "delegation_seed.jsonl', 'w",
        "delegation_seed.jsonl\", \"a",
        "delegation_seed.jsonl', 'a",
        "SEED_PATH.write_text",
        "DELEGATION_SEED_PATH.write_text",
        "SEED_PATH.open(\"w",
        "DELEGATION_SEED_PATH.open(\"w",
    )
    for s in forbidden_substrings:
        assert s not in src, s


def test_module_does_not_create_generated_seed_jsonl() -> None:
    src = (Path(dip.__file__)).read_text(encoding="utf-8")
    assert "generated_seed.jsonl" not in src


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dip.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
        "shell=True",
    ):
        assert forbidden not in src, forbidden


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_imports_only_allowed_dependencies() -> None:
    names = _imported_module_names()
    allowed = {
        "__future__",
        "argparse",
        "datetime",
        "hashlib",
        "json",
        "os",
        "sys",
        "tempfile",
        "pathlib",
        "typing",
        "reporting",
        "reporting.development_roadmap_intake",
        "reporting.execution_authority",
        "reporting.notification_event",
    }
    extra = names - allowed
    assert extra == set(), f"unexpected imports: {extra}"


def test_module_imports_cleanly() -> None:
    importlib.reload(dip)
    assert callable(dip.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(dip)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "development_intake_promotion.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_seed_writes() -> None:
    text = _doc_text().lower()
    assert "no automatic queue write" in text or "no automatic queue promotion" in text
    assert "operator-authored" in text
    assert "seed.jsonl" in text


def test_doc_states_a16b_is_operator_gated() -> None:
    text = _doc_text().lower()
    assert "a16b" in text
    assert "not implemented" in text
    assert "operator" in text


def test_doc_states_step5_remains_blocked() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    import re

    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window, (
            f"'Level 6' at offset {m.start()} lacks "
            f"'permanently disabled' qualifier"
        )
