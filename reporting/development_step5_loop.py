"""Autonomous Implementation Loop — Step 5.0 (dry-run, planner-only).

Anchored by:

* ``docs/adr/ADR-017-step5-autonomous-implementation-loop.md`` (Accepted)
* ``docs/governance/step5_design.md`` §13 (first slice proposal)
* ``docs/roadmap/autonomous_development.txt`` §A14
* ``tests/unit/test_development_step5_loop.py`` (contract pins from
  PR #153 + the runtime pins added alongside this module)

What this module does
---------------------

1. Reads (atomically, never mutating) the three upstream ADE
   artefacts: A11 delegation, A10 bugfix loop, A8 work queue.
2. Selects at most one item per cycle, by deterministic ordering:
   delegation_id ASC, then bugfix candidate_id ASC, then queue
   item_id ASC.
3. Classifies the item via the upstream-recorded execution-authority
   decision (``AUTO_ALLOWED`` / ``NEEDS_HUMAN`` / ``PERMANENTLY_DENIED``)
   and halts loudly on anything other than ``AUTO_ALLOWED``.
4. Builds a deterministic ``step5_plan.v1.json`` artefact at
   ``logs/step5_plan/<cycle_id>.json`` with the closed schema declared
   in step5_design.md §8.3.
5. Updates ``logs/step5_plan/history.jsonl`` (bounded 90-entry rolling
   window; atomic rewrite; mirrors the A12 history pattern).
6. Writes ``logs/step5_loop/latest.json`` snapshot.
7. Records one audit-ledger event with ``autonomy_level_claimed=0``
   via ``reporting.agent_audit.append_event(...)``.
8. Exits 0 even when the cycle halts on an authority deny — Step 5.0
   is diagnostic, not gating.

Hard guarantees (pinned by tests)
---------------------------------

* ``step5_implementation_allowed = False`` (literal constant).
* ``STEP5_ENABLED_SUBSTAGE = "none"`` (closed-vocab default).
* No ``git`` / ``gh`` / ``subprocess`` / ``socket`` / network calls
  from this module.
* No imports of QRE-internal symbols (``research``,
  ``dashboard.dashboard``, ``automation``, ``broker``, ``agent.risk``,
  ``agent.execution``, ``reporting.intelligent_routing``).
* ``_atomic_write_json`` refuses every path outside
  ``logs/step5_*/...``.
* Step 5 implementation remains BLOCKED. Autonomy-ladder Level 6
  remains permanently disabled per ADR-015 §Doctrine 1.

CLI
---

::

    python -m reporting.development_step5_loop --dry-run
    python -m reporting.development_step5_loop --dry-run --no-write
    python -m reporting.development_step5_loop --dry-run --indent 0

Exits 0 even on diagnostic halt cycles.
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

from reporting import agent_audit as _audit
from reporting import approval_policy as _ap  # noqa: F401  (re-asserted contract)
from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea  # noqa: F401  (re-asserted contract)


# ---------------------------------------------------------------------------
# Schema / version anchors
# ---------------------------------------------------------------------------

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A14"
REPORT_KIND: Final[str] = "step5_plan"
LOOP_REPORT_KIND: Final[str] = "step5_loop"


# ---------------------------------------------------------------------------
# Closed vocabularies (pinned by tests; widening requires a code change
# pinned by an updated test).
# ---------------------------------------------------------------------------

#: Step 5 sub-stage closed vocabulary. Default ``"none"``; the operator
#: flips the cap by amending this module via a governance-bootstrap PR
#: — never at runtime.
STEP5_SUBSTAGES: Final[tuple[str, ...]] = ("none", "5.0", "5.1", "5.2")

#: The active sub-stage cap. Default-deny: ``"none"`` means the loop
#: produces only diagnostic artefacts and never escalates.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Closed halt-reason vocabulary. Adding an entry requires a matching
#: test update; the closed cardinality is pinned.
STEP5_HALT_REASONS: Final[tuple[str, ...]] = (
    "needs_human",
    "permanently_denied",
    "out_of_allowlist",
    "no_eligible_item",
    "ok",
)

#: Closed outcome-kind vocabulary.
STEP5_OUTCOME_KINDS: Final[tuple[str, ...]] = (
    "halt_needs_human",
    "halt_permanently_denied",
    "halt_out_of_allowlist",
    "no_op_no_eligible_item",
    "plan_emitted",
)

#: Closed source-kind vocabulary. Items can only originate from these
#: three upstream artefacts.
STEP5_SOURCE_KINDS: Final[tuple[str, ...]] = (
    "delegation",
    "bugfix",
    "queue",
)

#: Bounded history window. Mirrors A12's pattern.
MAX_HISTORY_ENTRIES: Final[int] = 90

#: Hard-pinned literal: Step 5 implementation is NOT allowed beyond
#: the dry-run / planner-only Step 5.0 surface. Flipping this constant
#: requires a code change pinned by a test update AND an ADR-015
#: amendment AND a fresh release-gate report.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Repo-relative paths
# ---------------------------------------------------------------------------

_THIS_FILE: Final[Path] = Path(__file__).resolve()
_REPO_ROOT: Final[Path] = _THIS_FILE.parent.parent

ARTIFACT_DIR: Final[Path] = _REPO_ROOT / "logs" / "step5_loop"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"

PLAN_DIR: Final[Path] = _REPO_ROOT / "logs" / "step5_plan"
HISTORY_PATH: Final[Path] = PLAN_DIR / "history.jsonl"

#: Step 5.0 write allowlist (string-prefix form). Any atomic-write
#: target whose POSIX path does not contain one of these prefixes is
#: refused with ``ValueError``.
_STEP5_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/step5_loop/",
    "logs/step5_plan/",
)


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

#: Pinned by tests. The artefact's ``discipline_invariants`` block
#: must contain exactly these keys with these values for Step 5.0.
_DISCIPLINE_INVARIANTS: Final[dict[str, bool]] = {
    "actually_modifies_target": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "mergeable_by_agent": False,
    "deployable_by_agent": False,
    "mutates_qre_artifacts": False,
    "mutates_frozen_contracts": False,
    "mutates_protected_paths": False,
    "uses_subprocess_or_network": False,
    "operator_step5_authorisation_required": True,
}


# ---------------------------------------------------------------------------
# B2.1 — Step 5.1 adapter (default-disabled, additive schema)
# ---------------------------------------------------------------------------

#: v3.15.16.A15.B2.1 — Default-disabled "would do" preview for a
#: hypothetical Step 5.1 cycle. Every Boolean field is pinned False
#: and ``would_touch_paths`` is empty. The block is emitted into
#: every plan payload as METADATA ONLY; no runtime gate reads it.
#:
#: Flipping any field here requires:
#:   (a) a coordinated source change pinned by updated tests, AND
#:   (b) the Path B / Path C governance amendments documented in
#:       docs/governance/step5_gate_truth_table.md section 6.
#:
#: ``step5_implementation_allowed`` remains ``Final[False]`` and
#: ``STEP5_ENABLED_SUBSTAGE`` remains ``Final["none"]`` regardless
#: of changes to this block — the B2.4a AST pin still holds.
#:
#: This constant declares the closed schema (used by tests).
#: Emitted payloads MUST call ``_fresh_step5_5_1_proposed()`` instead
#: of shallow-copying this constant — see helper below for why.
_STEP5_5_1_PROPOSED_DEFAULT: Final[dict[str, Any]] = {
    "mode": "dry_run_only",
    "would_create_branch": False,
    "would_open_pr": False,
    "would_touch_paths": [],
    "would_run_targeted_tests": False,
    "would_emit_release_gate_evidence": False,
}


def _fresh_step5_5_1_proposed() -> dict[str, Any]:
    """Return a fresh Step 5.1 adapter default block per payload.

    ``would_touch_paths`` must be a fresh empty list per payload —
    never a shared object reference with the module-level
    ``_STEP5_5_1_PROPOSED_DEFAULT`` constant. A shallow ``dict(...)``
    copy of the constant would leak the same list across every
    emitted payload, which a future caller could mutate and
    silently affect prior snapshots. This helper rebuilds the
    block from scratch so every emitted ``would_touch_paths`` is
    a fresh, independent ``[]``.
    """
    return {
        "mode": "dry_run_only",
        "would_create_branch": False,
        "would_open_pr": False,
        "would_touch_paths": [],
        "would_run_targeted_tests": False,
        "would_emit_release_gate_evidence": False,
    }


# ---------------------------------------------------------------------------
# B2.2 — Step 5.2 PR dry-run (default-disabled, additive schema)
# ---------------------------------------------------------------------------

#: v3.15.16.A15.B2.2 — Default-disabled "would do" preview for a
#: hypothetical Step 5.2 cycle (the substage that would actually
#: open a code-review request against ``main``). Every Boolean
#: field is pinned False, every string field is empty, and every
#: list field is empty. The block is emitted into every plan
#: payload as METADATA ONLY; no runtime gate reads it.
#:
#: Flipping any field here requires:
#:   (a) a coordinated source change pinned by updated tests, AND
#:   (b) the Path B / Path C governance amendments documented in
#:       docs/governance/step5_gate_truth_table.md section 6.
#:
#: ``step5_implementation_allowed`` remains ``Final[False]`` and
#: ``STEP5_ENABLED_SUBSTAGE`` remains ``Final["none"]`` regardless
#: of changes to this block — the B2.4a AST pin still holds, and
#: the existing ``test_no_runtime_consumer_of_step5_gate_constants``
#: test continues to assert no branch reads the gating constants.
#:
#: This constant declares the closed schema (used by tests).
#: Emitted payloads MUST call ``_fresh_step5_5_2_proposed()`` instead
#: of shallow-copying this constant — see helper below for why.
_STEP5_5_2_PROPOSED_DEFAULT: Final[dict[str, Any]] = {
    "mode": "dry_run_only",
    "would_create_branch": False,
    "would_open_pr": False,
    "would_target_branch": "",
    "would_branch_name": "",
    "would_pr_title": "",
    "would_pr_body": "",
    "would_labels": [],
    "would_reviewers": [],
    "would_assignees": [],
    "would_emit_release_gate_evidence": False,
}


def _fresh_step5_5_2_proposed() -> dict[str, Any]:
    """Return a fresh Step 5.2 PR dry-run default block per payload.

    The three list fields (``would_labels``, ``would_reviewers``,
    ``would_assignees``) must each be a fresh empty list per
    payload — never a shared object reference with the module-level
    ``_STEP5_5_2_PROPOSED_DEFAULT`` constant. A shallow
    ``dict(...)`` copy of the constant would leak the same lists
    across every emitted payload, which a future caller could
    mutate and silently affect prior snapshots. This helper
    rebuilds the block from scratch so every emitted list field
    is a fresh, independent ``[]``. String fields are immutable
    in Python so they cannot exhibit the same aliasing hazard;
    they are pinned to the empty literal regardless.
    """
    return {
        "mode": "dry_run_only",
        "would_create_branch": False,
        "would_open_pr": False,
        "would_target_branch": "",
        "would_branch_name": "",
        "would_pr_title": "",
        "would_pr_body": "",
        "would_labels": [],
        "would_reviewers": [],
        "would_assignees": [],
        "would_emit_release_gate_evidence": False,
    }


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


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file. Returns ``None`` if the file is missing or
    unreadable. **Never mutates** the file."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _entries_list(payload: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(key)
    if not isinstance(raw, list):
        return []
    return [e for e in raw if isinstance(e, dict)]


# ---------------------------------------------------------------------------
# Deterministic selection
# ---------------------------------------------------------------------------


def _select_item(
    delegation: dict[str, Any] | None,
    bugfix: dict[str, Any] | None,
    queue: dict[str, Any] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Pick at most one item per cycle by deterministic ordering.

    Order: delegation_id ASC → bugfix candidate_id ASC → queue
    item_id ASC. Returns ``(source_kind, item)`` or ``(None, None)``
    when nothing eligible exists.
    """
    deleg_entries = sorted(
        (e for e in _entries_list(delegation, "entries") if e.get("delegation_id")),
        key=lambda e: str(e.get("delegation_id")),
    )
    if deleg_entries:
        return ("delegation", deleg_entries[0])

    bug_candidates = sorted(
        (c for c in _entries_list(bugfix, "candidates") if c.get("candidate_id")),
        key=lambda c: str(c.get("candidate_id")),
    )
    if bug_candidates:
        return ("bugfix", bug_candidates[0])

    queue_items = sorted(
        (i for i in _entries_list(queue, "items") if i.get("item_id")),
        key=lambda i: str(i.get("item_id")),
    )
    if queue_items:
        return ("queue", queue_items[0])

    return (None, None)


