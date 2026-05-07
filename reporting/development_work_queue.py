"""A8 — Autonomous Development Operating Queue Foundation.

Read-only, deterministic Kanban-style **development** work queue. This
module exposes a closed vocabulary, a frozen per-item schema, an
explicit operator-authored seed input, and an artifact under
``logs/development_work_queue/latest.json``.

Distinct from:

* ``reporting.proposal_queue`` — roadmap-document intake of proposals.
* the QRE research campaign queue — research execution ordering.
* the Intelligent Routing Layer queue — advisory research routing.

This is the autonomous **development** queue: roadmap/build/maintenance
work items, routed to agent roles by mandate, and progressed through
deterministic gates. A8 ships the schema + vocabularies + a read-only
CLI; auto-execute and auto-merge are out of scope.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` + ``reporting.approval_policy``.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``.
* No mutation behaviour, no approval-inbox decisions.
* Only canonical roadmap paths are accepted as ``source_document``;
  archive paths under ``docs/roadmap/archive/`` are rejected.
* Plain headings in the canonical roadmap docs do **not** become
  queue items. Items only come from explicit operator-authored
  entries in the sidecar seed file.
* Bounded scalars only — no PR text, no diffs, no body content.

CLI::

    python -m reporting.development_work_queue
    python -m reporting.development_work_queue --indent 2
    python -m reporting.development_work_queue --no-write
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

from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A8"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: 16 agent mandates. Mirrors ``.claude/agents/*`` plus ``human_operator``.
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

#: 12 Kanban-style item statuses.
STATUSES: Final[tuple[str, ...]] = (
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

#: 10 development work categories.
CATEGORIES: Final[tuple[str, ...]] = (
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

#: 11 human-needed reasons. ``"none"`` is reserved for ``human_needed=False``.
HUMAN_NEEDED_REASONS: Final[tuple[str, ...]] = (
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

#: Roadmap tracks the items can claim as their source.
ROADMAP_TRACKS: Final[tuple[str, ...]] = (
    "autonomous_development",
    "qre_feature_build",
    "sidecar_seed",
)

#: Risk levels are reused verbatim from the Execution Authority classifier.
RISK_LEVELS: Final[tuple[str, ...]] = ea.RISK_CLASSES

#: Per-item schema keys, exact and ordered.
ITEM_SCHEMA_KEYS: Final[tuple[str, ...]] = (
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

#: Deterministic placeholders for per-item timestamps. The wrapper
#: artifact carries ``generated_at_utc`` for the report itself; items
#: stay byte-reproducible across runs.
ITEM_TIME_PLACEHOLDER: Final[str] = "deterministic_seed_placeholder"

#: Bounded length for free-text fields on a single item. Keeps the
#: artifact small and the evidence audit-friendly.
MAX_TITLE_LEN: Final[int] = 200
MAX_NOTES_LEN: Final[int] = 1000
MAX_ACCEPTANCE_ITEMS: Final[int] = 16
MAX_ACCEPTANCE_LINE_LEN: Final[int] = 200
MAX_BLOCKED_BY: Final[int] = 16

#: Canonical roadmap paths the queue accepts as ``source_document``
#: when ``roadmap_track in {autonomous_development, qre_feature_build}``.
CANONICAL_ROADMAP_PATHS: Final[tuple[str, ...]] = (
    "docs/roadmap/autonomous_development.txt",
    "docs/roadmap/Roadmap v6.md",
)

#: Default seed file path. Optional. Absent = zero items.
DEFAULT_SEED_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "development_work_queue" / "seed.jsonl"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_work_queue"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_work_queue/latest.json"

#: Marker emitted on the report wrapper when no items are present.
NOTE_NO_ITEMS: Final[str] = "no_explicit_queue_items_found"
NOTE_ITEMS_PRESENT: Final[str] = "explicit_seed_items_present"
NOTE_SEED_FILE_ABSENT: Final[str] = "seed_file_absent"
NOTE_SEED_FILE_EMPTY: Final[str] = "seed_file_empty"

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


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./") if p else ""


def _is_archive_path(p: str) -> bool:
    n = _normalize_path(p).lower()
    return n.startswith("docs/roadmap/archive/")


def _is_canonical_roadmap_path(p: str) -> bool:
    return _normalize_path(p) in CANONICAL_ROADMAP_PATHS


def _bounded_str(value: Any, max_len: int) -> str:
    """Coerce to ``str`` and enforce a hard length bound. Non-strings
    yield an empty string. The classifier keeps body content out of
    the artifact; this helper is the second line of defence."""
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _bounded_str_list(
    value: Any, max_items: int, max_line_len: int
) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value[:max_items]:
        if isinstance(v, str):
            out.append(_bounded_str(v, max_line_len))
    return out


def _bounded_id_list(value: Any, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value[:max_items]:
        if isinstance(v, str) and v.strip():
            out.append(_bounded_str(v, 64))
    return out


def _bounded_role_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in value:
        if not isinstance(v, str):
            continue
        if v not in AGENT_ROLES:
            continue
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def _coerce_priority(value: Any) -> int:
    """Bound priority to the inclusive range [1, 5]. Non-ints map to 3."""
    if isinstance(value, bool):
        return 3
    if isinstance(value, int):
        if value < 1:
            return 1
        if value > 5:
            return 5
        return value
    return 3


def _deterministic_item_id(title: str, source_section: str) -> str:
    h = hashlib.sha256()
    h.update(title.encode("utf-8"))
    h.update(b"\x1f")
    h.update(source_section.encode("utf-8"))
    return "dwq_" + h.hexdigest()[:12]


# ---------------------------------------------------------------------------
# Item parsing and validation
# ---------------------------------------------------------------------------


def _validate_and_normalize_item(
    raw: dict[str, Any],
    *,
    line_index: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return a normalized item dict plus a list of warnings.

    Items that fail closed-vocabulary checks are dropped (return
    ``None``) with a warning; items that pass become a fully-typed
    schema-conformant dict. Never raises on user input."""
    warnings: list[str] = []

    if not isinstance(raw, dict):
        warnings.append(f"seed_line_{line_index}_not_an_object")
        return None, warnings

    title = _bounded_str(raw.get("title"), MAX_TITLE_LEN)
    if not title:
        warnings.append(f"seed_line_{line_index}_missing_title")
        return None, warnings

    track = raw.get("roadmap_track")
    if track not in ROADMAP_TRACKS:
        warnings.append(f"seed_line_{line_index}_invalid_roadmap_track")
        return None, warnings

    source_document = _normalize_path(
        raw.get("source_document") if isinstance(raw.get("source_document"), str) else ""
    )
    if track == "sidecar_seed":
        if source_document and source_document not in ("sidecar_seed", ""):
            # Tolerated: operator may point sidecar entries at any path.
            pass
        if not source_document:
            source_document = "sidecar_seed"
    else:
        if _is_archive_path(source_document):
            warnings.append(f"seed_line_{line_index}_archive_path_rejected")
            return None, warnings
        if not _is_canonical_roadmap_path(source_document):
            warnings.append(
                f"seed_line_{line_index}_non_canonical_source_document"
            )
            return None, warnings

    section = _bounded_str(raw.get("source_section_or_anchor"), MAX_TITLE_LEN)

    category = raw.get("category")
    if category not in CATEGORIES:
        warnings.append(f"seed_line_{line_index}_invalid_category")
        return None, warnings

    required_role = raw.get("required_agent_role")
    if required_role not in AGENT_ROLES:
        warnings.append(f"seed_line_{line_index}_invalid_required_agent_role")
        return None, warnings

    supporting = _bounded_role_list(raw.get("supporting_agent_roles"))

    status = raw.get("status")
    if status not in STATUSES:
        warnings.append(f"seed_line_{line_index}_invalid_status")
        return None, warnings

    risk_level = raw.get("risk_level")
    if risk_level not in RISK_LEVELS:
        warnings.append(f"seed_line_{line_index}_invalid_risk_level")
        return None, warnings

    human_needed = raw.get("human_needed")
    if not isinstance(human_needed, bool):
        warnings.append(f"seed_line_{line_index}_invalid_human_needed")
        return None, warnings

    human_needed_reason = raw.get("human_needed_reason")
    if human_needed_reason not in HUMAN_NEEDED_REASONS:
        warnings.append(f"seed_line_{line_index}_invalid_human_needed_reason")
        return None, warnings

    if human_needed and human_needed_reason == "none":
        warnings.append(f"seed_line_{line_index}_human_needed_true_but_reason_none")
        return None, warnings
    if (not human_needed) and human_needed_reason != "none":
        warnings.append(
            f"seed_line_{line_index}_human_needed_false_but_reason_not_none"
        )
        return None, warnings

    protected_surface = raw.get("protected_surface")
    if not isinstance(protected_surface, bool):
        warnings.append(f"seed_line_{line_index}_invalid_protected_surface")
        return None, warnings

    blocked_by = _bounded_id_list(raw.get("blocked_by"), MAX_BLOCKED_BY)
    acceptance = _bounded_str_list(
        raw.get("acceptance_criteria"),
        MAX_ACCEPTANCE_ITEMS,
        MAX_ACCEPTANCE_LINE_LEN,
    )
    validation = _bounded_str_list(
        raw.get("validation_requirements"),
        MAX_ACCEPTANCE_ITEMS,
        MAX_ACCEPTANCE_LINE_LEN,
    )

    notes = _bounded_str(raw.get("notes"), MAX_NOTES_LEN)

    priority = _coerce_priority(raw.get("priority"))

    # Cross-validate against execution_authority. The decision becomes
    # an additive field on the item; never silently rewrites the
    # operator's declared status.
    decision = ea.classify(
        action_type="file_edit",
        target_path=source_document if source_document else None,
        risk_class=risk_level,
    )

    item_id = _deterministic_item_id(title, section)

    item: dict[str, Any] = {
        "item_id": item_id,
        "title": title,
        "source_document": source_document,
        "source_section_or_anchor": section,
        "roadmap_track": track,
        "category": category,
        "required_agent_role": required_role,
        "supporting_agent_roles": supporting,
        "execution_authority": decision.decision,
        "status": status,
        "human_needed": human_needed,
        "human_needed_reason": human_needed_reason,
        "blocked_by": blocked_by,
        "priority": priority,
        "risk_level": risk_level,
        "protected_surface": protected_surface,
        "acceptance_criteria": acceptance,
        "validation_requirements": validation,
        "created_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "updated_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "notes": notes,
    }

    if not acceptance:
        warnings.append(f"item_{item_id}_missing_acceptance_criteria")
    if (
        decision.decision == ea.DECISION_AUTO_ALLOWED
        and human_needed is True
    ):
        warnings.append(
            f"item_{item_id}_human_needed_true_but_authority_auto_allowed"
        )
    if (
        decision.decision == ea.DECISION_PERMANENTLY_DENIED
        and human_needed is False
    ):
        warnings.append(
            f"item_{item_id}_human_needed_false_but_authority_denied"
        )

    return item, warnings


