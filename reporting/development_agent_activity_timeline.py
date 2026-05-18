"""Agent Activity Center — read-only aggregator (B2.0b + A20d).

Pure-stdlib aggregator that reads the closed 14-entry catalog of
upstream ADE-core artefacts on disk and writes a single canonical
artefact at ``logs/development_agent_activity_timeline/latest.json``
satisfying the closed schema defined in
``docs/governance/agent_activity_center_aggregator_schema.md``.

Catalog cardinality (post-A20d)
-------------------------------

* ``UPSTREAM_CATALOG_LEN = 14`` — 10 ADE-core upstream artefact
  paths + 1 read-only seed health entry + 3 A20-series read-only
  roadmap artefacts (A20a catalog, A20b unit decomposition, A20c
  unit-authority projection).
* ``PROJECTABLE_UPSTREAM_LEN = 7`` — A18c, A18 promotion report,
  Step 5.0 loop snapshot, N5b merge preflight, A20a roadmap task
  catalog, A20b implementation-unit decomposition, A20c unit
  authority decisions. These seven sources contribute
  ``work_items[]`` rows.
* ``HEALTH_ONLY_UPSTREAM_LEN = 7`` — work_queue (A8), delegation
  (A11), bugfix_loop (A10), release_gate (A9), step5_plan history,
  operational_digest (A12), plus the read-only
  ``generated_seed.jsonl`` health entry. These contribute
  ``artifact_health[]`` rows only.

A20d note: the three roadmap upstreams are surfaced as read-only
work-item rows. Each row carries explicit ``read_only=True`` and
``mutation_allowed=False`` markers; no approval-button payload, no
required-phrase synthesis, no mutation endpoint, no next-buildable
selector (that is A20e scope).

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.agent_audit_summary.assert_no_secrets`` only.
* No imports of ``subprocess``, ``socket``, ``urllib``,
  ``urllib.request``, ``urllib.parse``, ``requests``, ``httpx``,
  ``aiohttp``, ``http.client``.
* No imports of ``research``, ``dashboard.dashboard``,
  ``automation``, ``broker``, ``agent.risk``, ``agent.execution``,
  ``reporting.intelligent_routing``.
* No ``os.environ`` read of any kind. Invariants are sourced from
  upstream artefacts or constants — never from process env.
* No GitHub CLI invocation, no version-control CLI invocation, no
  child-process spawn, no ``os.system``, no ``popen``, no
  shell-mode subprocess flag.
* Atomic write only under
  ``logs/development_agent_activity_timeline/...`` via
  ``tempfile.mkstemp`` + ``os.replace``. Sentinel-restricted to the
  closed write prefix.
* No write to ``seed.jsonl``, ``generated_seed.jsonl``, or
  ``delegation_seed.jsonl``. The module mentions
  ``generated_seed.jsonl`` only as a read path in the catalog.
* Deterministic output: sorted-keys indented JSON. Same upstream
  contents + same injected ``generated_at_utc`` → byte-identical
  artefact.
* Read-only over upstreams: pinned by a before/after sha256 test.
* ``step5_implementation_allowed = False`` (Final constant).
* ``STEP5_ENABLED_SUBSTAGE = "none"`` (Final constant).
* Per-record bounded sizes per schema §13.

What this module is NOT
-----------------------

* Not a Flask blueprint. B2.0c is a separate future unit.
* Not a PWA frontend. B2.0d is a separate future unit.
* Not a push-notification publisher. B2.0e is a separate future
  unit.
* Not a mutation endpoint. Read-only by construction.
* Not authorised to flip ``step5_implementation_allowed`` or
  ``STEP5_ENABLED_SUBSTAGE``. Both stay ``Final`` at their
  default-deny values.
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

from reporting.agent_audit_summary import assert_no_secrets


# ---------------------------------------------------------------------------
# Schema / module anchors
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "aat.v0.1"
REPORT_KIND: Final[str] = "agent_activity_timeline"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies (echoed in the ``vocabularies`` envelope block)
# ---------------------------------------------------------------------------

STAGES: Final[tuple[str, ...]] = (
    "discovered",
    "queued",
    "delegated",
    "planned",
    "dry_run_ready",
    "pr_proposed",
    "pr_opened",
    "ci_feedback",
    "needs_human",
    "merge_candidate",
    "done_blocked",
)

SEVERITIES: Final[tuple[str, ...]] = ("info", "warn", "human", "error")

DECISIONS: Final[tuple[str, ...]] = (
    "queue",
    "delegate",
    "plan",
    "generate",
    "approve_dry_run",
    "require_human",
    "flag",
    "flag_flaky",
    "quarantine",
    "review",
    "rerun",
    "surface",
    "advise_merge",
    "no_op",
    "ingest",
    "annotate",
)

RISKS: Final[tuple[str, ...]] = ("low", "medium", "high", "critical")

FRESHNESS_STATES: Final[tuple[str, ...]] = (
    "fresh",
    "stale",
    "missing",
    "malformed",
)

ARTIFACT_HEALTH_STATES: Final[tuple[str, ...]] = (
    "ok",
    "stale",
    "malformed",
    "missing",
    "unreadable",
)

HUMAN_ACTION_TYPES: Final[tuple[str, ...]] = (
    "operator_go_required",
    "review_recommended",
    "copy_only",
    "informational",
)

INVARIANT_STATES: Final[tuple[str, ...]] = (
    "on",
    "off",
    "danger_off",
    "info",
    "unknown",
)

SOURCE_KINDS: Final[tuple[str, ...]] = (
    "roadmap_v6",
    "work_queue",
    "delegation",
    "bugfix_loop",
    "release_gate",
    "generated_lane",
    "generated_lane_promotion",
    "step5_plan",
    "step5_loop",
    "ci_feedback",
    "merge_preflight",
    "operational_digest",
    "addendum_loop",
    "roadmap_task_catalog",
    "roadmap_implementation_unit",
    "roadmap_unit_authority_decision",
)

AGENT_ROLES: Final[tuple[str, ...]] = (
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

EVENT_TYPES: Final[tuple[str, ...]] = (
    "discovered",
    "annotated",
    "queued",
    "delegated",
    "plan_drafted",
    "review",
    "verdict",
    "generated",
    "detected",
    "ci_result",
    "rerun_queued",
    "dry_run",
    "preflight",
    "quarantined",
    "in_review",
    "surfaced",
)


# ---------------------------------------------------------------------------
# Closed upstream catalog
#
# Each entry: (group, source_kind_or_None, relative_artifact_path,
#              projectable_in_v0_1).
#
# ``projectable_in_v0_1=True`` means the v0.1 aggregator emits
# WorkItem rows from this upstream. ``False`` means the upstream
# contributes ArtifactHealth only.
# ---------------------------------------------------------------------------

UPSTREAM_CATALOG: Final[
    tuple[tuple[str, str | None, str, bool], ...]
] = (
    (
        "queue",
        "work_queue",
        "logs/development_work_queue/latest.json",
        False,
    ),
    (
        "queue",
        "delegation",
        "logs/development_delegation/latest.json",
        False,
    ),
    (
        "loops",
        "bugfix_loop",
        "logs/development_bugfix_loop/latest.json",
        False,
    ),
    (
        "gates",
        "release_gate",
        "logs/development_release_gate/latest.json",
        False,
    ),
    (
        "step5",
        "step5_loop",
        "logs/step5_loop/latest.json",
        True,
    ),
    (
        "step5",
        "step5_plan",
        "logs/step5_plan/history.jsonl",
        False,
    ),
    (
        "generated",
        "generated_lane",
        "logs/development_generated_lane_a18c/latest.json",
        True,
    ),
    (
        "generated",
        "generated_lane_promotion",
        "logs/development_generated_lane_promotion_report/latest.json",
        True,
    ),
    (
        "gates",
        "merge_preflight",
        "logs/development_merge_preflight/latest.json",
        True,
    ),
    (
        "digest",
        "operational_digest",
        "logs/development_operational_digest/latest.json",
        False,
    ),
    (
        "seed",
        None,
        "generated_seed.jsonl",
        False,
    ),
    (
        "roadmap",
        "roadmap_task_catalog",
        "logs/roadmap_task_catalog/latest.json",
        True,
    ),
    (
        "roadmap",
        "roadmap_implementation_unit",
        "logs/roadmap_task_units/latest.json",
        True,
    ),
    (
        "roadmap",
        "roadmap_unit_authority_decision",
        "logs/roadmap_unit_authority/latest.json",
        True,
    ),
)

UPSTREAM_CATALOG_LEN: Final[int] = 14
PROJECTABLE_UPSTREAM_LEN: Final[int] = 7
HEALTH_ONLY_UPSTREAM_LEN: Final[int] = 7


# ---------------------------------------------------------------------------
# Operator-approved TTL defaults (seconds)
# ---------------------------------------------------------------------------

TTL_BY_GROUP: Final[dict[str, int]] = {
    "queue": 600,
    "loops": 1800,
    "step5": 1800,
    "gates": 1800,
    "generated": 1800,
    "digest": 1800,
    "seed": 86400,
    "roadmap": 1800,
}


# ---------------------------------------------------------------------------
# Bounded sizes (mirrors schema §13)
# ---------------------------------------------------------------------------

MAX_WORK_ITEMS: Final[int] = 256
MAX_AGENT_EVENTS: Final[int] = 2048
MAX_HUMAN_ACTIONS: Final[int] = 64
MAX_ARTIFACT_HEALTH: Final[int] = 64
MAX_INVARIANT_STATUS: Final[int] = 32


# ---------------------------------------------------------------------------
# Per-row scalar caps
# ---------------------------------------------------------------------------

MAX_TITLE_LEN: Final[int] = 200
MAX_VERDICT_LEN: Final[int] = 200
MAX_NEXT_ACTION_LEN: Final[int] = 200
MAX_SUMMARY_LEN: Final[int] = 600
MAX_REASON_LEN: Final[int] = 200
MAX_PARSE_ERROR_LEN: Final[int] = 200
MAX_INVARIANT_DETAIL_LEN: Final[int] = 200


# ---------------------------------------------------------------------------
# Read-only seed warning chip
# ---------------------------------------------------------------------------

SEED_READ_ONLY_WARNING: Final[str] = "Read-only · UI must not write"


# ---------------------------------------------------------------------------
# Repo-relative artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_agent_activity_timeline"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_agent_activity_timeline/latest.json"
)

#: Atomic-write allowlist. Any path whose POSIX form does not
#: contain this prefix raises ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/development_agent_activity_timeline/"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    """Return an ISO 8601 UTC timestamp truncated to seconds."""
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso_utc(s: str | None) -> _dt.datetime | None:
    """Parse an ISO 8601 UTC string. Returns ``None`` on failure."""
    if not s or not isinstance(s, str):
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return _dt.datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _utc_seconds_age(reference_utc: str, candidate_utc: str | None) -> int:
    """Return the non-negative integer age in seconds between
    ``reference_utc`` and ``candidate_utc``. Returns 0 when either
    side is missing or unparseable."""
    ref = _parse_iso_utc(reference_utc)
    cand = _parse_iso_utc(candidate_utc)
    if ref is None or cand is None:
        return 0
    delta_s = int((ref - cand).total_seconds())
    return max(0, delta_s)


def _file_mtime_iso(path: Path) -> str | None:
    """Return the file's mtime as an ISO 8601 UTC string truncated
    to seconds. Returns ``None`` if the file does not exist."""
    try:
        st = path.stat()
    except (OSError, ValueError):
        return None
    return (
        _dt.datetime.fromtimestamp(st.st_mtime, _dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Bounded helpers
# ---------------------------------------------------------------------------


def _truncate(s: Any, cap: int) -> str:
    """Coerce to string and truncate to ``cap`` characters."""
    if s is None:
        return ""
    text = str(s)
    if len(text) > cap:
        return text[: cap - 1] + "…"
    return text


def _short_id_from(*parts: str) -> str:
    """Deterministic short id derived from the parts. Stable across
    Python invocations (hash randomisation does not affect sha256)."""
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Filesystem read helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> tuple[str, dict[str, Any] | None, str | None]:
    """Best-effort JSON read.

    Returns ``(status, payload, error_detail)`` where ``status`` is
    one of:

    * ``"ok"`` — file present, parsed cleanly. ``payload`` is the dict.
    * ``"absent"`` — file does not exist. ``payload`` is ``None``.
    * ``"malformed"`` — file present, parse failed. ``payload`` is
      ``None`` and ``error_detail`` carries a bounded error string.

    No exceptions escape. No subprocess. No network.
    """
    if not path.is_file():
        return ("absent", None, None)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ("malformed", None, _truncate(repr(exc), MAX_PARSE_ERROR_LEN))
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        return ("malformed", None, _truncate(str(exc), MAX_PARSE_ERROR_LEN))
    if not isinstance(payload, dict):
        return ("ok", None, None)
    return ("ok", payload, None)


def _count_jsonl_rows(path: Path) -> tuple[str, int, str | None]:
    """Best-effort JSONL row count. Returns ``(status, row_count,
    error_detail)``. ``status`` ∈ ``{"ok", "absent", "malformed"}``."""
    if not path.is_file():
        return ("absent", 0, None)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return ("malformed", 0, _truncate(repr(exc), MAX_PARSE_ERROR_LEN))
    rows = [line for line in text.splitlines() if line.strip()]
    return ("ok", len(rows), None)


# ---------------------------------------------------------------------------
# Atomic write helper — sentinel-restricted
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as sorted-key indented JSON.

    Refuses any path whose POSIX form does not contain
    ``logs/development_agent_activity_timeline/`` — the closed
    write allowlist.
    """
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_agent_activity_timeline._atomic_write_json "
            f"refuses non-aggregator-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_agent_activity_timeline.",
        suffix=".tmp",
        dir=str(path.parent),
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
# Projection helpers — v0.1 emits WorkItems from 4 sources only
# ---------------------------------------------------------------------------