def _source_id(source_kind: str, item: dict[str, Any]) -> str:
    if source_kind == "delegation":
        return str(item.get("delegation_id") or "")
    if source_kind == "bugfix":
        return str(item.get("candidate_id") or "")
    if source_kind == "queue":
        return str(item.get("item_id") or "")
    return ""


def _cycle_id_from(source_kind: str, item: dict[str, Any]) -> str:
    """sha256-derived deterministic cycle_id from item identity.

    Includes ``source_kind`` so that collisions across upstream artefacts
    are impossible by construction.
    """
    raw = f"{source_kind}|{_source_id(source_kind, item)}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# Authority classification (read upstream-recorded decision verbatim)
# ---------------------------------------------------------------------------


def _classify(item: dict[str, Any]) -> tuple[str, str]:
    """Read the upstream-recorded execution-authority classification.

    All three upstream ADE producers (A8/A10/A11) record an
    ``execution_authority`` field per item — Step 5.0 obeys it
    verbatim, never re-classifies.

    Returns ``(decision, halt_reason)`` where ``halt_reason`` is one
    of the closed ``STEP5_HALT_REASONS`` values.
    """
    decision = item.get("execution_authority") or item.get("authority_decision")
    if decision == "AUTO_ALLOWED":
        return ("AUTO_ALLOWED", "ok")
    if decision == "PERMANENTLY_DENIED":
        return ("PERMANENTLY_DENIED", "permanently_denied")
    # Unknown / NEEDS_HUMAN / missing → fail-safe to NEEDS_HUMAN halt.
    return ("NEEDS_HUMAN", "needs_human")


