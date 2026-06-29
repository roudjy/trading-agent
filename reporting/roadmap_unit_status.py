"""A21a — Dynamic Unit Status Ledger (read-only, deterministic).

Step 5 / A21 foundation. Records per-unit execution status as a
pinned Python literal seed so the A20e selector can advance past
completed units without editing
``reporting/roadmap_task_units.py`` (the A20b static decomposition).

Static unit definitions (catalog, decomposition) remain in
``reporting/roadmap_task_units.py``. **Dynamic execution status**
lives here. The two surfaces are deliberately separated so a unit
moving from ``not_started`` to ``merged`` no longer requires
touching the A20b seed every time.

This module is **Step 5 foundation only**. It does **not**:

* execute work;
* create branches;
* open PRs;
* run tests or governance lint;
* merge or deploy;
* call any LLM, external API, or hidden judgment;
* mutate any approval inbox, seed JSONL, queue, or upstream
  artefact;
* call the canonical ``execution_authority`` classifier;
* grant runtime / trading / paper / shadow / live authority;
* grant production-merge authority;
* activate Step 5 or Level 6 or relax any branch-protection
  invariant.

Hard guarantees (pinned by tests):

* Stdlib + (read-only) ``reporting.roadmap_task_units`` only —
  the only reason to read A20b is to expose the cross-reference
  module version on the projection; no A20b mutation, no
  per-unit status mirror.
* No subprocess, no network, no ``gh``, no ``git``, no
  ``os.system``, no dynamic-eval, no dynamic-exec, no API
  authorization headers.
* No imports of ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``, ``live``,
  ``paper``, ``shadow``, ``trading``,
  ``reporting.intelligent_routing``,
  ``reporting.execution_authority``,
  ``reporting.development_queue_admission_policy``,
  ``reporting.development_agent_activity_timeline``.
* Closed ``DYNAMIC_UNIT_STATUS`` vocabulary (7 values) and
  closed ``DYNAMIC_STATUS_SOURCE`` vocabulary (5 values).
* Atomic write only under ``logs/roadmap_unit_status/``.
* Deterministic output: same seed + injected
  ``generated_at_utc`` => byte-identical artefact.
* ``merged`` status requires non-empty ``pr_number``,
  non-empty ``merge_sha``, non-empty ``reason``.
* Duplicate records for the same ``unit_id`` fail closed
  deterministically (the duplicate ``unit_id`` is appended to
  ``duplicate_unit_ids`` and every record sharing that id is
  marked ``valid = False``).
* Invalid records are surfaced (``valid = False``) instead of
  silently dropped; the selector must fail closed on them.

CLI::

    python -m reporting.roadmap_unit_status
    python -m reporting.roadmap_unit_status --no-write
    python -m reporting.roadmap_unit_status --status
    python -m reporting.roadmap_unit_status --indent 2

Status transition rules (advisory; selector enforces buildable
filter on its own):

* ``not_started -> in_progress``
* ``in_progress -> pr_open``
* ``pr_open -> merged``
* ``pr_open -> failed``
* ``in_progress -> failed``
* ``not_started -> blocked``
* ``not_started -> skipped``
* ``failed -> blocked``
* ``blocked``, ``skipped``, ``merged`` are terminal unless an
  explicit operator override record is appended.
* No implicit resurrection of merged units. A duplicate record
  for a unit_id that already has a ``merged`` record fails closed
  via duplicate detection.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import roadmap_task_units as rtu

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A21a"
REPORT_KIND: Final[str] = "roadmap_unit_status"


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants (Final constants — never flipped at runtime)
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed dynamic unit-status vocabulary. 11 values.
#:
#: The four runner-lifecycle states (``selected``, ``branch_created``,
#: ``implementation_complete``, ``tests_passed``) are reserved for
#: Step 5 / A21 slices (A21c onwards). The A21c bounded PR runner
#: itself does NOT mutate the dynamic ledger today — the ledger
#: remains seed-driven — but the vocabulary widening lets future
#: slices record runner progress without another vocab change.
DYNAMIC_UNIT_STATUS: Final[tuple[str, ...]] = (
    "not_started",
    "selected",
    "branch_created",
    "in_progress",
    "implementation_complete",
    "tests_passed",
    "pr_open",
    "merged",
    "failed",
    "blocked",
    "skipped",
)

#: Statuses that are terminal unless an explicit operator override
#: is appended. The validator does not currently support overrides;
#: ``merged`` records that conflict with later records produce a
#: duplicate fail-closed verdict.
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"merged", "blocked", "skipped"}
)

#: Closed dynamic-source vocabulary. 6 values.
#:
#: ``runner_auto_merge`` is reserved for evidence records emitted by
#: the A21d auto-merge phase of
#: :mod:`reporting.autonomous_pr_runner`. Those records are appended
#: to a local-only artefact at
#: ``logs/roadmap_unit_status/runner_merges.json`` and read by
#: :func:`collect_snapshot` on top of the pinned seed.
DYNAMIC_STATUS_SOURCE: Final[tuple[str, ...]] = (
    "pr_merge",
    "operator_override",
    "loop_state",
    "ci_failure",
    "operator_block",
    "runner_auto_merge",
)

#: Closed per-record ``validation_reason`` vocabulary. ``""`` denotes
#: a valid record.
DYNAMIC_STATUS_INVALID_REASON: Final[tuple[str, ...]] = (
    "",
    "unknown_status",
    "unknown_source",
    "empty_unit_id",
    "merged_without_pr_number",
    "merged_without_merge_sha",
    "merged_without_reason",
    "duplicate_unit_id",
    "missing_updated_at_utc",
    "evidence_not_a_list",
    "pr_number_not_a_positive_int",
    "merge_sha_not_a_hex_string",
)

#: Closed source-of-truth artefact path (single output).
DYNAMIC_STATUS_OUTPUT_PATH: Final[str] = (
    "logs/roadmap_unit_status/latest.json"
)


# ---------------------------------------------------------------------------
# Schema field tuples (exact, ordered)
# ---------------------------------------------------------------------------

#: Per-record schema. Exact and ordered.
DYNAMIC_UNIT_STATUS_RECORD_FIELDS: Final[tuple[str, ...]] = (
    "unit_id",
    "status",
    "source",
    "updated_at_utc",
    "pr_number",
    "merge_sha",
    "reason",
    "evidence",
    "valid",
    "validation_reason",
)

#: Top-level projection schema. Exact and ordered.
ROADMAP_UNIT_STATUS_PROJECTION_FIELDS: Final[tuple[str, ...]] = (
    "generated_at_utc",
    "schema_version",
    "module_version",
    "source_units_module_version",
    "ledger_records",
    "duplicate_unit_ids",
    "invalid_record_count",
    "valid_record_count",
    "fail_closed",
    "ledger_invariants",
)


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

MAX_UNIT_ID_LEN: Final[int] = 128
MAX_REASON_LEN: Final[int] = 240
MAX_SHA_LEN: Final[int] = 64
MAX_SHA_MIN: Final[int] = 7
MAX_EVIDENCE_ITEMS: Final[int] = 8
MAX_EVIDENCE_ITEM_LEN: Final[int] = 240
MAX_PR_NUMBER: Final[int] = 1_000_000


# ---------------------------------------------------------------------------
# Artefact paths
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "roadmap_unit_status"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"

#: Auxiliary runner-merges artefact. Written by the A21d auto-merge
#: phase of :mod:`reporting.autonomous_pr_runner`. Local-only by
#: design: ``logs/`` is gitignored and CI projects only the pinned
#: seed. :func:`collect_snapshot` reads this file on top of the seed
#: when ``repo_root`` is provided.
RUNNER_MERGES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "roadmap_unit_status" / "runner_merges.json"
)
RUNNER_MERGES_REL_PATH: Final[str] = (
    "logs/roadmap_unit_status/runner_merges.json"
)
RUNNER_MERGES_SCHEMA_VERSION: Final[str] = "1.0"
RUNNER_MERGES_REPORT_KIND: Final[str] = "runner_auto_merge_evidence"

#: Atomic-write allowlist (POSIX substring). Any write target whose
#: path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/roadmap_unit_status/"


# ---------------------------------------------------------------------------
# Ledger invariants emitted on every projection
# ---------------------------------------------------------------------------

_BASE_LEDGER_INVARIANTS: Final[dict[str, bool]] = {
    "deterministic_projection": True,
    "no_random_ordering": True,
    "no_llm_judgment": True,
    "no_fuzzy_parsing": True,
    "no_work_execution": True,
    "no_branch_creation": True,
    "no_pr_creation": True,
    "no_merge_or_deploy": True,
    "no_mutation_routes": True,
    "no_approval_buttons": True,
    "no_runtime_trading_authority": True,
    "no_step5_runtime": True,
    "no_level6": True,
    "no_production_merge_authority": True,
    "step5_implementation_allowed": False,
    "mutates_a20b_artifact": False,
    "writes_only_roadmap_unit_status_log": True,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "writes_to_approval_inbox": False,
    "writes_to_work_queue_jsonl": False,
    "calls_llm_or_external_api": False,
    "uses_subprocess_or_network": False,
    "calls_execution_authority_classifier": False,
    "merged_status_requires_evidence": True,
    "duplicate_unit_id_fails_closed": True,
    "invalid_record_fails_closed": True,
    "no_implicit_merged_resurrection": True,
}


# ---------------------------------------------------------------------------
# Pinned status ledger seed
# ---------------------------------------------------------------------------
#
# Each record describes one observed execution-status fact for one
# implementation unit. Append-only by convention: appending a new
# record (e.g. flipping a unit to ``merged``) does NOT require editing
# ``reporting/roadmap_task_units.py``.
#
# Bootstrap records (3 entries) capture the three already-merged
# v3.15.16 routing-layer units. Their merge SHAs are pinned verbatim;
# editing them counts as evidence tampering and is rejected by review.

_STATUS_LEDGER_SEED: Final[tuple[dict[str, Any], ...]] = (
    {
        "unit_id": "u_v3_15_16_diagnostic_routing_signals_schema_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-05-18T11:46:10Z",
        "pr_number": 250,
        "merge_sha": "fcb1abbea4bd2ca190fe6e807b3dacd184faa702",
        "reason": "implemented by PR #250",
        "evidence": (
            "github_pr_number=250",
            "github_merge_sha=fcb1abbea4bd2ca190fe6e807b3dacd184faa702",
        ),
    },
    {
        "unit_id": "u_v3_15_16_routing_explanation_reporter_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-05-18T12:16:21Z",
        "pr_number": 252,
        "merge_sha": "6f588a89b43a2cfec40f92252bde530220877b37",
        "reason": "implemented by PR #252",
        "evidence": (
            "github_pr_number=252",
            "github_merge_sha=6f588a89b43a2cfec40f92252bde530220877b37",
        ),
    },
    {
        "unit_id": "u_v3_15_16_routing_governance_doc_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-05-18T14:36:27Z",
        "pr_number": 254,
        "merge_sha": "df7dc6562ec3cd3a9f87e83e758881bd6fdb16f8",
        "reason": "implemented by PR #254",
        "evidence": (
            "github_pr_number=254",
            "github_merge_sha=df7dc6562ec3cd3a9f87e83e758881bd6fdb16f8",
        ),
    },
    {
        "unit_id": "u_ade_qre_018a_queue_baseline_reconciliation_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018b_blocked_thesis_lineage_census_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018c_identity_ambiguity_resolution_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018d_campaign_lineage_materialization_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018e_null_control_readiness_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018f_evidence_reason_record_completion_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018g_validation_repro_operator_completion_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018h_campaign_portfolio_reconstruction_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018i_rejected_thesis_replacement_plan_001",
        "status": "merged",
        "source": "pr_merge",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        "reason": "implemented by PR #685",
        "evidence": (
            "github_pr_number=685",
            "github_merge_sha=ae26b0d94a631d15dcaff5842fb2d7f0b4d5113e",
        ),
    },
    {
        "unit_id": "u_ade_qre_018j_second_broad_campaign_prep_001",
        "status": "blocked",
        "source": "operator_block",
        "updated_at_utc": "2026-06-29T07:14:03Z",
        "pr_number": 685,
        "merge_sha": "",
        "reason": "blocked because ADE-QRE-018H produced zero READY_FOR_PREREGISTRATION cells",
        "evidence": (
            "github_pr_number=685",
            "portfolio_ready_cell_count=0",
            "second_campaign_manifest_materialized=false",
        ),
    },
)


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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _normalise_evidence(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        out.append(_bounded_str(item, MAX_EVIDENCE_ITEM_LEN))
        if len(out) >= MAX_EVIDENCE_ITEMS:
            break
    return out


def _is_hex_sha(value: str) -> bool:
    if not value:
        return False
    if not (MAX_SHA_MIN <= len(value) <= MAX_SHA_LEN):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in value)


# ---------------------------------------------------------------------------
# Per-record validation
# ---------------------------------------------------------------------------


def _validate_record(raw: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(valid, validation_reason)`` for a single record.

    ``validation_reason`` is a closed-vocab string from
    :data:`DYNAMIC_STATUS_INVALID_REASON`. ``""`` denotes a valid
    record. Duplicate detection happens at the projection layer,
    not here.
    """
    unit_id = _bounded_str(raw.get("unit_id"), MAX_UNIT_ID_LEN)
    if not unit_id:
        return False, "empty_unit_id"
    status = _bounded_str(raw.get("status"), 32)
    if status not in DYNAMIC_UNIT_STATUS:
        return False, "unknown_status"
    source = _bounded_str(raw.get("source"), 64)
    if source not in DYNAMIC_STATUS_SOURCE:
        return False, "unknown_source"
    updated_at = _bounded_str(raw.get("updated_at_utc"), 32)
    if not updated_at:
        return False, "missing_updated_at_utc"
    if status == "merged":
        pr_num = raw.get("pr_number")
        if not isinstance(pr_num, int) or pr_num <= 0 or pr_num > MAX_PR_NUMBER:
            return False, "pr_number_not_a_positive_int"
        sha = _bounded_str(raw.get("merge_sha"), MAX_SHA_LEN)
        if not sha:
            return False, "merged_without_merge_sha"
        if not _is_hex_sha(sha):
            return False, "merge_sha_not_a_hex_string"
        reason = _bounded_str(raw.get("reason"), MAX_REASON_LEN)
        if not reason:
            return False, "merged_without_reason"
    evidence_raw = raw.get("evidence")
    if evidence_raw is not None and not isinstance(
        evidence_raw, (list, tuple)
    ):
        return False, "evidence_not_a_list"
    return True, ""