def _project_step5_loop(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/step5_loop/latest.json``.

    Emits at most one WorkItem when the loop carries a non-no-op
    ``current_plan``. Returns ``(work_items, agent_events, human_actions)``.
    """
    if not isinstance(payload, dict):
        return ([], [], [])
    plan = payload.get("current_plan") or {}
    if not isinstance(plan, dict):
        return ([], [], [])
    outcome = plan.get("outcome")
    if outcome in (None, "no_op_no_eligible_item"):
        return ([], [], [])

    cycle_id = str(plan.get("cycle_id") or "")
    source_id = str(plan.get("source_id") or "")
    halt_reason = plan.get("halt_reason")
    decision = plan.get("execution_authority_decision")
    upstream_source_kind = plan.get("source_kind") or ""

    if outcome == "halt_needs_human":
        stage = "needs_human"
        human_needed = True
        risk = "medium"
    elif outcome in ("halt_permanently_denied", "halt_out_of_allowlist"):
        stage = "done_blocked"
        human_needed = False
        risk = "high"
    elif outcome == "plan_emitted":
        stage = "planned"
        human_needed = False
        risk = "low"
    else:
        # Unknown outcome — surface as needs_human (fail-safe).
        stage = "needs_human"
        human_needed = True
        risk = "medium"

    short = _short_id_from("step5_loop", cycle_id or source_id)
    item_id = f"wi_step5_{short}"
    title = _truncate(
        f"Step 5.0 cycle {short} ({upstream_source_kind or 'unknown'})",
        MAX_TITLE_LEN,
    )
    verdict = _truncate(
        f"outcome={outcome} halt_reason={halt_reason} decision={decision}",
        MAX_VERDICT_LEN,
    )
    next_action = _truncate(
        "Operator review" if human_needed else "Awaiting next cycle",
        MAX_NEXT_ACTION_LEN,
    )
    summary = _truncate(
        (
            f"Step 5.0 dry-run loop produced outcome={outcome}. "
            f"Authority decision={decision}. Halt reason={halt_reason}. "
            "Loop remains dry-run-only; substage stays \"none\"."
        ),
        MAX_SUMMARY_LEN,
    )
    updated_at = (
        payload.get("generated_at_utc")
        if isinstance(payload.get("generated_at_utc"), str)
        else generated_at_utc
    )
    event_id = f"ev_step5_{short}"

    work_item = {
        "item_id": item_id,
        "title": title,
        "source_kind": "step5_loop",
        "source_path": "logs/step5_loop/latest.json",
        "current_stage": stage,
        "owner_role": "determinism_guardian",
        "risk": risk,
        "human_needed": human_needed,
        "latest_verdict": verdict,
        "next_action": next_action,
        "updated_at": updated_at,
        "summary": summary,
        "event_ids": [event_id],
    }

    agent_event = {
        "event_id": event_id,
        "item_id": item_id,
        "timestamp": updated_at,
        "agent_role": "determinism_guardian",
        "module": "step5_loop",
        "event_type": "plan_drafted" if outcome == "plan_emitted" else "verdict",
        "summary": _truncate(verdict, MAX_REASON_LEN),
        "decision": (
            "plan"
            if outcome == "plan_emitted"
            else ("require_human" if human_needed else "flag")
        ),
        "reason": _truncate(
            f"step5_loop outcome={outcome}",
            MAX_REASON_LEN,
        ),
        "artifact_path": "logs/step5_loop/latest.json",
        "severity": "human" if human_needed else "info",
    }

    human_actions: list[dict[str, Any]] = []
    if human_needed:
        action_id = f"ha_step5_{short}"
        human_actions.append(
            {
                "action_id": action_id,
                "item_id": item_id,
                "severity": "medium",
                "title": title,
                "why_required": _truncate(
                    (
                        "Step 5.0 loop halted with needs_human. Operator "
                        "review required before any further cycle."
                    ),
                    MAX_SUMMARY_LEN,
                ),
                "required_phrase": None,
                "safe_to_ignore": False,
                "copy_only": True,
                "source_artifact_path": "logs/step5_loop/latest.json",
                "suggested_role": "determinism_guardian",
                "created_at": updated_at,
            }
        )

    return ([work_item], [agent_event], human_actions)


def _project_a18c(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/development_generated_lane_a18c/latest.json``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    bounded = rows[:16]
    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for row in bounded:
        if not isinstance(row, dict):
            continue
        cand_id = str(row.get("a18c_candidate_id") or row.get("generated_candidate_id") or "")
        if not cand_id:
            continue
        admission_decision = row.get("admission_decision") or "needs_human"
        admission_reason = row.get("admission_reason") or "needs_human_authority_decision"
        target_lane = row.get("would_target_lane") or "none"
        requires_go = bool(row.get("would_require_operator_go"))

        short = _short_id_from("a18c", cand_id)
        item_id = f"wi_a18c_{short}"

        if admission_decision == "admissible":
            stage = "queued"
            human_needed = False
            risk = "low"
        elif admission_decision == "permanently_denied":
            stage = "done_blocked"
            human_needed = False
            risk = "high"
        else:
            stage = "needs_human"
            human_needed = True
            risk = "medium"

        title = _truncate(
            f"A18c admission · {cand_id}", MAX_TITLE_LEN
        )
        verdict = _truncate(
            (
                f"admission_decision={admission_decision} "
                f"admission_reason={admission_reason} "
                f"would_target_lane={target_lane}"
            ),
            MAX_VERDICT_LEN,
        )
        next_action = _truncate(
            "Operator review · A17 admission gate"
            if human_needed
            else "Awaiting downstream promotion report",
            MAX_NEXT_ACTION_LEN,
        )
        summary = _truncate(
            (
                "Generated-lane A18c projected this row through the A17 "
                "admission policy. The A18c projector never admits to "
                "the queue; admission stays operator-paced."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_a18c_{short}"
        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "generated_lane",
                "source_path": "logs/development_generated_lane_a18c/latest.json",
                "current_stage": stage,
                "owner_role": "release_gate_agent",
                "risk": risk,
                "human_needed": human_needed,
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "release_gate_agent",
                "module": "generated_lane_a18c",
                "event_type": "verdict",
                "summary": verdict,
                "decision": "require_human" if human_needed else "surface",
                "reason": _truncate(
                    f"a18c admission decision={admission_decision}",
                    MAX_REASON_LEN,
                ),
                "artifact_path": (
                    "logs/development_generated_lane_a18c/latest.json"
                ),
                "severity": "human" if human_needed else "info",
            }
        )
        if human_needed:
            actions.append(
                {
                    "action_id": f"ha_a18c_{short}",
                    "item_id": item_id,
                    "severity": "medium",
                    "title": title,
                    "why_required": _truncate(
                        (
                            "A18c projector returned needs_human. "
                            "Promotion remains operator-paced; no "
                            "phrase is synthesised here."
                        ),
                        MAX_SUMMARY_LEN,
                    ),
                    # Pinned default: A18c rows never synthesise a phrase.
                    "required_phrase": None,
                    "safe_to_ignore": False,
                    "copy_only": True,
                    "source_artifact_path": (
                        "logs/development_generated_lane_a18c/latest.json"
                    ),
                    "suggested_role": "release_gate_agent",
                    "created_at": upstream_ts_str,
                }
            )
        # Suppress the requires_go signal in v0.1 — informational only.
        _ = requires_go

    return (work_items, events, actions)


def _project_promotion_report(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/development_generated_lane_promotion_report/latest.json``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    envelope_phrase = payload.get("operator_go_phrase_required")
    if not isinstance(envelope_phrase, str):
        envelope_phrase = None

    bounded = rows[:16]
    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for row in bounded:
        if not isinstance(row, dict):
            continue
        cand_id = str(
            row.get("a18c_candidate_id")
            or row.get("generated_candidate_id")
            or row.get("item_id")
            or ""
        )
        if not cand_id:
            continue
        block_reason = row.get("block_reason") or "promotion_disabled_by_default"

        short = _short_id_from("a18_promotion", cand_id)
        item_id = f"wi_a18prom_{short}"
        title = _truncate(
            f"A18 promotion report · {cand_id}", MAX_TITLE_LEN
        )
        verdict = _truncate(
            (
                f"promotion_allowed=False block_reason={block_reason}"
            ),
            MAX_VERDICT_LEN,
        )
        next_action = _truncate(
            "Operator-go required to advance promotion",
            MAX_NEXT_ACTION_LEN,
        )
        summary = _truncate(
            (
                "A18 promotion-readiness report row. Every row is "
                "hard-pinned promotion_allowed=False; the module "
                "never promotes. Operator-go is required to advance."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_a18prom_{short}"
        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "generated_lane_promotion",
                "source_path": (
                    "logs/development_generated_lane_promotion_report/latest.json"
                ),
                "current_stage": "needs_human",
                "owner_role": "release_gate_agent",
                "risk": "medium",
                "human_needed": True,
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "release_gate_agent",
                "module": "generated_lane_promotion",
                "event_type": "verdict",
                "summary": verdict,
                "decision": "require_human",
                "reason": _truncate(
                    f"promotion-report block_reason={block_reason}",
                    MAX_REASON_LEN,
                ),
                "artifact_path": (
                    "logs/development_generated_lane_promotion_report/latest.json"
                ),
                "severity": "human",
            }
        )
        # Operator-go phrase: source from the row's own
        # ``required_operator_go_phrase`` field, falling back to the
        # envelope-level ``operator_go_phrase_required`` field. Never
        # synthesise.
        row_phrase = row.get("required_operator_go_phrase")
        if not isinstance(row_phrase, str):
            row_phrase = envelope_phrase
        actions.append(
            {
                "action_id": f"ha_a18prom_{short}",
                "item_id": item_id,
                "severity": "medium",
                "title": title,
                "why_required": _truncate(
                    (
                        "Promotion remains operator-paced; phrase "
                        "originates from the promotion-report row "
                        "metadata, not from the aggregator."
                    ),
                    MAX_SUMMARY_LEN,
                ),
                "required_phrase": row_phrase,
                "safe_to_ignore": False,
                "copy_only": True,
                "source_artifact_path": (
                    "logs/development_generated_lane_promotion_report/latest.json"
                ),
                "suggested_role": "release_gate_agent",
                "created_at": upstream_ts_str,
            }
        )

    return (work_items, events, actions)


def _project_merge_preflight(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/development_merge_preflight/latest.json``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    candidates = payload.get("candidates") or payload.get("rows") or []
    if not isinstance(candidates, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    bounded = candidates[:16]
    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for cand in bounded:
        if not isinstance(cand, dict):
            continue
        cand_id = str(
            cand.get("preflight_id")
            or cand.get("recommendation_id")
            or cand.get("pr_number")
            or ""
        )
        if not cand_id:
            continue
        verdict_value = cand.get("dry_run_verdict") or "would_block"

        short = _short_id_from("merge_preflight", cand_id)
        item_id = f"wi_mp_{short}"

        if verdict_value == "would_be_live_candidate_if_authorized":
            stage = "merge_candidate"
            risk = "low"
        elif verdict_value == "would_require_operator":
            stage = "needs_human"
            risk = "medium"
        else:
            stage = "done_blocked"
            risk = "low"

        title = _truncate(
            f"Merge preflight · {cand_id}", MAX_TITLE_LEN
        )
        verdict = _truncate(
            f"dry_run_verdict={verdict_value}", MAX_VERDICT_LEN
        )
        next_action = _truncate(
            "Live merge is permanently disabled — surfaced for operator visibility only",
            MAX_NEXT_ACTION_LEN,
        )
        summary = _truncate(
            (
                "N5b Phase 1 dry-run merge preflight projection. The "
                "live merge path is not implemented; this surfaces "
                "what a hypothetical live merge would require."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_mp_{short}"
        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "merge_preflight",
                "source_path": "logs/development_merge_preflight/latest.json",
                "current_stage": stage,
                "owner_role": "release_gate_agent",
                "risk": risk,
                "human_needed": stage == "needs_human",
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "release_gate_agent",
                "module": "development_merge_preflight",
                "event_type": "preflight",
                "summary": verdict,
                "decision": (
                    "advise_merge"
                    if stage == "merge_candidate"
                    else "require_human"
                ),
                "reason": _truncate(
                    f"merge_preflight verdict={verdict_value}",
                    MAX_REASON_LEN,
                ),
                "artifact_path": (
                    "logs/development_merge_preflight/latest.json"
                ),
                "severity": (
                    "human" if stage == "needs_human" else "info"
                ),
            }
        )

    return (work_items, events, actions)


# ---------------------------------------------------------------------------
# A20d roadmap projectors (read-only visibility for A20a / A20b / A20c).
# Each row carries explicit ``read_only=True`` / ``mutation_allowed=False``
# markers. No HumanAction synthesises a required_phrase. No mutation
# endpoint is emitted. No next-buildable-unit selection — that is A20e
# scope.
# ---------------------------------------------------------------------------

_ROADMAP_MAX_ROWS: Final[int] = 64

_A20B_RISK_TO_AAC_RISK: Final[dict[str, str]] = {
    "LOW": "low",
    "MEDIUM": "medium",
    "HIGH": "high",
    "UNKNOWN": "medium",
}


def _project_roadmap_catalog(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/roadmap_task_catalog/latest.json`` (A20a) into
    read-only catalog rows. One WorkItem per ``RoadmapTask``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    tasks = payload.get("roadmap_tasks") or []
    if not isinstance(tasks, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for task in tasks[:_ROADMAP_MAX_ROWS]:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        phase = str(task.get("phase") or "")
        status = str(task.get("status") or "not_started")
        title_text = str(task.get("title") or task_id)
        purpose = str(task.get("purpose") or "")

        short = _short_id_from("roadmap_task_catalog", task_id, phase)
        item_id = f"wi_rt_catalog_{short}"
        title = _truncate(
            f"Roadmap task · {phase} · {title_text}", MAX_TITLE_LEN
        )
        verdict = _truncate(
            f"phase={phase} status={status}", MAX_VERDICT_LEN
        )
        next_action = _truncate(
            "Read-only roadmap catalog row · informational",
            MAX_NEXT_ACTION_LEN,
        )
        summary = _truncate(
            purpose
            or (
                "Roadmap v6 task catalog row (A20a). Informational "
                "only; no implementation, runtime, trading, paper, "
                "shadow, broker, risk, or live authority is granted."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_rt_catalog_{short}"

        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "roadmap_task_catalog",
                "source_path": "logs/roadmap_task_catalog/latest.json",
                "current_stage": "discovered",
                "owner_role": "product_owner",
                "risk": "low",
                "human_needed": False,
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
                "read_only": True,
                "mutation_allowed": False,
                "phase": phase,
                "status": status,
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "product_owner",
                "module": "roadmap_task_catalog",
                "event_type": "discovered",
                "summary": verdict,
                "decision": "surface",
                "reason": _truncate(
                    "A20a read-only roadmap task catalog row",
                    MAX_REASON_LEN,
                ),
                "artifact_path": "logs/roadmap_task_catalog/latest.json",
                "severity": "info",
            }
        )

    return (work_items, events, [])


def _evidence_value_by_kind(evidence: Any, kind: str) -> str:
    """Return the first ``value`` for ``kind`` in an A20c evidence
    list, or the empty string."""
    if not isinstance(evidence, list):
        return ""
    for rec in evidence:
        if isinstance(rec, dict) and rec.get("kind") == kind:
            v = rec.get("value")
            if isinstance(v, str):
                return v
    return ""


def _project_roadmap_units(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/roadmap_task_units/latest.json`` (A20b) into
    read-only implementation-unit rows. One WorkItem per
    ``ImplementationUnit``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    units = payload.get("implementation_units") or []
    if not isinstance(units, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for unit in units[:_ROADMAP_MAX_ROWS]:
        if not isinstance(unit, dict):
            continue
        unit_id = str(unit.get("id") or "")
        if not unit_id:
            continue
        phase = str(unit.get("phase") or "")
        task_id = str(unit.get("roadmap_task_id") or "")
        risk_class = str(unit.get("risk_class") or "UNKNOWN")
        operator_gate = str(unit.get("operator_gate") or "none")
        authority_hint = str(unit.get("authority_hint") or "")
        title_text = str(unit.get("title") or unit_id)
        target_layer = str(unit.get("target_layer") or "")
        unit_status = str(unit.get("status") or "not_started")

        if authority_hint == "PERMANENTLY_DENIED_SURFACE":
            stage = "done_blocked"
            human_needed = False
        elif (
            authority_hint == "NEEDS_HUMAN_CANDIDATE"
            or operator_gate != "none"
        ):
            stage = "needs_human"
            human_needed = True
        else:
            stage = "discovered"
            human_needed = False

        aac_risk = _A20B_RISK_TO_AAC_RISK.get(risk_class, "medium")

        short = _short_id_from("roadmap_implementation_unit", unit_id, phase)
        item_id = f"wi_rt_unit_{short}"
        title = _truncate(
            f"Roadmap unit · {phase} · {title_text}", MAX_TITLE_LEN
        )
        verdict = _truncate(
            (
                f"hint={authority_hint or 'unknown'} "
                f"gate={operator_gate} risk={risk_class}"
            ),
            MAX_VERDICT_LEN,
        )
        next_action = _truncate(
            "Operator review · A20b unit hint"
            if human_needed
            else (
                "Awaiting A20c authority verdict"
                if stage == "done_blocked"
                else "Read-only unit row · informational"
            ),
            MAX_NEXT_ACTION_LEN,
        )
        summary = _truncate(
            (
                f"A20b implementation unit row. target_layer={target_layer} "
                "Hint is non-authoritative; A20c integrates the canonical "
                "Execution Authority verdict. No implementation, runtime, "
                "trading, paper, shadow, broker, risk, or live authority "
                "is granted."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_rt_unit_{short}"

        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "roadmap_implementation_unit",
                "source_path": "logs/roadmap_task_units/latest.json",
                "current_stage": stage,
                "owner_role": "planner",
                "risk": aac_risk,
                "human_needed": human_needed,
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
                "read_only": True,
                "mutation_allowed": False,
                "phase": phase,
                "roadmap_task_id": task_id,
                "risk_class": risk_class,
                "operator_gate": operator_gate,
                "authority_hint_a20b": authority_hint,
                "status": unit_status,
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "planner",
                "module": "roadmap_task_units",
                "event_type": "annotated",
                "summary": verdict,
                "decision": "require_human" if human_needed else "surface",
                "reason": _truncate(
                    f"A20b unit hint={authority_hint}",
                    MAX_REASON_LEN,
                ),
                "artifact_path": "logs/roadmap_task_units/latest.json",
                "severity": "human" if human_needed else "info",
            }
        )
        if human_needed:
            actions.append(
                {
                    "action_id": f"ha_rt_unit_{short}",
                    "item_id": item_id,
                    "severity": "medium",
                    "title": title,
                    "why_required": _truncate(
                        (
                            "A20b emitted a NEEDS_HUMAN_CANDIDATE hint or "
                            "operator_gate != none for this unit. Final "
                            "authority is settled by A20c. This row is "
                            "informational only — copy / inspect, never "
                            "execute."
                        ),
                        MAX_SUMMARY_LEN,
                    ),
                    # A20d MUST NOT synthesise a required phrase; the
                    # hint is non-authoritative metadata, not an
                    # operator-go phrase.
                    "required_phrase": None,
                    "safe_to_ignore": False,
                    "copy_only": True,
                    "source_artifact_path": (
                        "logs/roadmap_task_units/latest.json"
                    ),
                    "suggested_role": "planner",
                    "created_at": upstream_ts_str,
                }
            )

    return (work_items, events, actions)


def _project_roadmap_unit_authority(
    payload: dict[str, Any] | None,
    *,
    generated_at_utc: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Project ``logs/roadmap_unit_authority/latest.json`` (A20c)
    into read-only authority-verdict rows. One WorkItem per
    ``UnitAuthorityDecision``."""
    if not isinstance(payload, dict):
        return ([], [], [])
    decisions = payload.get("authority_decisions") or []
    if not isinstance(decisions, list):
        return ([], [], [])

    work_items: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    upstream_ts = payload.get("generated_at_utc")
    upstream_ts_str = (
        upstream_ts if isinstance(upstream_ts, str) else generated_at_utc
    )

    for decision in decisions[:_ROADMAP_MAX_ROWS]:
        if not isinstance(decision, dict):
            continue
        unit_id = str(decision.get("implementation_unit_id") or "")
        if not unit_id:
            continue
        task_id = str(decision.get("roadmap_task_id") or "")
        phase = str(decision.get("phase") or "")
        final_class = str(
            decision.get("final_authority_class") or "NEEDS_HUMAN"
        )
        requires_go = bool(decision.get("requires_operator_go"))
        permanently_denied = bool(decision.get("permanently_denied"))
        classifier_used = bool(decision.get("classifier_used"))
        fail_closed = bool(decision.get("fail_closed"))
        deny_reasons = decision.get("deny_reasons") or []
        if not isinstance(deny_reasons, list):
            deny_reasons = []
        evidence = decision.get("evidence")

        risk_class = _evidence_value_by_kind(evidence, "risk_class") or "UNKNOWN"
        operator_gate = (
            _evidence_value_by_kind(evidence, "operator_gate") or "none"
        )

        if permanently_denied:
            stage = "done_blocked"
            aac_risk = "high"
            human_needed = False
        elif requires_go:
            stage = "needs_human"
            aac_risk = _A20B_RISK_TO_AAC_RISK.get(risk_class, "medium")
            human_needed = True
        else:
            stage = "discovered"
            aac_risk = _A20B_RISK_TO_AAC_RISK.get(risk_class, "low")
            human_needed = False

        short = _short_id_from(
            "roadmap_unit_authority_decision", unit_id, final_class
        )
        item_id = f"wi_rt_auth_{short}"
        title = _truncate(
            f"Authority · {phase} · {unit_id}", MAX_TITLE_LEN
        )
        deny_join = ",".join(str(r) for r in deny_reasons[:4]) or "(none)"
        verdict = _truncate(
            (
                f"final={final_class} requires_operator_go={requires_go} "
                f"permanently_denied={permanently_denied} "
                f"deny_reasons={deny_join}"
            ),
            MAX_VERDICT_LEN,
        )
        if permanently_denied:
            next_action_text = (
                "Permanently denied · no implementation path under current policy"
            )
        elif requires_go:
            next_action_text = (
                "Operator-go required before any implementation PR may proceed"
            )
        else:
            next_action_text = (
                "AUTO_ALLOWED candidate · read-only display, normal PR review applies"
            )
        next_action = _truncate(next_action_text, MAX_NEXT_ACTION_LEN)
        summary = _truncate(
            (
                f"A20c authority verdict on A20b unit {unit_id}. "
                f"final_authority_class={final_class}; "
                f"classifier_used={classifier_used}; "
                f"fail_closed={fail_closed}. Display-only; A20d does "
                "not execute, merge, or grant runtime / trading / "
                "paper / shadow / live authority."
            ),
            MAX_SUMMARY_LEN,
        )
        event_id = f"ev_rt_auth_{short}"

        work_items.append(
            {
                "item_id": item_id,
                "title": title,
                "source_kind": "roadmap_unit_authority_decision",
                "source_path": "logs/roadmap_unit_authority/latest.json",
                "current_stage": stage,
                "owner_role": "architecture_guardian",
                "risk": aac_risk,
                "human_needed": human_needed,
                "latest_verdict": verdict,
                "next_action": next_action,
                "updated_at": upstream_ts_str,
                "summary": summary,
                "event_ids": [event_id],
                "read_only": True,
                "mutation_allowed": False,
                "phase": phase,
                "roadmap_task_id": task_id,
                "implementation_unit_id": unit_id,
                "final_authority_class": final_class,
                "risk_class": risk_class,
                "operator_gate": operator_gate,
                "requires_operator_go": requires_go,
                "permanently_denied": permanently_denied,
                "classifier_used": classifier_used,
                "fail_closed": fail_closed,
            }
        )
        events.append(
            {
                "event_id": event_id,
                "item_id": item_id,
                "timestamp": upstream_ts_str,
                "agent_role": "architecture_guardian",
                "module": "roadmap_unit_authority",
                "event_type": "verdict",
                "summary": verdict,
                "decision": (
                    "flag"
                    if permanently_denied
                    else ("require_human" if requires_go else "surface")
                ),
                "reason": _truncate(
                    f"A20c final_authority_class={final_class}",
                    MAX_REASON_LEN,
                ),
                "artifact_path": "logs/roadmap_unit_authority/latest.json",
                "severity": (
                    "warn"
                    if permanently_denied
                    else ("human" if requires_go else "info")
                ),
            }
        )
        if human_needed:
            actions.append(
                {
                    "action_id": f"ha_rt_auth_{short}",
                    "item_id": item_id,
                    "severity": "medium",
                    "title": title,
                    "why_required": _truncate(
                        (
                            "A20c authority verdict requires operator "
                            "review before any implementation PR for "
                            "this unit. Display-only here; no phrase "
                            "is synthesised."
                        ),
                        MAX_SUMMARY_LEN,
                    ),
                    "required_phrase": None,
                    "safe_to_ignore": False,
                    "copy_only": True,
                    "source_artifact_path": (
                        "logs/roadmap_unit_authority/latest.json"
                    ),
                    "suggested_role": "architecture_guardian",
                    "created_at": upstream_ts_str,
                }
            )

    return (work_items, events, actions)


# ---------------------------------------------------------------------------
# Artefact health, freshness, invariants, counts
# ---------------------------------------------------------------------------


def _compute_artifact_health(
    *,
    repo_root: Path,
    generated_at_utc: str,
    parsed: dict[str, tuple[str, dict[str, Any] | None, str | None]],
    jsonl_rows: dict[str, tuple[str, int, str | None]],
) -> list[dict[str, Any]]:
    """Build one ArtifactHealth row per catalog entry (11 rows)."""
    out: list[dict[str, Any]] = []
    for group, _kind, rel_path, _proj in UPSTREAM_CATALOG:
        full_path = repo_root / rel_path
        ttl = TTL_BY_GROUP.get(group, 1800)
        is_jsonl = rel_path.endswith(".jsonl")

        if is_jsonl:
            status, rows, err = jsonl_rows.get(rel_path, ("absent", 0, None))
            parse_ok = status != "malformed"
            payload: dict[str, Any] | None = None
        else:
            status, payload, err = parsed.get(rel_path, ("absent", None, None))
            parse_ok = status != "malformed"
            rows = 0
            if isinstance(payload, dict):
                # Try to derive a row count from common shapes.
                for key in ("rows", "candidates", "items"):
                    val = payload.get(key)
                    if isinstance(val, list):
                        rows = len(val)
                        break

        mtime = _file_mtime_iso(full_path)
        if mtime is None:
            fresh = False
        else:
            age = _utc_seconds_age(generated_at_utc, mtime)
            fresh = age <= ttl

        module_version = ""
        if isinstance(payload, dict):
            mv = payload.get("module_version")
            if isinstance(mv, str):
                module_version = mv

        has_summary = False
        if isinstance(payload, dict):
            has_summary = bool(
                payload.get("summary")
                or payload.get("note")
                or payload.get("readiness_note")
            )

        row: dict[str, Any] = {
            "path": rel_path,
            "group": group,
            "fresh": bool(fresh),
            "parse_ok": bool(parse_ok),
            "row_count": int(rows),
            "last_modified": mtime if mtime is not None else "",
            "module_version": module_version,
            "has_summary": bool(has_summary),
        }
        if err is not None:
            row["parse_error"] = _truncate(err, MAX_PARSE_ERROR_LEN)
        if group == "seed":
            row["read_only_warning"] = SEED_READ_ONLY_WARNING
        out.append(row)

    out.sort(key=lambda r: r["path"])
    return out[:MAX_ARTIFACT_HEALTH]


def _compute_freshness(
    *,
    generated_at_utc: str,
    artifact_health: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive the freshness block from artefact-health rows."""
    any_stale = False
    any_malformed = False
    oldest_age = 0
    ttl_map: dict[str, int] = {}
    for row in artifact_health:
        if not row.get("parse_ok"):
            any_malformed = True
        if not row.get("fresh"):
            any_stale = True
        path = row["path"]
        group = row["group"]
        ttl_map[path] = TTL_BY_GROUP.get(group, 1800)
        mtime = row.get("last_modified") or None
        if mtime:
            age = _utc_seconds_age(generated_at_utc, mtime)
            if age > oldest_age:
                oldest_age = age
    return {
        "generated_at_utc": generated_at_utc,
        "oldest_artifact_age_seconds": int(oldest_age),
        "any_stale": bool(any_stale),
        "any_malformed": bool(any_malformed),
        "background_refreshing": False,
        "ttl_seconds_by_path": dict(sorted(ttl_map.items())),
    }


def _compute_invariant_status(
    *,
    parsed: dict[str, tuple[str, dict[str, Any] | None, str | None]],
) -> list[dict[str, Any]]:
    """Build the 9-row closed InvariantStatus list. ``a18c_enabled``
    is sourced from the A18c artefact's ``enabled`` field when
    present; everything else is static."""
    a18c_status, a18c_payload, _ = parsed.get(
        "logs/development_generated_lane_a18c/latest.json",
        ("absent", None, None),
    )
    if a18c_status == "ok" and isinstance(a18c_payload, dict):
        a18c_value = bool(a18c_payload.get("enabled"))
        a18c_tone = "on" if a18c_value else "off"
    else:
        a18c_value = False
        a18c_tone = "unknown"

    invariants = [
        {
            "key": "level_6",
            "label": "Level 6",
            "value": "permanently_disabled",
            "tone": "danger_off",
            "detail": _truncate(
                (
                    "Level 6 stays permanently disabled per ADR-015 "
                    "Doctrine 1. Cannot be re-enabled by this UI or "
                    "any agent."
                ),
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "step5_substage",
            "label": "Step 5 substage",
            "value": STEP5_ENABLED_SUBSTAGE,
            "tone": "info",
            "detail": _truncate(
                "Current Step 5 substage cap. Default-deny is 'none'.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "step5_implementation_allowed",
            "label": "Step 5 impl. allowed",
            "value": step5_implementation_allowed,
            "tone": "off",
            "detail": _truncate(
                "Final constant; Step 5 plans stay dry-run only.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "live_merge_implemented",
            "label": "Live merge",
            "value": False,
            "tone": "off",
            "detail": _truncate(
                "Autonomous merge is not implemented; operator merges only.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "deploy_coupled",
            "label": "Deploy coupled to merge",
            "value": False,
            "tone": "off",
            "detail": _truncate(
                "Merge does not trigger deploy. Deploy is fully manual.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "a18c_enabled",
            "label": "A18c lane",
            "value": a18c_value,
            "tone": a18c_tone,
            "detail": _truncate(
                "Generated lane A18c. Value sourced from the A18c artefact.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "a18b_writer_enabled",
            "label": "A18b writer",
            "value": False,
            "tone": "off",
            "detail": _truncate(
                "A18b writer disabled by default; aggregator reads only.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "n5b_live_execute",
            "label": "N5b live execute",
            "value": False,
            "tone": "off",
            "detail": _truncate(
                "No live execution path is enabled.",
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
        {
            "key": "agent_service",
            "label": "Agent service",
            "value": "healthy",
            "tone": "on",
            "detail": _truncate(
                (
                    "Static placeholder in v0.1; a future revision "
                    "may wire to a heartbeat source."
                ),
                MAX_INVARIANT_DETAIL_LEN,
            ),
        },
    ]
    invariants.sort(key=lambda r: r["key"])
    return invariants[:MAX_INVARIANT_STATUS]


def _aggregate_counts(
    work_items: list[dict[str, Any]],
) -> dict[str, int]:
    """Compute the counts block from work_items[]."""
    by_stage = {stage: 0 for stage in STAGES}
    for w in work_items:
        stage = w.get("current_stage")
        if isinstance(stage, str) and stage in by_stage:
            by_stage[stage] += 1
    needs_human = sum(1 for w in work_items if w.get("human_needed"))
    total_open = sum(
        1 for w in work_items if w.get("current_stage") != "done_blocked"
    )
    return {
        "discovered": by_stage["discovered"],
        "queued": by_stage["queued"],
        "delegated": by_stage["delegated"],
        "planned": by_stage["planned"],
        "dry_run_ready": by_stage["dry_run_ready"],
        "pr_proposed": by_stage["pr_proposed"],
        "pr_opened": by_stage["pr_opened"],
        "ci_feedback": by_stage["ci_feedback"],
        "needs_human": needs_human,
        "merge_candidate": by_stage["merge_candidate"],
        "blocked": by_stage["done_blocked"],
        "total_open": total_open,
    }


def _vocabularies_block() -> dict[str, list[str]]:
    """Return the closed-vocabularies echo block."""
    return {
        "stage": list(STAGES),
        "severity": list(SEVERITIES),
        "decision": list(DECISIONS),
        "risk": list(RISKS),
        "freshness": list(FRESHNESS_STATES),
        "artifact_health": list(ARTIFACT_HEALTH_STATES),
        "human_action": list(HUMAN_ACTION_TYPES),
        "invariant_state": list(INVARIANT_STATES),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Pure scorer. Reads the closed 14-entry upstream catalog
    (11 ADE-core entries + 3 A20d read-only roadmap entries) and
    returns a sorted-key envelope dict satisfying the AAC schema."""
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    # Read every catalog entry exactly once.
    parsed: dict[
        str, tuple[str, dict[str, Any] | None, str | None]
    ] = {}
    jsonl_rows: dict[str, tuple[str, int, str | None]] = {}
    for _group, _kind, rel_path, _proj in UPSTREAM_CATALOG:
        full_path = root / rel_path
        if rel_path.endswith(".jsonl"):
            jsonl_rows[rel_path] = _count_jsonl_rows(full_path)
        else:
            parsed[rel_path] = _read_json(full_path)

    # Project the v0.1 projectable upstreams (4 only).
    work_items: list[dict[str, Any]] = []
    agent_events: list[dict[str, Any]] = []
    human_actions: list[dict[str, Any]] = []

    step5_status, step5_payload, _ = parsed.get(
        "logs/step5_loop/latest.json", ("absent", None, None)
    )
    if step5_status == "ok":
        wi, ev, ha = _project_step5_loop(
            step5_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    a18c_status, a18c_payload, _ = parsed.get(
        "logs/development_generated_lane_a18c/latest.json",
        ("absent", None, None),
    )
    if a18c_status == "ok":
        wi, ev, ha = _project_a18c(a18c_payload, generated_at_utc=ts)
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    prom_status, prom_payload, _ = parsed.get(
        "logs/development_generated_lane_promotion_report/latest.json",
        ("absent", None, None),
    )
    if prom_status == "ok":
        wi, ev, ha = _project_promotion_report(
            prom_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    mp_status, mp_payload, _ = parsed.get(
        "logs/development_merge_preflight/latest.json",
        ("absent", None, None),
    )
    if mp_status == "ok":
        wi, ev, ha = _project_merge_preflight(
            mp_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    # A20d — read-only roadmap visibility. Each projector handles
    # absent / malformed payload gracefully (returns empty lists);
    # the aggregator never raises on a missing roadmap upstream.
    rt_catalog_status, rt_catalog_payload, _ = parsed.get(
        "logs/roadmap_task_catalog/latest.json",
        ("absent", None, None),
    )
    if rt_catalog_status == "ok":
        wi, ev, ha = _project_roadmap_catalog(
            rt_catalog_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    rt_units_status, rt_units_payload, _ = parsed.get(
        "logs/roadmap_task_units/latest.json",
        ("absent", None, None),
    )
    if rt_units_status == "ok":
        wi, ev, ha = _project_roadmap_units(
            rt_units_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    rt_auth_status, rt_auth_payload, _ = parsed.get(
        "logs/roadmap_unit_authority/latest.json",
        ("absent", None, None),
    )
    if rt_auth_status == "ok":
        wi, ev, ha = _project_roadmap_unit_authority(
            rt_auth_payload, generated_at_utc=ts
        )
        work_items.extend(wi)
        agent_events.extend(ev)
        human_actions.extend(ha)

    # Deterministic ordering.
    work_items.sort(key=lambda w: w["item_id"])
    agent_events.sort(key=lambda e: (e["timestamp"], e["event_id"]))
    human_actions.sort(key=lambda a: a["action_id"])

    # Apply bounded caps.
    work_items = work_items[:MAX_WORK_ITEMS]
    agent_events = agent_events[:MAX_AGENT_EVENTS]
    human_actions = human_actions[:MAX_HUMAN_ACTIONS]

    artifact_health = _compute_artifact_health(
        repo_root=root,
        generated_at_utc=ts,
        parsed=parsed,
        jsonl_rows=jsonl_rows,
    )
    invariant_status = _compute_invariant_status(parsed=parsed)
    freshness = _compute_freshness(
        generated_at_utc=ts,
        artifact_health=artifact_health,
    )
    counts = _aggregate_counts(work_items)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "freshness": freshness,
        "counts": counts,
        "work_items": work_items,
        "agent_events": agent_events,
        "human_actions": human_actions,
        "artifact_health": artifact_health,
        "invariant_status": invariant_status,
        "vocabularies": _vocabularies_block(),
    }

    # Defense-in-depth: scrub the envelope before write.
    assert_no_secrets(snapshot)
    return snapshot


def write_outputs(snapshot: dict[str, Any]) -> Path:
    """Persist the snapshot to
    ``logs/development_agent_activity_timeline/latest.json``.
    Sentinel-restricted via ``_atomic_write_json``."""
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_agent_activity_timeline",
        description=(
            "Agent Activity Center read-only aggregator. Reads the "
            "closed 14-entry upstream catalog (11 ADE-core entries + "
            "3 A20d read-only roadmap entries) and writes "
            "logs/development_agent_activity_timeline/latest.json. "
            "NEVER mutates upstream state. NEVER opens, merges, or "
            "deploys anything. NEVER writes outside the canonical "
            "aggregator path. NEVER writes to any seed JSONL."
        ),
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_agent_activity_timeline/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    try:
        snap = collect_snapshot()
        if not args.no_write:
            write_outputs(snap)
        json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"development_agent_activity_timeline failed: {exc!r}\n"
        )
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