def _read_seed_lines(path: Path) -> tuple[list[str], bool]:
    """Read non-blank lines from a strict JSONL seed file.

    Each line must be either blank (tolerated) or a single JSON
    object (parsed downstream). A second tuple member reports
    whether the file existed at all."""
    if not path.is_file():
        return [], False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return [], True
    out: list[str] = []
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s:
            continue
        out.append(s)
    return out, True


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_status": {s: 0 for s in STATUSES},
        "by_role": {r: 0 for r in AGENT_ROLES},
        "by_category": {c: 0 for c in CATEGORIES},
        "human_needed": 0,
        "blocked": 0,
        "protected_surface": 0,
        "ready_for_autonomous_action": 0,
        "requiring_human_operator": 0,
        "execution_authority": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
    }


_AUTONOMOUS_READY_STATUSES: Final[frozenset[str]] = frozenset(
    {"ready", "in_progress"}
)


def _aggregate_counts(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(items)
    for it in items:
        counts["by_status"][it["status"]] += 1
        counts["by_role"][it["required_agent_role"]] += 1
        counts["by_category"][it["category"]] += 1
        counts["execution_authority"][it["execution_authority"]] += 1
        if it["human_needed"]:
            counts["human_needed"] += 1
        if it["status"] == "blocked":
            counts["blocked"] += 1
        if it["protected_surface"]:
            counts["protected_surface"] += 1
        if (
            it["execution_authority"] == ea.DECISION_AUTO_ALLOWED
            and not it["human_needed"]
            and it["status"] in _AUTONOMOUS_READY_STATUSES
        ):
            counts["ready_for_autonomous_action"] += 1
        if (
            it["human_needed"]
            or it["execution_authority"] == ea.DECISION_NEEDS_HUMAN
            or it["status"] == "human_needed"
        ):
            counts["requiring_human_operator"] += 1
    return counts


def collect_snapshot(
    *,
    seed_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic snapshot dict.

    The pure generator is byte-stable when called twice with the
    same inputs **including** an injected ``generated_at_utc``. The
    runtime CLI defaults the timestamp to the current UTC clock,
    which means CLI invocations are *not* byte-identical across
    different wall-clock seconds — that is intentional. Tests
    asserting byte-stable output must inject ``generated_at_utc``.

    Args:
        seed_path: override the default
            ``docs/development_work_queue/seed.jsonl`` source. Tests
            point this at a synthetic fixture path.
        generated_at_utc: override the wrapper's report timestamp.
            ``None`` (the default) reads the current UTC clock.
            Tests pass a fixed string to assert byte-stable output.
    """
    sp = seed_path if seed_path is not None else DEFAULT_SEED_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    seed_lines, seed_present = _read_seed_lines(sp)
    warnings: list[str] = []
    items: list[dict[str, Any]] = []

    for idx, line in enumerate(seed_lines, start=1):
        try:
            payload = json.loads(line)
        except ValueError:
            warnings.append(f"seed_line_{idx}_invalid_json")
            continue
        item, item_warns = _validate_and_normalize_item(
            payload, line_index=idx
        )
        warnings.extend(item_warns)
        if item is not None:
            items.append(item)

    items.sort(key=lambda it: (it["priority"], it["item_id"]))

    if not seed_present:
        note = NOTE_SEED_FILE_ABSENT
    elif not seed_lines:
        note = NOTE_SEED_FILE_EMPTY
    elif not items:
        note = NOTE_NO_ITEMS
    else:
        note = NOTE_ITEMS_PRESENT

    counts = _aggregate_counts(items)

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_work_queue",
        "generated_at_utc": ts,
        "source_document_paths": list(CANONICAL_ROADMAP_PATHS),
        "seed_path": str(sp.relative_to(REPO_ROOT)) if sp.is_relative_to(REPO_ROOT) else str(sp),
        "seed_present": seed_present,
        "source_available": True,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "agent_roles": list(AGENT_ROLES),
            "statuses": list(STATUSES),
            "categories": list(CATEGORIES),
            "human_needed_reasons": list(HUMAN_NEEDED_REASONS),
            "risk_levels": list(RISK_LEVELS),
            "roadmap_tracks": list(ROADMAP_TRACKS),
        },
        "counts": counts,
        "items": items,
        "execution_authority_module_version": ea.MODULE_VERSION,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_work_queue._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_work_queue.", suffix=".tmp", dir=str(path.parent)
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
        prog="python -m reporting.development_work_queue",
        description=(
            "Read-only Autonomous Development Operating Queue. Reads "
            "the operator-authored sidecar seed and produces a "
            "deterministic Kanban-style work-item queue. Decides "
            "nothing; mutates nothing."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_work_queue/latest.json "
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
