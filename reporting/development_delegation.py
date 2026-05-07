"""A11 — Bounded Roadmap Implementation Delegation.

Pure, deterministic, stdlib-only roadmap-marker parser. Converts
explicit, machine-readable delegation markers inside the canonical
roadmap docs (and an optional sidecar seed) into routable
delegation entries. **No fuzzy parsing.** Plain headings, prose,
lists, and bullet points produce zero entries. Archive paths are
excluded.

Marker syntax inside a canonical roadmap doc:

::

    <!-- ade_delegation
    delegation_id: <opaque-stable-id>
    title: <≤200 chars>
    category: <one of A8 CATEGORIES>
    required_agent_role: <one of A8 AGENT_ROLES>
    risk_level: <LOW | MEDIUM | HIGH | UNKNOWN>
    acceptance_criteria:
      - <≤200 chars>
      - <…>
    human_needed: <true | false>
    human_needed_reason: <closed reason>
    -->

The parser is strict: every required field must be present and
each value must belong to the closed vocabulary. Anything else
becomes a validation_warning and is dropped, never silently
promoted.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` + ``reporting.approval_policy`` +
  ``reporting.development_work_queue`` (read-only API).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* No mutation of any upstream artifact.
* Atomic write only under ``logs/development_delegation/latest.json``.
* Only canonical roadmap paths are accepted as roadmap sources;
  archive paths are excluded by both inclusion list and a positive
  ``archive/`` substring check.

CLI::

    python -m reporting.development_delegation
    python -m reporting.development_delegation --no-write
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
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
MODULE_VERSION: Final[str] = "v3.15.16.A11"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

#: The two canonical roadmap docs accepted as marker sources. The
#: parser refuses any other document. ADE remains generic, but this
#: module's roadmap-pickup happens against these two (and the
#: optional sidecar seed). Archive paths are explicitly rejected.
CANONICAL_ROADMAP_PATHS: Final[tuple[str, ...]] = (
    "docs/roadmap/autonomous_development.txt",
    "docs/roadmap/Roadmap v6.md",
)

#: Optional sidecar seed file. Strict JSONL. Empty by default.
DEFAULT_SIDECAR_SEED_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "development_work_queue" / "delegation_seed.jsonl"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_delegation"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_delegation/latest.json"

# ---------------------------------------------------------------------------
# Closed vocabularies (re-using A8 vocabularies, plus a closed marker
# field set)
# ---------------------------------------------------------------------------

#: Marker required field set; closed.
MARKER_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "delegation_id",
        "title",
        "category",
        "required_agent_role",
        "risk_level",
        "acceptance_criteria",
        "human_needed",
        "human_needed_reason",
    }
)

#: Per-entry schema keys; exact and ordered.
ENTRY_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "delegation_id",
    "title",
    "source_document",
    "source_section_or_anchor",
    "roadmap_track",
    "category",
    "required_agent_role",
    "supporting_agent_roles",
    "execution_authority_decision",
    "execution_authority_reason",
    "status",
    "human_needed",
    "human_needed_reason",
    "risk_level",
    "protected_surface",
    "acceptance_criteria",
    "validation_requirements",
    "notes",
    "created_at_placeholder",
    "updated_at_placeholder",
)

ITEM_TIME_PLACEHOLDER: Final[str] = "deterministic_seed_placeholder"

#: Status assigned to parsed delegation entries. Operator promotion
#: into the work queue is required to advance to ``ready``.
DEFAULT_STATUS: Final[str] = "triaged"

#: Bounded length for free-text fields.
MAX_TITLE_LEN: Final[int] = 200
MAX_NOTES_LEN: Final[int] = 1000
MAX_AC_ITEMS: Final[int] = 16
MAX_AC_LINE_LEN: Final[int] = 200
MAX_DELEGATION_ID_LEN: Final[int] = 64
MAX_MARKERS_PER_DOC: Final[int] = 256

#: Roadmap track per source document.
ROADMAP_TRACK_BY_SOURCE: Final[dict[str, str]] = {
    "docs/roadmap/autonomous_development.txt": "autonomous_development",
    "docs/roadmap/Roadmap v6.md": "qre_feature_build",
}

#: Wrapper-level note vocabulary.
NOTE_NO_ENTRIES: Final[str] = "no_explicit_delegation_entries"
NOTE_ENTRIES_PRESENT: Final[str] = "delegation_entries_present"
NOTE_ROADMAP_DOCS_MISSING: Final[str] = "roadmap_docs_missing"

#: Marker pattern. The opener and closer are pinned exactly so prose
#: cannot accidentally match.
_MARKER_OPEN: Final[str] = "<!-- ade_delegation"
_MARKER_CLOSE: Final[str] = "-->"
_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--\s*ade_delegation\b(.*?)-->", re.DOTALL
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


def _coerce_bool(s: str) -> bool | None:
    s = s.strip().lower()
    if s in {"true", "yes", "1"}:
        return True
    if s in {"false", "no", "0"}:
        return False
    return None


# ---------------------------------------------------------------------------
# Marker body parser
# ---------------------------------------------------------------------------


def _parse_marker_body(body: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse a marker body into a typed dict.

    Returns ``(payload, warnings)``. Returns ``None`` payload with
    warnings on any structural failure. The grammar is intentionally
    minimal:

    * one ``key: value`` per line for scalar fields,
    * ``acceptance_criteria:`` followed by indented ``- value`` lines,
    * blank lines and comment lines (``#``) tolerated.

    Anything else is rejected with a warning."""
    warnings: list[str] = []
    out: dict[str, Any] = {}
    ac: list[str] | None = None
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            ac = None if ac is not None else None
            continue
        if line.lstrip().startswith("#"):
            continue
        # acceptance_criteria block markers
        if ac is not None:
            stripped = line.lstrip()
            if stripped.startswith("- "):
                if len(ac) >= MAX_AC_ITEMS:
                    warnings.append("acceptance_criteria_truncated")
                else:
                    ac.append(_bounded_str(stripped[2:].strip(), MAX_AC_LINE_LEN))
                continue
            ac = None  # any other line ends the block
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

    delegation_id = _bounded_str(payload.get("delegation_id"), MAX_DELEGATION_ID_LEN)
    if not delegation_id or not re.match(r"^[A-Za-z0-9_.\-]+$", delegation_id):
        warnings.append("marker_invalid_delegation_id")
        return None, warnings

    title = _bounded_str(payload.get("title"), MAX_TITLE_LEN)
    if not title:
        warnings.append("marker_missing_title")
        return None, warnings

    category = payload.get("category")
    if category not in dwq.CATEGORIES:
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

    hn_raw = payload.get("human_needed")
    if isinstance(hn_raw, bool):
        human_needed = hn_raw
    else:
        coerced = _coerce_bool(str(hn_raw)) if hn_raw is not None else None
        if coerced is None:
            warnings.append("marker_invalid_human_needed")
            return None, warnings
        human_needed = coerced

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
            "delegation_id": delegation_id,
            "title": title,
            "category": category,
            "required_agent_role": role,
            "risk_level": risk,
            "human_needed": human_needed,
            "human_needed_reason": hn_reason,
            "acceptance_criteria": ac_clean,
        },
        warnings,
    )


