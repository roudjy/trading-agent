"""Step 5.0.1 — Roadmap Intake Bridge (read-only, deterministic).

Pure, stdlib-only roadmap-to-candidate bridge. Converts explicit,
machine-readable ``<!-- ade_roadmap_intake ... -->`` markers inside
Roadmap v6, the Roadmap v6 Addendum, the QRE phase-prompts doc, and
the QRE ADE operating-manual doc into bounded ADE candidate work
items.

This module is the **only** path by which ADE picks up real roadmap
work without operator-authored sidecar seeds. **No fuzzy parsing.**
Plain Markdown headings, prose, lists, and bullet points produce
zero candidates. Archive paths are excluded. Anything not inside an
explicit marker is invisible to this module.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` +
  ``reporting.approval_policy`` + ``reporting.development_work_queue``
  (read-only) + ``reporting.development_delegation`` (read-only).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* No mutation of any upstream roadmap, phase-prompt, or operating-
  manual document. Read-only.
* No promotion into ``docs/development_work_queue/seed.jsonl`` or
  ``docs/development_work_queue/delegation_seed.jsonl``. Promotion
  remains an explicit operator action.
* Atomic write only under ``logs/development_roadmap_intake/``.
* Roadmap v6 remains canonical; the Addendum is treated as an
  extension, not a replacement.
* Step 5.0.1 carries ``step5_implementation_allowed = False`` and
  ``STEP5_ENABLED_SUBSTAGE = "none"`` invariants. Step 5.1 / 5.2
  remain BLOCKED.

CLI::

    python -m reporting.development_roadmap_intake
    python -m reporting.development_roadmap_intake --no-write
    python -m reporting.development_roadmap_intake --indent 0
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import development_work_queue as dwq
from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A14.5_0_1"
REPORT_KIND: Final[str] = "development_roadmap_intake"

# ---------------------------------------------------------------------------
# Step 5 invariants (re-asserted on every artefact)
# ---------------------------------------------------------------------------

#: Step 5 sub-stage cap. Default-deny. Mirrors
#: ``reporting.development_step5_loop`` so the artefact is self-attesting.
STEP5_ENABLED_SUBSTAGE: Final[str] = "none"

#: Hard-pinned literal: Step 5 implementation is NOT allowed beyond
#: the dry-run / planner-only Step 5.0 surface plus the read-only
#: intake bridge. Flipping this constant requires a code change pinned
#: by a test update AND an ADR-015 amendment AND a fresh release-gate
#: report.
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Sources (closed)
# ---------------------------------------------------------------------------

#: Closed source-kind vocabulary. Adding a value requires a code
#: change pinned by an updated test.
SOURCE_KINDS: Final[tuple[str, ...]] = (
    "roadmap_v6",
    "roadmap_v6_addendum",
    "phase_prompt",
    "operating_manual",
)

#: Mapping from canonical source path → source_kind. The parser refuses
#: any path not listed here. Existing Roadmap v6 stays canonical;
#: Addendum is an extension, not a replacement.
SOURCE_PATH_TO_KIND: Final[dict[str, str]] = {
    "docs/roadmap/Roadmap v6.md": "roadmap_v6",
    "docs/roadmap/Roadmap v6 Addendum.md": "roadmap_v6_addendum",
    "docs/roadmap/qre_roadmap_v6_phase_prompts.md": "phase_prompt",
    "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md": "operating_manual",
}

#: Default canonical source paths, in deterministic order.
DEFAULT_SOURCE_PATHS: Final[tuple[str, ...]] = tuple(
    sorted(SOURCE_PATH_TO_KIND.keys())
)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Intake-status closed vocabulary.
INTAKE_STATUSES: Final[tuple[str, ...]] = (
    "proposed",
    "eligible",
    "blocked",
    "human_needed",
    "rejected",
)

#: Candidate-kind closed vocabulary. Read-only governance work only.
#: Notably absent: live, paper, shadow, risk, broker, execution,
#: trading. Diagnostics do not trade.
CANDIDATE_KINDS: Final[tuple[str, ...]] = (
    "docs",
    "reporting",
    "governance",
    "observability",
    "test",
)

#: Promotion-target closed vocabulary. ``none`` is the default for
#: this PR — promotion remains an explicit operator action.
PROMOTION_TARGETS: Final[tuple[str, ...]] = (
    "development_delegation",
    "development_work_queue",
    "none",
)

#: Marker required field set; closed.
MARKER_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "candidate_id",
        "phase",
        "title",
        "category",
        "required_agent_role",
        "risk_level",
        "target_path",
        "human_needed",
        "human_needed_reason",
        "acceptance_criteria",
    }
)

#: Per-candidate schema keys; exact and ordered.
CANDIDATE_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "title",
    "source_document",
    "source_anchor",
    "roadmap_phase",
    "source_kind",
    "candidate_kind",
    "category",
    "required_agent_role",
    "risk_level",
    "target_path",
    "execution_authority_decision",
    "execution_authority_reason",
    "human_needed",
    "human_needed_reason",
    "intake_status",
    "acceptance_criteria",
    "validation_requirements",
    "promotion_target",
    "notes",
)

#: Bounded length for free-text fields on a single candidate.
MAX_TITLE_LEN: Final[int] = 200
MAX_NOTES_LEN: Final[int] = 1000
MAX_AC_ITEMS: Final[int] = 16
MAX_AC_LINE_LEN: Final[int] = 200
MAX_ID_LEN: Final[int] = 96
MAX_PHASE_LEN: Final[int] = 64
MAX_TARGET_PATH_LEN: Final[int] = 300
MAX_MARKERS_PER_DOC: Final[int] = 256

#: Wrapper-level note vocabulary.
NOTE_NO_CANDIDATES: Final[str] = "no_explicit_intake_candidates"
NOTE_CANDIDATES_PRESENT: Final[str] = "intake_candidates_present"
NOTE_SOURCE_DOCS_MISSING: Final[str] = "source_docs_missing"

#: Marker pattern. Opener and closer are pinned exactly so prose
#: cannot accidentally match.
_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*ade_roadmap_intake\b(.*?)-->", re.DOTALL
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_roadmap_intake"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_roadmap_intake/latest.json"
)

#: Atomic-write allowlist (POSIX path substring form). Any write
#: target whose path does not contain this substring is refused with
#: ``ValueError``.
_WRITE_PREFIX: Final[str] = "logs/development_roadmap_intake/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool]] = {
    "actually_modifies_target": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "mergeable_by_agent": False,
    "deployable_by_agent": False,
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "fuzzy_parsing": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "operator_promotion_required": True,
    "step5_implementation_allowed": False,
    "diagnostics_do_not_trade": True,
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


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def _normalize_path(p: str) -> str:
    if not p:
        return ""
    return p.replace("\\", "/").lstrip("./")


def _is_archive_path(p: str) -> bool:
    n = _normalize_path(p).lower()
    return n.startswith("docs/roadmap/archive/") or "/archive/" in n


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _coerce_bool(s: Any) -> bool | None:
    if isinstance(s, bool):
        return s
    if not isinstance(s, str):
        return None
    v = s.strip().lower()
    if v in {"true", "yes", "1"}:
        return True
    if v in {"false", "no", "0"}:
        return False
    return None


# ---------------------------------------------------------------------------
# Marker body parser
# ---------------------------------------------------------------------------


def _parse_marker_body(body: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse a marker body into a typed dict.

    Returns ``(payload, warnings)``. Returns ``None`` payload with
    warnings on any structural failure. Same minimal grammar as A11:

    * one ``key: value`` per line for scalar fields,
    * ``acceptance_criteria:`` followed by indented ``- value`` lines,
    * blank lines and comment lines (``#``) tolerated.

    Anything else is rejected with a warning.
    """
    warnings: list[str] = []
    out: dict[str, Any] = {}
    ac: list[str] | None = None
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue
        if ac is not None:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                if len(ac) >= MAX_AC_ITEMS:
                    warnings.append("acceptance_criteria_truncated")
                else:
                    ac.append(_bounded_str(stripped[2:].strip(), MAX_AC_LINE_LEN))
                continue
            ac = None
        if ":" not in line:
            warnings.append("marker_line_without_colon")
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value_stripped = value.strip()
        if key == "acceptance_criteria":
            ac = []
            out["acceptance_criteria"] = ac
            continue
        out[key] = value_stripped
    return out if out else None, warnings