# ---------------------------------------------------------------------------
# Record normalisation
# ---------------------------------------------------------------------------


def _normalise_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw seed record into a deterministic emitted record.

    Always returns a fully-shaped record (every field in
    :data:`DYNAMIC_UNIT_STATUS_RECORD_FIELDS` is present). Invalid
    records keep their declared fields where possible but carry
    ``valid = False`` and a validation_reason in closed vocab.
    """
    valid, reason = _validate_record(raw)
    unit_id = _bounded_str(raw.get("unit_id"), MAX_UNIT_ID_LEN)
    status = _bounded_str(raw.get("status"), 32)
    source = _bounded_str(raw.get("source"), 64)
    updated_at = _bounded_str(raw.get("updated_at_utc"), 32)
    pr_number_raw = raw.get("pr_number")
    if isinstance(pr_number_raw, int) and pr_number_raw > 0:
        pr_number = pr_number_raw
    else:
        pr_number = 0
    sha = _bounded_str(raw.get("merge_sha"), MAX_SHA_LEN)
    record_reason = _bounded_str(raw.get("reason"), MAX_REASON_LEN)
    evidence = _normalise_evidence(raw.get("evidence"))
    return {
        "unit_id": unit_id,
        "status": status if status in DYNAMIC_UNIT_STATUS else "",
        "source": source if source in DYNAMIC_STATUS_SOURCE else "",
        "updated_at_utc": updated_at,
        "pr_number": pr_number,
        "merge_sha": sha,
        "reason": record_reason,
        "evidence": evidence,
        "valid": valid,
        "validation_reason": reason if reason in DYNAMIC_STATUS_INVALID_REASON
        else "",
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _load_runner_merges_artifact(
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Best-effort read of the optional A21d runner-merges artefact.

    Returns the list of record dicts. Returns an empty list when the
    artefact is absent, malformed, or has the wrong shape (defensive:
    the file is local-only and may be regenerated by the runner).
    """
    path = repo_root / RUNNER_MERGES_REL_PATH
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    if not isinstance(payload, dict):
        return []
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def collect_snapshot(
    *,
    seed: tuple[dict[str, Any], ...] | None = None,
    generated_at_utc: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build the deterministic dynamic unit-status projection.

    ``seed`` is the pinned ``_STATUS_LEDGER_SEED`` by default;
    tests override this to exercise validation paths.

    ``repo_root`` is optional. When provided, the projection
    overlays records from the A21d runner-merges artefact at
    ``logs/roadmap_unit_status/runner_merges.json`` on top of the
    seed. Tests that pass ``seed=`` typically do NOT pass
    ``repo_root`` and therefore see no overlay.
    """
    if seed is not None:
        src_records: list[dict[str, Any]] = list(seed)
    else:
        src_records = list(_STATUS_LEDGER_SEED)
    if repo_root is not None:
        overlay = _load_runner_merges_artifact(repo_root)
        src_records.extend(overlay)
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    normalised: list[dict[str, Any]] = []
    for raw in src_records:
        if not isinstance(raw, dict):
            normalised.append(
                {
                    "unit_id": "",
                    "status": "",
                    "source": "",
                    "updated_at_utc": "",
                    "pr_number": 0,
                    "merge_sha": "",
                    "reason": "",
                    "evidence": [],
                    "valid": False,
                    "validation_reason": "empty_unit_id",
                }
            )
            continue
        normalised.append(_normalise_record(raw))

    # Duplicate detection.
    seen_unit_ids: dict[str, int] = {}
    for rec in normalised:
        uid = rec["unit_id"]
        if not uid:
            continue
        seen_unit_ids[uid] = seen_unit_ids.get(uid, 0) + 1
    duplicate_unit_ids = sorted(
        uid for uid, count in seen_unit_ids.items() if count > 1
    )
    if duplicate_unit_ids:
        dup_set = set(duplicate_unit_ids)
        for rec in normalised:
            if rec["unit_id"] in dup_set:
                rec["valid"] = False
                rec["validation_reason"] = "duplicate_unit_id"

    # Stable deterministic sort: by unit_id, then updated_at_utc.
    normalised.sort(
        key=lambda r: (r["unit_id"], r["updated_at_utc"], r["status"])
    )

    invalid_count = sum(1 for r in normalised if not r["valid"])
    valid_count = sum(1 for r in normalised if r["valid"])
    fail_closed = bool(duplicate_unit_ids) or invalid_count > 0

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "source_units_module_version": rtu.MODULE_VERSION,
        "vocabularies": {
            "dynamic_unit_status": list(DYNAMIC_UNIT_STATUS),
            "dynamic_status_source": list(DYNAMIC_STATUS_SOURCE),
            "dynamic_status_invalid_reason": list(
                DYNAMIC_STATUS_INVALID_REASON
            ),
        },
        "ledger_records": normalised,
        "duplicate_unit_ids": list(duplicate_unit_ids),
        "invalid_record_count": invalid_count,
        "valid_record_count": valid_count,
        "fail_closed": fail_closed,
        "ledger_invariants": dict(_BASE_LEDGER_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write ``payload`` as sorted-key indented JSON.
    Refuses any path outside ``logs/roadmap_unit_status/``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix:
        raise ValueError(
            "roadmap_unit_status._atomic_write_json refuses "
            f"non-ledger-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".roadmap_unit_status.",
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


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# A21d runner-merges artefact helpers (write)
# ---------------------------------------------------------------------------


def append_runner_merge_record(
    record: dict[str, Any],
    *,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> Path:
    """Append a runner-merge evidence record to the auxiliary
    artefact at ``logs/roadmap_unit_status/runner_merges.json``.

    Validates the record first via :func:`_validate_record`. Refuses
    appending when:

    * the record fails per-record validation;
    * the record's ``source`` is not ``"runner_auto_merge"`` (this
      surface is reserved for the A21d runner; other sources go
      through the seed);
    * the record's ``status`` is not ``"merged"`` (this surface
      records terminal-merged evidence only; other statuses go
      through the seed);
    * a record with the same ``unit_id`` already exists in the
      artefact (no implicit resurrection of merged units).

    Refusals raise :class:`ValueError`. On success the artefact is
    written atomically to the allowlisted path and returned.
    """
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    valid, reason = _validate_record(record)
    if not valid:
        raise ValueError(
            f"runner_merge_record_invalid:{reason}"
        )
    if record.get("source") != "runner_auto_merge":
        raise ValueError(
            "runner_merge_record_source_must_be_runner_auto_merge"
        )
    if record.get("status") != "merged":
        raise ValueError(
            "runner_merge_record_status_must_be_merged"
        )

    existing = _load_runner_merges_artifact(root)
    unit_id = _bounded_str(record.get("unit_id"), MAX_UNIT_ID_LEN)
    for prior in existing:
        if isinstance(prior, dict) and prior.get("unit_id") == unit_id:
            raise ValueError(
                "runner_merge_record_unit_id_already_present"
            )

    normalised = _normalise_record(record)
    # Strip the runtime-computed validity flags from the persisted
    # form so it round-trips losslessly on subsequent loads.
    persisted = {k: v for k, v in normalised.items() if k not in {
        "valid", "validation_reason"
    }}

    out_records = list(existing) + [persisted]
    payload = {
        "schema_version": RUNNER_MERGES_SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": RUNNER_MERGES_REPORT_KIND,
        "generated_at_utc": ts,
        "records": out_records,
    }
    target = root / RUNNER_MERGES_REL_PATH
    _atomic_write_json(target, payload)
    return target


# ---------------------------------------------------------------------------
# Status renderer
# ---------------------------------------------------------------------------


def _render_status(snapshot: dict[str, Any]) -> str:
    inv = snapshot["ledger_invariants"]
    recs = snapshot["ledger_records"]
    lines = [
        f"roadmap_unit_status {snapshot['module_version']} "
        f"schema={snapshot['schema_version']}",
        f"generated_at_utc={snapshot['generated_at_utc']}",
        (
            f"records_total={len(recs)} "
            f"valid={snapshot['valid_record_count']} "
            f"invalid={snapshot['invalid_record_count']} "
            f"fail_closed={snapshot['fail_closed']}"
        ),
        f"duplicate_unit_ids={','.join(snapshot['duplicate_unit_ids']) or '-'}",
        (
            "no_runtime_trading_authority="
            f"{inv['no_runtime_trading_authority']} "
            f"no_step5_runtime={inv['no_step5_runtime']} "
            f"no_level6={inv['no_level6']} "
            "no_production_merge_authority="
            f"{inv['no_production_merge_authority']}"
        ),
        (
            "no_work_execution="
            f"{inv['no_work_execution']} "
            f"no_branch_creation={inv['no_branch_creation']} "
            f"no_pr_creation={inv['no_pr_creation']} "
            f"no_merge_or_deploy={inv['no_merge_or_deploy']}"
        ),
        (
            "merged_status_requires_evidence="
            f"{inv['merged_status_requires_evidence']} "
            "duplicate_unit_id_fails_closed="
            f"{inv['duplicate_unit_id_fails_closed']} "
            "invalid_record_fails_closed="
            f"{inv['invalid_record_fails_closed']} "
            "no_implicit_merged_resurrection="
            f"{inv['no_implicit_merged_resurrection']}"
        ),
    ]
    for r in recs:
        lines.append(
            f"  rec {r['unit_id']} status={r['status']} "
            f"source={r['source']} pr={r['pr_number']} "
            f"sha={r['merge_sha'][:7] if r['merge_sha'] else '-'} "
            f"valid={r['valid']}"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.roadmap_unit_status",
        description=(
            "A21a Dynamic Unit Status Ledger. Read-only deterministic "
            "projection over a pinned seed of per-unit execution "
            "statuses. Does NOT execute work, does NOT create "
            "branches, does NOT open PRs, does NOT merge or deploy. "
            "Step 5 implementation remains BLOCKED."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout output (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/roadmap_unit_status/latest.json "
            "(stdout only)."
        ),
    )
    p.add_argument(
        "--status",
        action="store_true",
        help=(
            "Render a compact human-readable status summary to stdout "
            "and exit. Does not write any artefact."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snap = collect_snapshot()
    if args.status:
        sys.stdout.write(_render_status(snap))
        return 0
    indent = args.indent if args.indent and args.indent > 0 else None
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
