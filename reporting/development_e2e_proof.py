"""A13 — Autonomous Development End-to-End Proof Harness.

Pure, deterministic, stdlib-only orchestrator that exercises the
full ADE lifecycle on synthetic, no-op fixtures and emits a proof
artifact. Proves that the Autonomous Development Engine can run
the full loop:

    roadmap pickup
    -> agent-role refinement / decomposition
    -> prioritisation
    -> execution readiness
    -> bounded execution / simulation
    -> validation
    -> release-gate / report-out
    -> operator-facing digest

ADE core remains pure. The harness:

* never invokes ``subprocess``, ``gh``, or ``git``,
* never opens a network connection,
* never modifies any production research artifact,
* never touches protected surfaces,
* never starts a real branch / PR / commit,
* never mutates ``seed.jsonl`` / ``bugfix_seed.jsonl`` /
  ``delegation_seed.jsonl`` on disk,
* writes only to ``logs/development_e2e_proof/latest.json`` and a
  scratch directory the caller passes in (defaults to a tmp dir),
* uses synthetic fixtures the harness constructs in-memory or in
  a tmp dir.

Execution is simulated: the proof's "bounded execution" step
records that a docs-only target *would* be modified — it does not
modify it. This is the safest possible target for a
domain-neutral ADE proof.

CLI::

    python -m reporting.development_e2e_proof
    python -m reporting.development_e2e_proof --no-write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_operational_digest as dod
from reporting import development_release_gate as drg
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A13"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_e2e_proof"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_e2e_proof/latest.json"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: 8 lifecycle steps. Closed; ordered.
FLOW_STEPS: Final[tuple[str, ...]] = (
    "roadmap_pickup",
    "agent_refinement",
    "prioritisation",
    "execution_readiness",
    "bounded_execution_or_simulation",
    "validation",
    "release_gate",
    "digest_report_out",
)

#: 4 step-status values. Closed.
STEP_STATUSES: Final[tuple[str, ...]] = (
    "passed",
    "failed",
    "blocked",
    "not_evaluated",
)

#: 3 final proof states. Closed.
PROOF_STATUSES: Final[tuple[str, ...]] = ("passed", "failed", "blocked")

#: Closed blocker reasons. None of these is a hidden authority
#: signal; each maps directly to an observable property of the
#: lifecycle.
BLOCKER_REASONS: Final[tuple[str, ...]] = (
    "no_delegation_entry_parsed",
    "agent_role_invalid",
    "missing_acceptance_criteria",
    "queue_did_not_route_item",
    "execution_readiness_unresolved",
    "simulation_target_protected",
    "validation_evidence_missing",
    "release_gate_no_go",
    "digest_did_not_reflect_item",
    "qre_coupling_detected",
    "protected_path_violation",
    "none",
)

#: A safe synthetic target path used for the bounded-execution
#: simulation. ``docs/operator/...`` is doc_non_policy, LOW risk,
#: AUTO_ALLOWED. The harness records that it *would* modify this
#: path; it does not actually modify it.
SIMULATION_TARGET_PATH: Final[str] = "docs/operator/ade_e2e_proof_target.md"

#: The synthetic delegation marker the proof writes into a fixture
#: roadmap doc inside the scratch directory. The marker is well-formed
#: per the A11 grammar and yields one delegation entry on parse.
SYNTHETIC_DELEGATION_ID: Final[str] = "ade_e2e_synthetic_001"
SYNTHETIC_TITLE: Final[str] = "ADE E2E proof: doc-only no-op target"

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _proof_id_from(snapshot: dict[str, Any], ts: str) -> str:
    h = hashlib.sha256()
    h.update(ts.encode("utf-8"))
    for step in snapshot.get("flow_steps", []):
        h.update(step.get("step", "").encode("utf-8"))
        h.update(step.get("status", "").encode("utf-8"))
    return "e2e_" + h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Fixture construction (in-memory / scratch directory)
# ---------------------------------------------------------------------------


def _build_synthetic_canonical_roadmap_text() -> str:
    """Construct a canonical-roadmap-shaped fixture body containing
    one valid A11 delegation marker, plus prose, headings, and bullet
    lists that must NOT generate delegation entries (false-positive
    guard)."""
    return (
        "# Synthetic Autonomous Development Track\n"
        "\n"
        "## §A13 fixture\n"
        "\n"
        "This block is plain prose and must not become a delegation.\n"
        "\n"
        "- bullet one\n"
        "- bullet two\n"
        "\n"
        "<!-- ade_delegation\n"
        f"delegation_id: {SYNTHETIC_DELEGATION_ID}\n"
        f"title: {SYNTHETIC_TITLE}\n"
        "category: docs\n"
        "required_agent_role: implementation_agent\n"
        "risk_level: LOW\n"
        "human_needed: false\n"
        "human_needed_reason: none\n"
        "acceptance_criteria:\n"
        "  - synthetic doc target file would be created\n"
        "  - synthetic validation evidence would be clean\n"
        "  - release gate would emit a verdict\n"
        "-->\n"
        "\n"
        "More prose that should not be parsed.\n"
    )


def _build_synthetic_queue_seed_item() -> dict[str, Any]:
    """The A8 queue seed item routed by the proof. Targets a safe
    docs path (AUTO_ALLOWED + LOW risk + non-protected)."""
    return {
        "title": SYNTHETIC_TITLE,
        "source_document": SIMULATION_TARGET_PATH,
        "source_section_or_anchor": "ade_e2e_synthetic_001",
        "roadmap_track": "sidecar_seed",
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
        "acceptance_criteria": [
            "synthetic doc target file would be created",
            "synthetic validation evidence would be clean",
            "release gate would emit a verdict",
        ],
        "validation_requirements": ["operator confirms doc preview"],
        "notes": "ADE E2E proof synthetic item — no real change.",
    }


def _build_synthetic_release_evidence() -> dict[str, Any]:
    """A clean evidence-input contract for A9. All required keys
    present and clean — the gate should produce a `go` or
    `go_with_followups` verdict."""
    return {
        "schema_version": "1.0",
        "evidence": {
            "ci_status": {"present": True, "value": "green"},
            "smoke_status": {"present": True, "value": "passed"},
            "governance_lint_status": {"present": True, "value": "ok"},
            "frozen_hash_status": {"present": True, "value": "stable"},
            "no_touch_path_delta_status": {"present": True, "value": "clean"},
            "queue_cross_reference_status": {
                "present": True,
                "value": "consistent",
            },
        },
    }


def _build_synthetic_failure_summary() -> dict[str, Any]:
    """A bounded synthetic failure summary for A10. Produces one
    bounded_in_repo bugfix candidate against the simulation target."""
    return {
        "schema_version": "1.0",
        "failures": [
            {
                "failure_class": "lint",
                "target_path": SIMULATION_TARGET_PATH,
                "message_digest": "synthetic_e2e_001",
                "severity": "low",
                "occurrence_count": 1,
                "first_seen_utc": "2026-05-08T00:00:00Z",
                "last_seen_utc": "2026-05-08T00:00:00Z",
                "detail": "ADE E2E synthetic lint warning",
            }
        ],
    }


def _build_scratch_fixture(scratch: Path) -> dict[str, Path]:
    """Lay out a synthetic ADE artifact set inside a scratch
    directory. Nothing under this scratch is committed; nothing
    under it is a real ADE artifact."""
    logs = scratch / "logs"
    docs = scratch / "docs"
    (logs / "development_work_queue").mkdir(parents=True, exist_ok=True)
    (logs / "development_release_gate").mkdir(parents=True, exist_ok=True)
    (logs / "development_bugfix_loop").mkdir(parents=True, exist_ok=True)
    (logs / "development_delegation").mkdir(parents=True, exist_ok=True)
    (logs / "release_gate_input").mkdir(parents=True, exist_ok=True)
    (logs / "bugfix_loop_input").mkdir(parents=True, exist_ok=True)
    (docs / "roadmap").mkdir(parents=True, exist_ok=True)
    (docs / "development_work_queue").mkdir(parents=True, exist_ok=True)
    return {
        "scratch": scratch,
        "logs": logs,
        "docs": docs,
        "queue_artifact": logs / "development_work_queue" / "latest.json",
        "release_gate_artifact": logs / "development_release_gate" / "latest.json",
        "bugfix_loop_artifact": logs / "development_bugfix_loop" / "latest.json",
        "delegation_artifact": logs / "development_delegation" / "latest.json",
        "release_evidence": logs / "release_gate_input" / "latest.json",
        "failure_summary": logs / "bugfix_loop_input" / "latest.json",
        "queue_seed": docs / "development_work_queue" / "seed.jsonl",
        "delegation_seed": (
            docs / "development_work_queue" / "delegation_seed.jsonl"
        ),
        "canonical_roadmap_doc": (
            docs / "roadmap" / "autonomous_development.txt"
        ),
        "canonical_qre_roadmap": docs / "roadmap" / "Roadmap v6.md",
    }


# ---------------------------------------------------------------------------
# Step builders
# ---------------------------------------------------------------------------


def _step(
    name: str,
    *,
    status: str,
    blocker_reason: str = "none",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in STEP_STATUSES:
        raise ValueError(f"invalid step status: {status}")
    if blocker_reason not in BLOCKER_REASONS:
        raise ValueError(f"invalid blocker reason: {blocker_reason}")
    return {
        "step": name,
        "status": status,
        "blocker_reason": blocker_reason,
        "evidence": evidence or {},
    }


# ---------------------------------------------------------------------------
# Lifecycle execution (all read-only / synthetic)
# ---------------------------------------------------------------------------


def _run_lifecycle(scratch_paths: dict[str, Path]) -> dict[str, Any]:
    """Run the eight lifecycle steps on synthetic fixtures. Returns
    a dict with the step results plus closed-list violation counters
    and a summary."""
    flow_steps: list[dict[str, Any]] = []
    missing_capabilities: list[str] = []
    protected_path_violations: list[str] = []
    qre_coupling_violations: list[str] = []
    human_needed_items = 0

    # Step 1 — roadmap_pickup -----------------------------------------
    scratch_paths["canonical_roadmap_doc"].write_text(
        _build_synthetic_canonical_roadmap_text(), encoding="utf-8"
    )
    scratch_paths["canonical_qre_roadmap"].write_text(
        "# QRE roadmap fixture (intentionally empty)\n", encoding="utf-8"
    )
    scratch_paths["delegation_seed"].write_text("", encoding="utf-8")

    delegation_snapshot = ddl.collect_snapshot(
        roadmap_paths=ddl.CANONICAL_ROADMAP_PATHS,
        sidecar_seed_path=scratch_paths["delegation_seed"],
        repo_root=scratch_paths["scratch"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    delegation_entry_count = len(delegation_snapshot.get("entries") or [])
    if delegation_entry_count == 0:
        flow_steps.append(
            _step(
                "roadmap_pickup",
                status="failed",
                blocker_reason="no_delegation_entry_parsed",
                evidence={"entries": 0},
            )
        )
        missing_capabilities.append("roadmap_pickup")
    else:
        flow_steps.append(
            _step(
                "roadmap_pickup",
                status="passed",
                evidence={
                    "entries": delegation_entry_count,
                    "delegation_ids": [
                        e["delegation_id"]
                        for e in delegation_snapshot["entries"]
                    ],
                },
            )
        )

    # Step 2 — agent_refinement ---------------------------------------
    if delegation_entry_count == 0:
        flow_steps.append(
            _step(
                "agent_refinement",
                status="not_evaluated",
                blocker_reason="no_delegation_entry_parsed",
            )
        )
    else:
        entry = delegation_snapshot["entries"][0]
        ac_present = bool(entry.get("acceptance_criteria"))
        role_valid = entry.get("required_agent_role") in dwq.AGENT_ROLES
        if not ac_present:
            flow_steps.append(
                _step(
                    "agent_refinement",
                    status="failed",
                    blocker_reason="missing_acceptance_criteria",
                    evidence={"delegation_id": entry["delegation_id"]},
                )
            )
            missing_capabilities.append("agent_refinement_acceptance_criteria")
        elif not role_valid:
            flow_steps.append(
                _step(
                    "agent_refinement",
                    status="failed",
                    blocker_reason="agent_role_invalid",
                    evidence={"role": entry.get("required_agent_role")},
                )
            )
            missing_capabilities.append("agent_refinement_role")
        else:
            flow_steps.append(
                _step(
                    "agent_refinement",
                    status="passed",
                    evidence={
                        "delegation_id": entry["delegation_id"],
                        "required_agent_role": entry["required_agent_role"],
                        "human_needed": entry["human_needed"],
                        "execution_authority_decision": entry[
                            "execution_authority_decision"
                        ],
                    },
                )
            )

    # Step 3 — prioritisation -----------------------------------------
    queue_seed_item = _build_synthetic_queue_seed_item()
    scratch_paths["queue_seed"].write_text(
        json.dumps(queue_seed_item) + "\n", encoding="utf-8"
    )
    queue_snapshot = dwq.collect_snapshot(
        seed_path=scratch_paths["queue_seed"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    if queue_snapshot["counts"]["total"] != 1:
        flow_steps.append(
            _step(
                "prioritisation",
                status="failed",
                blocker_reason="queue_did_not_route_item",
                evidence={"queue_total": queue_snapshot["counts"]["total"]},
            )
        )
        missing_capabilities.append("prioritisation")
    else:
        item = queue_snapshot["items"][0]
        flow_steps.append(
            _step(
                "prioritisation",
                status="passed",
                evidence={
                    "item_id": item["item_id"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "execution_authority": item["execution_authority"],
                },
            )
        )

    # Persist queue artifact for downstream steps.
    scratch_paths["queue_artifact"].write_text(
        json.dumps(queue_snapshot), encoding="utf-8"
    )

    # Step 4 — execution_readiness ------------------------------------
    if queue_snapshot["counts"]["total"] != 1:
        flow_steps.append(
            _step(
                "execution_readiness",
                status="not_evaluated",
                blocker_reason="queue_did_not_route_item",
            )
        )
    else:
        ready = queue_snapshot["counts"]["ready_for_autonomous_action"]
        requiring_human = queue_snapshot["counts"]["requiring_human_operator"]
        item = queue_snapshot["items"][0]
        protected = bool(item.get("protected_surface"))
        if protected:
            flow_steps.append(
                _step(
                    "execution_readiness",
                    status="blocked",
                    blocker_reason="simulation_target_protected",
                    evidence={"item_id": item["item_id"]},
                )
            )
            protected_path_violations.append(item["source_document"])
        else:
            flow_steps.append(
                _step(
                    "execution_readiness",
                    status="passed",
                    evidence={
                        "ready_for_autonomous_action": ready,
                        "requiring_human_operator": requiring_human,
                        "execution_authority": item["execution_authority"],
                    },
                )
            )
            if requiring_human > 0:
                human_needed_items = requiring_human

    # Step 5 — bounded_execution_or_simulation ------------------------
    # Pure simulation: record a "would_modify_target_path" outcome.
    # Re-classify via execution_authority to be sure the target is
    # AUTO_ALLOWED before claiming simulation success.
    sim_decision = ea.classify(
        action_type="file_edit",
        target_path=SIMULATION_TARGET_PATH,
        risk_class=ea.RISK_LOW,
    )
    if sim_decision.decision == ea.DECISION_AUTO_ALLOWED:
        flow_steps.append(
            _step(
                "bounded_execution_or_simulation",
                status="passed",
                evidence={
                    "simulation_kind": "no_op_dry_run",
                    "would_modify_target_path": SIMULATION_TARGET_PATH,
                    "actual_modification": False,
                    "authority_decision": sim_decision.decision,
                },
            )
        )
    else:
        flow_steps.append(
            _step(
                "bounded_execution_or_simulation",
                status="blocked",
                blocker_reason="simulation_target_protected",
                evidence={
                    "would_modify_target_path": SIMULATION_TARGET_PATH,
                    "authority_decision": sim_decision.decision,
                },
            )
        )
        protected_path_violations.append(SIMULATION_TARGET_PATH)

    # Step 6 — validation ---------------------------------------------
    failure_summary = _build_synthetic_failure_summary()
    scratch_paths["failure_summary"].write_text(
        json.dumps(failure_summary), encoding="utf-8"
    )
    bugfix_snapshot = dbl.collect_snapshot(
        failure_input_path=scratch_paths["failure_summary"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    scratch_paths["bugfix_loop_artifact"].write_text(
        json.dumps(bugfix_snapshot), encoding="utf-8"
    )
    if bugfix_snapshot["counts"]["total"] != 1:
        flow_steps.append(
            _step(
                "validation",
                status="failed",
                blocker_reason="validation_evidence_missing",
                evidence={"bugfix_total": bugfix_snapshot["counts"]["total"]},
            )
        )
        missing_capabilities.append("validation")
    else:
        flow_steps.append(
            _step(
                "validation",
                status="passed",
                evidence={
                    "bugfix_candidate_id": bugfix_snapshot["candidates"][0][
                        "candidate_id"
                    ],
                    "bugfix_scope": bugfix_snapshot["candidates"][0][
                        "bugfix_scope"
                    ],
                    "human_needed": bugfix_snapshot["candidates"][0][
                        "human_needed"
                    ],
                },
            )
        )

    # Step 7 — release_gate -------------------------------------------
    # Promote the queue item into "validation_needed" + "release"
    # category so the release gate evaluates it.
    queue_seed_item_release = dict(queue_seed_item)
    queue_seed_item_release["category"] = "release"
    queue_seed_item_release["status"] = "validation_needed"
    scratch_paths["queue_seed"].write_text(
        json.dumps(queue_seed_item_release) + "\n", encoding="utf-8"
    )
    queue_snapshot_release = dwq.collect_snapshot(
        seed_path=scratch_paths["queue_seed"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    scratch_paths["queue_artifact"].write_text(
        json.dumps(queue_snapshot_release), encoding="utf-8"
    )
    scratch_paths["release_evidence"].write_text(
        json.dumps(_build_synthetic_release_evidence()), encoding="utf-8"
    )
    release_snapshot = drg.collect_snapshot(
        queue_artifact_path=scratch_paths["queue_artifact"],
        evidence_input_path=scratch_paths["release_evidence"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    scratch_paths["release_gate_artifact"].write_text(
        json.dumps(release_snapshot), encoding="utf-8"
    )
    if release_snapshot["counts"]["total"] == 0:
        flow_steps.append(
            _step(
                "release_gate",
                status="failed",
                blocker_reason="release_gate_no_go",
                evidence={"release_total": 0},
            )
        )
        missing_capabilities.append("release_gate")
    else:
        verdicts = [r["verdict"] for r in release_snapshot["rows"]]
        good = {drg.VERDICT_GO, drg.VERDICT_GO_WITH_FOLLOWUPS}
        if any(v in good for v in verdicts):
            flow_steps.append(
                _step(
                    "release_gate",
                    status="passed",
                    evidence={
                        "verdict": verdicts[0],
                        "verdict_reason": release_snapshot["rows"][0][
                            "verdict_reason"
                        ],
                    },
                )
            )
        else:
            flow_steps.append(
                _step(
                    "release_gate",
                    status="failed",
                    blocker_reason="release_gate_no_go",
                    evidence={"verdicts": list(verdicts)},
                )
            )
            missing_capabilities.append("release_gate_go")

    # Persist a delegation artifact for the digest step (use the
    # synthetic delegation snapshot already produced above).
    scratch_paths["delegation_artifact"].write_text(
        json.dumps(delegation_snapshot), encoding="utf-8"
    )

    # Step 8 — digest_report_out --------------------------------------
    digest = dod.collect_snapshot(
        queue_path=scratch_paths["queue_artifact"],
        release_gate_path=scratch_paths["release_gate_artifact"],
        bugfix_loop_path=scratch_paths["bugfix_loop_artifact"],
        delegation_path=scratch_paths["delegation_artifact"],
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    if digest["presence_count"] != 4:
        flow_steps.append(
            _step(
                "digest_report_out",
                status="failed",
                blocker_reason="digest_did_not_reflect_item",
                evidence={"presence_count": digest["presence_count"]},
            )
        )
        missing_capabilities.append("digest_report_out")
    else:
        flow_steps.append(
            _step(
                "digest_report_out",
                status="passed",
                evidence={
                    "presence_count": digest["presence_count"],
                    "operator_action_count": len(
                        digest["operator_action_list"]
                    ),
                    "step5_ready": digest["step5_readiness"]["step5_ready"],
                },
            )
        )

    # Loose-coupling self-check: every ADE module emitted in the
    # flow steps used only ADE module versions whose strings do not
    # mention QRE/IR.
    for snapshot in (
        delegation_snapshot,
        queue_snapshot_release,
        release_snapshot,
        bugfix_snapshot,
        digest,
    ):
        mv = snapshot.get("module_version") or ""
        if "intelligent_routing" in str(mv):
            qre_coupling_violations.append(str(mv))

    return {
        "flow_steps": flow_steps,
        "missing_capabilities": sorted(set(missing_capabilities)),
        "protected_path_violations": sorted(set(protected_path_violations)),
        "qre_coupling_violations": sorted(set(qre_coupling_violations)),
        "human_needed_items": human_needed_items,
        "digest": {
            "step5_ready": digest["step5_readiness"]["step5_ready"],
            "step5_design_planning_allowed": digest["step5_readiness"][
                "step5_design_planning_allowed"
            ],
            "step5_implementation_allowed": digest["step5_readiness"][
                "step5_implementation_allowed"
            ],
        },
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _summarize_proof_status(
    flow_steps: list[dict[str, Any]],
    *,
    protected_path_violations: list[str],
    qre_coupling_violations: list[str],
) -> str:
    if protected_path_violations or qre_coupling_violations:
        return "blocked"
    has_failed = any(s["status"] == "failed" for s in flow_steps)
    has_blocked = any(s["status"] == "blocked" for s in flow_steps)
    if has_blocked:
        return "blocked"
    if has_failed:
        return "failed"
    return "passed"


def _final_operator_summary(
    proof_status: str,
    autonomous_development_possible: bool,
    digest: dict[str, Any],
) -> str:
    if proof_status == "passed" and autonomous_development_possible:
        return (
            "ADE end-to-end autonomous development loop is possible in "
            "proof-harness mode. Step 5 design planning is allowed; Step 5 "
            "implementation requires separate operator authorisation."
        )
    if proof_status == "blocked":
        return (
            "ADE end-to-end proof is BLOCKED by a hard safety boundary. "
            "Inspect protected_path_violations / qre_coupling_violations."
        )
    return (
        "ADE end-to-end proof FAILED. Inspect missing_capabilities and "
        "the failed flow_steps for the next bounded ADE phase."
    )


def collect_snapshot(
    *,
    scratch_dir: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Run the full ADE lifecycle on synthetic fixtures and return
    the proof snapshot.

    Args:
        scratch_dir: directory the harness will use as its
            synthetic ADE root. The harness writes only inside this
            directory (and inside ``logs/development_e2e_proof/``
            when ``write_outputs`` is invoked). Defaults to a fresh
            tmp directory created with ``tempfile.mkdtemp``.
        generated_at_utc: override the wrapper's report timestamp.
    """
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()
    own_scratch = scratch_dir is None
    scratch = (
        scratch_dir
        if scratch_dir is not None
        else Path(tempfile.mkdtemp(prefix="ade_e2e_proof_"))
    )
    try:
        scratch_paths = _build_scratch_fixture(scratch)
        outcome = _run_lifecycle(scratch_paths)
    finally:
        # Tests that supply their own scratch dir manage cleanup.
        # When the harness owns the dir, leave it alone — the caller
        # may want to inspect it. tempfile.mkdtemp creates under the
        # OS temp tree, which is auto-cleaned by the OS.
        if own_scratch:
            pass

    proof_status = _summarize_proof_status(
        outcome["flow_steps"],
        protected_path_violations=outcome["protected_path_violations"],
        qre_coupling_violations=outcome["qre_coupling_violations"],
    )
    autonomous_development_possible = (
        proof_status == "passed"
        and not outcome["protected_path_violations"]
        and not outcome["qre_coupling_violations"]
    )

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_e2e_proof",
        "generated_at_utc": ts,
        "proof_status": proof_status,
        "autonomous_development_possible": autonomous_development_possible,
        "step5_design_planning_allowed": outcome["digest"][
            "step5_design_planning_allowed"
        ],
        "step5_implementation_allowed": outcome["digest"][
            "step5_implementation_allowed"
        ],
        "flow_steps": outcome["flow_steps"],
        "missing_capabilities": outcome["missing_capabilities"],
        "protected_path_violations": outcome["protected_path_violations"],
        "qre_coupling_violations": outcome["qre_coupling_violations"],
        "human_needed_items": outcome["human_needed_items"],
        "vocabularies": {
            "flow_steps": list(FLOW_STEPS),
            "step_statuses": list(STEP_STATUSES),
            "proof_statuses": list(PROOF_STATUSES),
            "blocker_reasons": list(BLOCKER_REASONS),
        },
        "scratch_dir": str(scratch),
        "discipline_invariants": {
            "actually_modifies_target": False,
            "creates_real_branches": False,
            "opens_real_prs": False,
            "mutates_production_artifacts": False,
            "uses_subprocess_or_network": False,
            "operator_step5_authorisation_required": True,
        },
    }
    snapshot["proof_id"] = _proof_id_from(snapshot, ts)
    snapshot["final_operator_summary"] = _final_operator_summary(
        proof_status,
        autonomous_development_possible,
        outcome["digest"],
    )
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_e2e_proof._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_e2e_proof.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_e2e_proof",
        description=(
            "Pure ADE end-to-end proof harness. Runs the full "
            "autonomous development lifecycle on synthetic, no-op "
            "fixtures and emits a proof artifact. Mutates nothing "
            "real; never opens a network connection."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_e2e_proof/latest.json "
            "(stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