def _validate_marker_payload(
    payload: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    missing = MARKER_REQUIRED_FIELDS - set(payload.keys())
    if missing:
        warnings.append(f"marker_missing_fields:{','.join(sorted(missing))}")
        return None, warnings

    candidate_id = _bounded_str(payload.get("candidate_id"), MAX_ID_LEN)
    if not candidate_id or not re.match(r"^[A-Za-z0-9_.\-]+$", candidate_id):
        warnings.append("marker_invalid_candidate_id")
        return None, warnings

    phase = _bounded_str(payload.get("phase"), MAX_PHASE_LEN)
    if not phase:
        warnings.append("marker_missing_phase")
        return None, warnings

    title = _bounded_str(payload.get("title"), MAX_TITLE_LEN)
    if not title:
        warnings.append("marker_missing_title")
        return None, warnings

    category = payload.get("category")
    if category not in CANDIDATE_KINDS:
        warnings.append("marker_invalid_category")
        return None, warnings

    role = payload.get("required_agent_role")
    if role not in dwq.AGENT_ROLES:
        warnings.append("marker_invalid_required_agent_role")
        return None, warnings

    risk = payload.get("risk_level")
    if risk not in ea.RISK_CLASSES:
        warnings.append("marker_invalid_risk_level")
        return None, warnings

    target_path = _bounded_str(payload.get("target_path"), MAX_TARGET_PATH_LEN)
    if not target_path:
        warnings.append("marker_missing_target_path")
        return None, warnings

    hn_raw = payload.get("human_needed")
    human_needed = _coerce_bool(hn_raw)
    if human_needed is None:
        warnings.append("marker_invalid_human_needed")
        return None, warnings

    hn_reason = payload.get("human_needed_reason")
    if hn_reason not in dwq.HUMAN_NEEDED_REASONS:
        warnings.append("marker_invalid_human_needed_reason")
        return None, warnings
    if human_needed and hn_reason == "none":
        warnings.append("marker_human_needed_true_but_reason_none")
        return None, warnings
    if (not human_needed) and hn_reason != "none":
        warnings.append("marker_human_needed_false_but_reason_not_none")
        return None, warnings

    ac = payload.get("acceptance_criteria") or []
    if not isinstance(ac, list) or not ac:
        warnings.append("marker_missing_acceptance_criteria")
        return None, warnings
    ac_clean: list[str] = []
    for entry in ac[:MAX_AC_ITEMS]:
        if isinstance(entry, str) and entry.strip():
            ac_clean.append(_bounded_str(entry, MAX_AC_LINE_LEN))
    if not ac_clean:
        warnings.append("marker_acceptance_criteria_empty_after_clean")
        return None, warnings

    return (
        {
            "candidate_id": candidate_id,
            "phase": phase,
            "title": title,
            "category": category,
            "required_agent_role": role,
            "risk_level": risk,
            "target_path": _normalize_path(target_path),
            "human_needed": human_needed,
            "human_needed_reason": hn_reason,
            "acceptance_criteria": ac_clean,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# Candidate construction
# ---------------------------------------------------------------------------


def _intake_status_for(
    *, decision: ea.ExecutionDecision, human_needed: bool
) -> str:
    """Map (decision, human_needed) → closed intake_status value.

    * Operator marked ``human_needed=true`` → ``human_needed``.
    * Authority ``PERMANENTLY_DENIED`` → ``blocked``.
    * Authority ``NEEDS_HUMAN`` → ``human_needed``.
    * Authority ``AUTO_ALLOWED`` and not human_needed → ``eligible``.
    * Anything else → ``proposed`` (fail-safe; never silently
      ``eligible``).
    """
    if human_needed:
        return "human_needed"
    if decision.decision == ea.DECISION_PERMANENTLY_DENIED:
        return "blocked"
    if decision.decision == ea.DECISION_NEEDS_HUMAN:
        return "human_needed"
    if decision.decision == ea.DECISION_AUTO_ALLOWED:
        return "eligible"
    return "proposed"


def _build_candidate(
    validated: dict[str, Any],
    *,
    source_document: str,
    source_anchor: str,
    source_kind: str,
) -> dict[str, Any]:
    decision = ea.classify(
        action_type="file_edit",
        target_path=validated["target_path"],
        risk_class=validated["risk_level"],
    )
    intake_status = _intake_status_for(
        decision=decision,
        human_needed=validated["human_needed"],
    )
    return {
        "candidate_id": validated["candidate_id"],
        "title": validated["title"],
        "source_document": source_document,
        "source_anchor": source_anchor,
        "roadmap_phase": validated["phase"],
        "source_kind": source_kind,
        "candidate_kind": validated["category"],
        "category": validated["category"],
        "required_agent_role": validated["required_agent_role"],
        "risk_level": validated["risk_level"],
        "target_path": validated["target_path"],
        "execution_authority_decision": decision.decision,
        "execution_authority_reason": decision.reason,
        "human_needed": validated["human_needed"],
        "human_needed_reason": validated["human_needed_reason"],
        "intake_status": intake_status,
        "acceptance_criteria": validated["acceptance_criteria"],
        "validation_requirements": [],
        "promotion_target": "none",
        "notes": "",
    }


def _candidates_from_doc(
    doc_path: str, *, text: str, source_kind: str
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []
    matches = list(_MARKER_RE.finditer(text))
    if len(matches) > MAX_MARKERS_PER_DOC:
        warnings.append(f"too_many_markers_truncated_at_{MAX_MARKERS_PER_DOC}")
        matches = matches[:MAX_MARKERS_PER_DOC]
    for idx, m in enumerate(matches, start=1):
        body = m.group(1)
        parsed, parse_warns = _parse_marker_body(body)
        for w in parse_warns:
            warnings.append(f"{doc_path}#marker{idx}:{w}")
        if parsed is None:
            continue
        validated, val_warns = _validate_marker_payload(parsed)
        for w in val_warns:
            warnings.append(f"{doc_path}#marker{idx}:{w}")
        if validated is None:
            continue
        candidate = _build_candidate(
            validated,
            source_document=doc_path,
            source_anchor=f"marker_{idx}",
            source_kind=source_kind,
        )
        candidates.append(candidate)
    return candidates, warnings


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_source_kind": {k: 0 for k in SOURCE_KINDS},
        "by_candidate_kind": {k: 0 for k in CANDIDATE_KINDS},
        "by_intake_status": {s: 0 for s in INTAKE_STATUSES},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
        "by_required_agent_role": {r: 0 for r in dwq.AGENT_ROLES},
        "by_promotion_target": {t: 0 for t in PROMOTION_TARGETS},
        "human_needed": 0,
        "eligible": 0,
        "blocked": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        counts["by_source_kind"][row["source_kind"]] += 1
        counts["by_candidate_kind"][row["candidate_kind"]] += 1
        counts["by_intake_status"][row["intake_status"]] += 1
        counts["by_execution_authority_decision"][
            row["execution_authority_decision"]
        ] += 1
        counts["by_required_agent_role"][row["required_agent_role"]] += 1
        counts["by_promotion_target"][row["promotion_target"]] += 1
        if row["human_needed"]:
            counts["human_needed"] += 1
        if row["intake_status"] == "eligible":
            counts["eligible"] += 1
        if row["intake_status"] == "blocked":
            counts["blocked"] += 1
    return counts


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    source_paths: tuple[str, ...] | None = None,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic roadmap-intake snapshot.

    Args:
        source_paths: override the default canonical source paths.
            Tests pass synthetic fixture paths here. The check
            against archive prefixes always runs; non-canonical paths
            are excluded with a validation_warning.
        repo_root: override repo root for tests. Defaults to the
            module's repo root.
        generated_at_utc: override the wrapper's report timestamp.
            Tests inject this for byte-stable output.
    """
    sp = source_paths if source_paths is not None else DEFAULT_SOURCE_PATHS
    root = repo_root if repo_root is not None else REPO_ROOT
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    warnings: list[str] = []
    candidates: list[dict[str, Any]] = []
    docs_used: list[str] = []
    docs_missing: list[str] = []
    seen_ids: set[str] = set()

    for doc in sp:
        norm = _normalize_path(doc)
        if _is_archive_path(norm):
            warnings.append(f"archive_path_excluded:{norm}")
            continue
        source_kind = SOURCE_PATH_TO_KIND.get(norm)
        if source_kind is None:
            warnings.append(f"non_canonical_source_path_excluded:{norm}")
            continue
        full_path = root / norm
        text = _read_text(full_path)
        if text is None:
            docs_missing.append(norm)
            continue
        docs_used.append(norm)
        doc_candidates, doc_warns = _candidates_from_doc(
            norm, text=text, source_kind=source_kind
        )
        warnings.extend(doc_warns)
        for cand in doc_candidates:
            if cand["candidate_id"] in seen_ids:
                warnings.append(
                    f"{norm}:duplicate_candidate_id:{cand['candidate_id']}"
                )
                continue
            seen_ids.add(cand["candidate_id"])
            candidates.append(cand)

    candidates.sort(key=lambda c: (c["source_kind"], c["candidate_id"]))

    counts = _aggregate_counts(candidates)

    if not docs_used:
        note = NOTE_SOURCE_DOCS_MISSING if docs_missing else NOTE_NO_CANDIDATES
    elif not candidates:
        note = NOTE_NO_CANDIDATES
    else:
        note = NOTE_CANDIDATES_PRESENT

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "step5_implementation_allowed": step5_implementation_allowed,
        "canonical_source_paths": list(DEFAULT_SOURCE_PATHS),
        "source_paths_used": docs_used,
        "source_paths_missing": docs_missing,
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "source_kinds": list(SOURCE_KINDS),
            "candidate_kinds": list(CANDIDATE_KINDS),
            "intake_statuses": list(INTAKE_STATUSES),
            "promotion_targets": list(PROMOTION_TARGETS),
            "agent_roles": list(dwq.AGENT_ROLES),
            "risk_levels": list(ea.RISK_CLASSES),
            "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
            "marker_required_fields": sorted(MARKER_REQUIRED_FIELDS),
        },
        "counts": counts,
        "candidates": candidates,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": dwq.MODULE_VERSION,
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as sorted-key indented JSON to ``path``,
    atomically, refusing any path outside
    ``logs/development_roadmap_intake/...``."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_roadmap_intake._atomic_write_json refuses "
            f"non-intake-logs output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_roadmap_intake.",
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
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_roadmap_intake",
        description=(
            "Step 5.0.1 Roadmap Intake Bridge. Read-only deterministic "
            "parser of explicit `<!-- ade_roadmap_intake ... -->` "
            "markers in Roadmap v6, the Roadmap v6 Addendum, the QRE "
            "phase-prompts doc, and the QRE ADE operating-manual doc. "
            "No fuzzy parsing. Decides nothing; mutates nothing. Step "
            "5 implementation remains BLOCKED."
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
            "Do not persist logs/development_roadmap_intake/latest.json "
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