def _outcome_for(halt_reason: str) -> str:
    if halt_reason == "ok":
        return "plan_emitted"
    if halt_reason == "needs_human":
        return "halt_needs_human"
    if halt_reason == "permanently_denied":
        return "halt_permanently_denied"
    if halt_reason == "out_of_allowlist":
        return "halt_out_of_allowlist"
    return "no_op_no_eligible_item"


# ---------------------------------------------------------------------------
# Plan / loop / history payload builders
# ---------------------------------------------------------------------------


def _bounded_str_list(value: Any, max_items: int, max_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value[:max_items]:
        if isinstance(v, str):
            out.append(v[:max_len])
    return out


def _build_plan_payload(
    *,
    source_kind: str,
    item: dict[str, Any],
    cycle_id: str,
    decision: str,
    halt_reason: str,
    outcome: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Construct the closed ``step5_plan.v1.json`` payload."""
    target_paths = _bounded_str_list(item.get("target_paths"), 16, 200)
    acceptance = _bounded_str_list(item.get("acceptance_criteria"), 16, 200)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "cycle_id": cycle_id,
        "source_kind": source_kind,
        "source_id": _source_id(source_kind, item),
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "execution_authority_decision": decision,
        "halt_reason": halt_reason,
        "outcome": outcome,
        "human_required": True,
        "release_gate_required": True,
        "acceptance_criteria": acceptance,
        "target_paths": target_paths,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "step5_5_1_proposed": _fresh_step5_5_1_proposed(),
        "step5_5_2_proposed": _fresh_step5_5_2_proposed(),
        "vocabularies": {
            "step5_substages": list(STEP5_SUBSTAGES),
            "halt_reasons": list(STEP5_HALT_REASONS),
            "outcome_kinds": list(STEP5_OUTCOME_KINDS),
            "source_kinds": list(STEP5_SOURCE_KINDS),
        },
    }


def _build_no_op_plan_payload(*, generated_at_utc: str) -> dict[str, Any]:
    """Plan payload for cycles where no eligible upstream item was
    found. Carries a stable ``cycle_id`` derived from the empty
    identity tuple so repeated empty ticks are byte-identical."""
    cycle_id = hashlib.sha256(b"no_eligible_item|").hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "cycle_id": cycle_id,
        "source_kind": "none",
        "source_id": "",
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "execution_authority_decision": "NOT_EVALUATED",
        "halt_reason": "no_eligible_item",
        "outcome": "no_op_no_eligible_item",
        "human_required": False,
        "release_gate_required": False,
        "acceptance_criteria": [],
        "target_paths": [],
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "step5_5_1_proposed": _fresh_step5_5_1_proposed(),
        "step5_5_2_proposed": _fresh_step5_5_2_proposed(),
        "vocabularies": {
            "step5_substages": list(STEP5_SUBSTAGES),
            "halt_reasons": list(STEP5_HALT_REASONS),
            "outcome_kinds": list(STEP5_OUTCOME_KINDS),
            "source_kinds": list(STEP5_SOURCE_KINDS),
        },
    }


def _history_entry_for(plan: dict[str, Any]) -> dict[str, Any]:
    """Compact projection written to history.jsonl per cycle."""
    return {
        "generated_at_utc": plan["generated_at_utc"],
        "cycle_id": plan["cycle_id"],
        "source_kind": plan["source_kind"],
        "source_id": plan["source_id"],
        "execution_authority_decision": plan["execution_authority_decision"],
        "halt_reason": plan["halt_reason"],
        "outcome": plan["outcome"],
        "module_version": plan["module_version"],
    }


def _build_loop_snapshot(
    *,
    plan: dict[str, Any],
    presence: dict[str, bool],
    generated_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": LOOP_REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "presence": presence,
        "current_plan": {
            "cycle_id": plan["cycle_id"],
            "source_kind": plan["source_kind"],
            "source_id": plan["source_id"],
            "outcome": plan["outcome"],
            "halt_reason": plan["halt_reason"],
            "execution_authority_decision": plan["execution_authority_decision"],
        },
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "max_history_entries": MAX_HISTORY_ENTRIES,
        "queue_module_version": dwq.MODULE_VERSION,
        "release_gate_module_version": "v3.15.16.A9",
        "bugfix_loop_module_version": dbl.MODULE_VERSION,
        "delegation_module_version": ddl.MODULE_VERSION,
    }


# ---------------------------------------------------------------------------
# Atomic write + bounded history append
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside ``logs/step5_*/...``."""
    posix = path.as_posix()
    if not any(prefix in posix or posix.startswith(prefix) for prefix in _STEP5_WRITE_PREFIXES):
        raise ValueError(
            "development_step5_loop._atomic_write_json refuses "
            f"non-step5-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_step5_loop.", suffix=".tmp", dir=str(path.parent)
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


def _append_history(path: Path, entry: dict[str, Any]) -> None:
    """Append ``entry`` to a bounded JSONL file. Truncates to the
    last ``MAX_HISTORY_ENTRIES`` lines on every write."""
    posix = path.as_posix()
    if "logs/step5_plan/" not in posix and not posix.startswith("logs/step5_plan/"):
        raise ValueError(
            "development_step5_loop._append_history refuses "
            f"non-step5-plan-logs path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        try:
            existing = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError:
            existing = []
    line = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    existing.append(line)
    if len(existing) > MAX_HISTORY_ENTRIES:
        existing = existing[-MAX_HISTORY_ENTRIES:]
    text = "\n".join(existing) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_step5_loop.history.", suffix=".tmp", dir=str(path.parent)
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


# ---------------------------------------------------------------------------
# Audit-ledger event emission (best-effort; never gates the cycle)
# ---------------------------------------------------------------------------


def _emit_audit_event(*, cycle_id: str, outcome: str, halt_reason: str) -> bool:
    """Append one ``reporting.agent_audit`` event for this cycle.

    Returns ``True`` if the event was successfully appended,
    ``False`` otherwise. Step 5.0 treats audit emission as
    best-effort and never raises on failure (mirrors A8–A13 audit
    posture).

    The event is recorded with ``autonomy_level_claimed=0`` and a
    closed-vocab outcome string; no payload, diff, or command summary
    is included.
    """
    try:
        _audit.append_event(
            {
                "actor": "step5_loop:dry_run",
                "event": "step5_cycle",
                "tool": "development_step5_loop",
                "outcome": "ok" if outcome == "plan_emitted" else "blocked",
                "block_reason": halt_reason if halt_reason != "ok" else None,
                "autonomy_level_claimed": 0,
                "step5_cycle_id": cycle_id,
                "step5_outcome": outcome,
                "step5_halt_reason": halt_reason,
                "step5_module_version": MODULE_VERSION,
            }
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pure scorer + write-side
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    delegation_path: Path | None = None,
    bugfix_path: Path | None = None,
    queue_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Pure, deterministic Step 5.0 scorer.

    Reads the three upstream ADE artefacts (read-only), selects at
    most one item by deterministic ordering, classifies, and returns
    a snapshot dict containing both the per-cycle ``plan`` and the
    aggregated ``loop`` projection.

    Tests that assert byte-stable output must inject
    ``generated_at_utc``.
    """
    dp = delegation_path if delegation_path is not None else ddl.ARTIFACT_LATEST
    bp = bugfix_path if bugfix_path is not None else dbl.ARTIFACT_LATEST
    qp = queue_path if queue_path is not None else dwq.ARTIFACT_LATEST
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    deleg_payload = _read_json(dp)
    bug_payload = _read_json(bp)
    queue_payload = _read_json(qp)

    presence = {
        "delegation": deleg_payload is not None,
        "bugfix_loop": bug_payload is not None,
        "queue": queue_payload is not None,
    }

    source_kind, item = _select_item(deleg_payload, bug_payload, queue_payload)

    if source_kind is None or item is None:
        plan = _build_no_op_plan_payload(generated_at_utc=ts)
    else:
        cycle_id = _cycle_id_from(source_kind, item)
        decision, halt_reason = _classify(item)
        outcome = _outcome_for(halt_reason)
        plan = _build_plan_payload(
            source_kind=source_kind,
            item=item,
            cycle_id=cycle_id,
            decision=decision,
            halt_reason=halt_reason,
            outcome=outcome,
            generated_at_utc=ts,
        )

    loop_snapshot = _build_loop_snapshot(
        plan=plan,
        presence=presence,
        generated_at_utc=ts,
    )

    return {
        "plan": plan,
        "loop": loop_snapshot,
        "history_entry": _history_entry_for(plan),
        "presence": presence,
    }


def write_outputs(snapshot: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Persist the snapshot artefacts under ``logs/step5_*/...``.

    Order:

    1. ``logs/step5_plan/<cycle_id>.json`` (per-cycle plan, atomic).
    2. ``logs/step5_plan/history.jsonl`` (bounded append, atomic
       rewrite at the 90-entry window).
    3. ``logs/step5_loop/latest.json`` (loop snapshot, atomic).
    """
    plan = snapshot["plan"]
    cycle_id = plan["cycle_id"]
    plan_path = PLAN_DIR / f"{cycle_id}.json"
    _atomic_write_json(plan_path, plan)
    _append_history(HISTORY_PATH, snapshot["history_entry"])
    _atomic_write_json(ARTIFACT_LATEST, snapshot["loop"])
    return (plan_path, HISTORY_PATH, ARTIFACT_LATEST)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.development_step5_loop",
        description=(
            "Step 5.0 dry-run planner. Reads upstream A8/A10/A11 artefacts, "
            "selects at most one item per cycle, classifies, and emits a "
            "deterministic plan artefact under logs/step5_*/. Never opens "
            "real branches/PRs, never invokes git/gh/subprocess/network, "
            "never mutates upstream artefacts. Step 5 implementation "
            "remains BLOCKED."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Step 5.0 is dry-run-only. This flag is accepted for "
            "operator clarity; the module behaves identically with or "
            "without it. Reserved for forward compatibility with later "
            "sub-stages."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist artefacts; print the snapshot JSON to "
            "stdout only. Useful for read-only inspection."
        ),
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
        # Emit one audit event per persisted cycle.
        _emit_audit_event(
            cycle_id=snapshot["plan"]["cycle_id"],
            outcome=snapshot["plan"]["outcome"],
            halt_reason=snapshot["plan"]["halt_reason"],
        )
    indent = args.indent if args.indent > 0 else None
    print(json.dumps(snapshot, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