def _entries_from_doc(
    doc_path: str, *, text: str
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    entries: list[dict[str, Any]] = []
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
        entry = _build_entry(
            validated,
            source_document=doc_path,
            source_section=f"marker_{idx}",
            roadmap_track=ROADMAP_TRACK_BY_SOURCE.get(doc_path, "sidecar_seed"),
        )
        entries.append(entry)
    return entries, warnings


def _entries_from_sidecar(
    seed_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    entries: list[dict[str, Any]] = []
    text = _read_text(seed_path)
    if text is None:
        return entries, warnings
    seen_ids: set[str] = set()
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        s = raw_line.strip()
        if not s:
            continue
        try:
            payload = json.loads(s)
        except ValueError:
            warnings.append(f"sidecar_line_{idx}_invalid_json")
            continue
        if not isinstance(payload, dict):
            warnings.append(f"sidecar_line_{idx}_not_an_object")
            continue
        validated, val_warns = _validate_marker_payload(payload)
        for w in val_warns:
            warnings.append(f"sidecar_line_{idx}:{w}")
        if validated is None:
            continue
        if validated["delegation_id"] in seen_ids:
            warnings.append(
                f"sidecar_line_{idx}:duplicate_delegation_id"
            )
            continue
        seen_ids.add(validated["delegation_id"])
        entries.append(
            _build_entry(
                validated,
                source_document="delegation_seed",
                source_section=f"line_{idx}",
                roadmap_track="sidecar_seed",
            )
        )
    return entries, warnings


# ---------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------


def _execution_authority_for(
    *, source_document: str, risk_level: str
) -> ea.ExecutionDecision:
    """Run the entry through ``ea.classify`` so the artifact carries
    a deterministic authority decision. The source document is the
    target_path the operator would edit to act on the delegation."""
    target = source_document if source_document != "delegation_seed" else "sidecar_seed"
    return ea.classify(
        action_type="file_edit",
        target_path=target if target else None,
        risk_class=risk_level,
    )


def _protected_surface(
    *, source_document: str, decision: ea.ExecutionDecision
) -> bool:
    """Mark canonical roadmap edits and any NEEDS_HUMAN/PERMANENTLY_DENIED
    target as protected. Operators may still promote them; the
    delegation parser only flags the surface."""
    if decision.target_path_category in {
        "claude_governance_hook",
        "dashboard_wiring",
        "frozen_contract",
        "live_path",
        "branch_protection_config",
        "deploy_script",
        "canonical_policy_doc",
        "canonical_roadmap",
        "ci_workflow",
    }:
        return True
    return decision.decision != ea.DECISION_AUTO_ALLOWED


def _build_entry(
    validated: dict[str, Any],
    *,
    source_document: str,
    source_section: str,
    roadmap_track: str,
) -> dict[str, Any]:
    decision = _execution_authority_for(
        source_document=source_document,
        risk_level=validated["risk_level"],
    )
    return {
        "delegation_id": validated["delegation_id"],
        "title": validated["title"],
        "source_document": source_document,
        "source_section_or_anchor": source_section,
        "roadmap_track": roadmap_track,
        "category": validated["category"],
        "required_agent_role": validated["required_agent_role"],
        "supporting_agent_roles": [],
        "execution_authority_decision": decision.decision,
        "execution_authority_reason": decision.reason,
        "status": DEFAULT_STATUS,
        "human_needed": validated["human_needed"],
        "human_needed_reason": validated["human_needed_reason"],
        "risk_level": validated["risk_level"],
        "protected_surface": _protected_surface(
            source_document=source_document, decision=decision
        ),
        "acceptance_criteria": validated["acceptance_criteria"],
        "validation_requirements": [],
        "notes": "",
        "created_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "updated_at_placeholder": ITEM_TIME_PLACEHOLDER,
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_roadmap_track": {
            "autonomous_development": 0,
            "qre_feature_build": 0,
            "sidecar_seed": 0,
        },
        "by_category": {c: 0 for c in dwq.CATEGORIES},
        "by_required_agent_role": {r: 0 for r in dwq.AGENT_ROLES},
        "by_status": {DEFAULT_STATUS: 0},
        "by_execution_authority_decision": {
            ea.DECISION_AUTO_ALLOWED: 0,
            ea.DECISION_NEEDS_HUMAN: 0,
            ea.DECISION_PERMANENTLY_DENIED: 0,
        },
        "human_needed": 0,
        "protected_surface": 0,
        "ready_for_operator_promotion": 0,
        "requiring_human_operator": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        counts["by_roadmap_track"][row["roadmap_track"]] += 1
        counts["by_category"][row["category"]] += 1
        counts["by_required_agent_role"][row["required_agent_role"]] += 1
        counts["by_status"][row["status"]] = counts["by_status"].get(row["status"], 0) + 1
        counts["by_execution_authority_decision"][
            row["execution_authority_decision"]
        ] += 1
        if row["human_needed"]:
            counts["human_needed"] += 1
            counts["requiring_human_operator"] += 1
        elif row["execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED and not row["protected_surface"]:
            counts["ready_for_operator_promotion"] += 1
        else:
            counts["requiring_human_operator"] += 1
        if row["protected_surface"]:
            counts["protected_surface"] += 1
    return counts


def collect_snapshot(
    *,
    roadmap_paths: tuple[str, ...] | None = None,
    sidecar_seed_path: Path | None = None,
    repo_root: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic delegation snapshot.

    Args:
        roadmap_paths: override the default canonical roadmap paths.
            Tests pass synthetic fixture paths here. The check
            against archive prefixes always runs.
        sidecar_seed_path: override the default
            ``docs/development_work_queue/delegation_seed.jsonl``.
        repo_root: override repo root for tests. Defaults to the
            module's repo root.
        generated_at_utc: override the wrapper's report timestamp.
    """
    rp = roadmap_paths if roadmap_paths is not None else CANONICAL_ROADMAP_PATHS
    root = repo_root if repo_root is not None else REPO_ROOT
    sp = sidecar_seed_path if sidecar_seed_path is not None else DEFAULT_SIDECAR_SEED_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    warnings: list[str] = []
    entries: list[dict[str, Any]] = []
    docs_used: list[str] = []
    docs_missing: list[str] = []
    seen_delegation_ids: set[str] = set()

    for doc in rp:
        norm = _normalize_path(doc)
        if _is_archive_path(norm):
            warnings.append(f"archive_path_excluded:{norm}")
            continue
        if norm not in CANONICAL_ROADMAP_PATHS:
            warnings.append(f"non_canonical_roadmap_path_excluded:{norm}")
            continue
        full_path = root / norm
        text = _read_text(full_path)
        if text is None:
            docs_missing.append(norm)
            continue
        docs_used.append(norm)
        doc_entries, doc_warns = _entries_from_doc(norm, text=text)
        warnings.extend(doc_warns)
        for entry in doc_entries:
            if entry["delegation_id"] in seen_delegation_ids:
                warnings.append(
                    f"{norm}:duplicate_delegation_id:{entry['delegation_id']}"
                )
                continue
            seen_delegation_ids.add(entry["delegation_id"])
            entries.append(entry)

    sidecar_entries, sidecar_warns = _entries_from_sidecar(sp)
    warnings.extend(sidecar_warns)
    for entry in sidecar_entries:
        if entry["delegation_id"] in seen_delegation_ids:
            warnings.append(
                f"sidecar:duplicate_delegation_id:{entry['delegation_id']}"
            )
            continue
        seen_delegation_ids.add(entry["delegation_id"])
        entries.append(entry)

    entries.sort(key=lambda e: (e["roadmap_track"], e["delegation_id"]))

    counts = _aggregate_counts(entries)

    if not docs_used and not sp.is_file():
        note = NOTE_ROADMAP_DOCS_MISSING if docs_missing else NOTE_NO_ENTRIES
    elif not entries:
        note = NOTE_NO_ENTRIES
    else:
        note = NOTE_ENTRIES_PRESENT

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_delegation",
        "generated_at_utc": ts,
        "canonical_roadmap_paths": list(CANONICAL_ROADMAP_PATHS),
        "roadmap_paths_used": docs_used,
        "roadmap_paths_missing": docs_missing,
        "sidecar_seed_path": str(sp.relative_to(root)) if sp.is_relative_to(root) else str(sp),
        "sidecar_seed_present": sp.is_file(),
        "note": note,
        "validation_warnings": warnings,
        "vocabularies": {
            "agent_roles": list(dwq.AGENT_ROLES),
            "categories": list(dwq.CATEGORIES),
            "human_needed_reasons": list(dwq.HUMAN_NEEDED_REASONS),
            "risk_levels": list(ea.RISK_CLASSES),
            "roadmap_tracks": ["autonomous_development", "qre_feature_build", "sidecar_seed"],
            "marker_required_fields": sorted(MARKER_REQUIRED_FIELDS),
        },
        "counts": counts,
        "entries": entries,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": dwq.MODULE_VERSION,
        "discipline_invariants": {
            "writes_to_seed_jsonl": False,
            "writes_to_bugfix_seed_jsonl": False,
            "writes_to_delegation_seed_jsonl": False,
            "fuzzy_parsing": False,
            "operator_promotion_required": True,
        },
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_delegation._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_delegation.", suffix=".tmp", dir=str(path.parent)
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
        prog="python -m reporting.development_delegation",
        description=(
            "Read-only delegation parser. Reads explicit "
            "`<!-- ade_delegation ... -->` markers from canonical "
            "roadmap docs and entries from the optional sidecar seed. "
            "No fuzzy parsing. Decides nothing; mutates nothing."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_delegation/latest.json "
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
