"""A18a — Generated Queue Lane projector (DRY-RUN / REPORT-ONLY).

Pure stdlib-only projector that inspects existing read-only
development artefacts (A10 bugfix loop, A11 delegation, A13 e2e
proof) and emits a bounded **dry-run** report of generated
candidate work items at
``logs/development_generated_lane/latest.json``.

This is the **smallest safe A18 slice**. It exists to make the
question "what would a generated queue lane propose?" answerable
**without** introducing any new authority. It does **NOT**:

* create or mutate ``generated_seed.jsonl`` (the file remains
  absent until a future operator-authorised A18b writer slice);
* append to ``seed.jsonl`` or ``delegation_seed.jsonl``;
* integrate with A17 queue admission as an active seed source;
* enqueue, execute, or dequeue any work item;
* mint or verify any approval token;
* call ``gh`` / ``git`` / ``subprocess`` / network;
* mutate any upstream artefact;
* edit any roadmap status field;
* mark any roadmap phase complete;
* enable Step 5.1 or Step 5.2;
* flip ``step5_implementation_allowed``;
* change ``STEP5_ENABLED_SUBSTAGE``;
* introduce or change Level 6 status.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.agent_audit_summary.assert_no_secrets``
  (read-only redactor guard).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``, ``reporting.approval_token_gate``,
  ``reporting.approval_token_runtime``,
  ``reporting.web_push_real_transport``.
* Atomic write only under ``logs/development_generated_lane/...``.
* Per-candidate schema is closed and exact. Bounded scalars only.
* No decision verb (``approve``, ``reject``, ``merge``, ``deploy``,
  ``trade``) appears in any emitted action / status / vocabulary
  value. The closed admission-preview / block-reason vocabularies
  use ``report_only_not_admitted`` and
  ``generated_lane_writer_not_authorized`` — they are explicitly
  NOT executable verbs.
* The literal string ``generated_seed.jsonl`` may appear in
  docstrings and discipline-invariant flag names (asserting absence)
  but NEVER on a write code path. The atomic-write helper refuses
  any path outside ``logs/development_generated_lane/...``.

CLI
---

::

    python -m reporting.development_generated_lane
    python -m reporting.development_generated_lane --no-write
    python -m reporting.development_generated_lane --indent 0

``--no-write`` prints the snapshot to stdout only; it writes no
file. Default mode atomic-writes
``logs/development_generated_lane/latest.json`` AND prints. **In
neither mode is ``generated_seed.jsonl`` created.**
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

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A18a"
REPORT_KIND: Final[str] = "development_generated_lane"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies + bounds
# ---------------------------------------------------------------------------

#: Closed proposed-kind vocabulary. Maps a source artefact to the
#: kind of generated candidate that would be proposed if a future
#: A18b writer were authorised. Adding a value requires a code
#: change pinned by an updated test.
PROPOSED_KINDS: Final[tuple[str, ...]] = (
    "bugfix",
    "delegation",
    "e2e_proof",
    "unknown",
)

#: Closed admission-preview vocabulary. A18a NEVER emits a value
#: other than ``report_only_not_admitted`` — admission is the
#: future A18c slice's authority, not this projector's.
ADMISSION_PREVIEWS: Final[tuple[str, ...]] = (
    "report_only_not_admitted",
)

#: Closed block-reason vocabulary. A18a NEVER emits a value
#: other than ``generated_lane_writer_not_authorized``.
BLOCK_REASONS: Final[tuple[str, ...]] = (
    "generated_lane_writer_not_authorized",
)

#: Closed validation-warning vocabulary.
VALIDATION_WARNINGS: Final[tuple[str, ...]] = (
    "bugfix_loop_artifact_absent",
    "bugfix_loop_artifact_unparseable",
    "delegation_artifact_absent",
    "delegation_artifact_unparseable",
    "e2e_proof_artifact_absent",
    "e2e_proof_artifact_unparseable",
    "no_candidates_from_any_source",
)

#: Closed candidate-record schema, exact and ordered.
GENERATED_CANDIDATE_KEYS: Final[tuple[str, ...]] = (
    "generated_candidate_id",
    "source_module",
    "source_id",
    "proposed_kind",
    "proposed_title",
    "proposed_summary",
    "evidence_hash",
    "admission_preview",
    "block_reason",
    "would_require_operator_go",
)

#: Closed wrapper-level note vocabulary.
NOTE_NO_SOURCES: Final[str] = "no_upstream_sources_available"
NOTE_NO_CANDIDATES: Final[str] = "no_candidates_from_any_source"
NOTE_CANDIDATES_PRESENT: Final[str] = "candidates_present_report_only"

#: Bounded length for free-text scalars. Tighter than upstream
#: schemas because A18a's job is to surface the existence of
#: candidates, not to render their contents.
MAX_TITLE_LEN: Final[int] = 120
MAX_SUMMARY_LEN: Final[int] = 300
MAX_SOURCE_ID_LEN: Final[int] = 200

#: Maximum candidates retained in any single snapshot, across all
#: sources combined. The list is round-robin across the three
#: upstream sources to give each visibility.
MAX_GENERATED_CANDIDATES: Final[int] = 16

#: Forbidden substrings inside any candidate scalar (defense in
#: depth on top of the closed schema + assert_no_secrets).
_FORBIDDEN_CANDIDATE_SUBSTRINGS: Final[tuple[str, ...]] = (
    "BEGIN PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "diff --git ",
    "+++ b/",
    "--- a/",
    "@@ -",
)


# ---------------------------------------------------------------------------
# Upstream artefact paths (read-only)
# ---------------------------------------------------------------------------

_BUGFIX_LOOP_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "development_bugfix_loop" / "latest.json"
)
_DELEGATION_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "development_delegation" / "latest.json"
)
_E2E_PROOF_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "development_e2e_proof" / "latest.json"
)


# ---------------------------------------------------------------------------
# A18a output path (sentinel-restricted)
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_generated_lane"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_generated_lane/latest.json"
)

#: Atomic-write allowlist (substring form). The sentinel-restricted
#: writer refuses any path that does not contain this prefix.
_WRITE_PREFIX: Final[str] = "logs/development_generated_lane/"


# ---------------------------------------------------------------------------
# Discipline invariants emitted into every artefact
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "writes_to_seed_jsonl": False,
    "writes_to_delegation_seed_jsonl": False,
    "writes_to_generated_seed_jsonl": False,
    "generated_seed_writer_authorized": False,
    "mutates_generated_seed": False,
    "admits_queue_items": False,
    "executes_work": False,
    "creates_real_branches": False,
    "opens_real_prs": False,
    "mergeable_by_agent": False,
    "deployable_by_agent": False,
    "mints_or_verifies_approval_tokens": False,
    "sends_real_push": False,
    "uses_subprocess_or_network": False,
    "calls_llm_or_external_api": False,
    "mutates_research_artifacts": False,
    "mutates_roadmap_status_fields": False,
    "marks_phase_complete": False,
    "operator_promotion_required": True,
    "operator_go_required_for_writer": True,
    "step5_implementation_allowed": False,
    "step5_enabled_substage": "none",
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


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()[:16]


def _scalar_passes_no_forbidden(value: str) -> bool:
    for needle in _FORBIDDEN_CANDIDATE_SUBSTRINGS:
        if needle in value:
            return False
    return True


# ---------------------------------------------------------------------------
# Per-source projectors → bounded candidate stubs
# ---------------------------------------------------------------------------


def _project_bugfix_candidate(
    rec: dict[str, Any],
) -> dict[str, Any] | None:
    """Project a A10 bugfix-loop candidate record into the closed
    A18a candidate schema. Returns ``None`` if the record is too
    malformed to project safely."""
    src_id = _bounded_str(
        rec.get("candidate_id"), MAX_SOURCE_ID_LEN
    )
    if not src_id:
        return None
    title = _bounded_str(
        rec.get("target_path") or rec.get("failure_class") or "",
        MAX_TITLE_LEN,
    )
    summary = _bounded_str(
        rec.get("rationale") or rec.get("failure_class") or "",
        MAX_SUMMARY_LEN,
    )
    if not _scalar_passes_no_forbidden(title):
        title = ""
    if not _scalar_passes_no_forbidden(summary):
        summary = ""
    return _build_candidate(
        source_module="development_bugfix_loop",
        source_id=src_id,
        proposed_kind="bugfix",
        proposed_title=title,
        proposed_summary=summary,
    )


def _project_delegation_candidate(
    rec: dict[str, Any],
) -> dict[str, Any] | None:
    """Project an A11 delegation record into the closed A18a
    candidate schema."""
    src_id = _bounded_str(
        rec.get("candidate_id") or rec.get("source_id"),
        MAX_SOURCE_ID_LEN,
    )
    if not src_id:
        return None
    title = _bounded_str(rec.get("title") or "", MAX_TITLE_LEN)
    summary = _bounded_str(
        rec.get("summary") or rec.get("rationale") or "",
        MAX_SUMMARY_LEN,
    )
    if not _scalar_passes_no_forbidden(title):
        title = ""
    if not _scalar_passes_no_forbidden(summary):
        summary = ""
    return _build_candidate(
        source_module="development_delegation",
        source_id=src_id,
        proposed_kind="delegation",
        proposed_title=title,
        proposed_summary=summary,
    )


def _project_e2e_proof_candidate(
    rec: dict[str, Any],
) -> dict[str, Any] | None:
    """Project an A13 e2e-proof record into the closed A18a
    candidate schema. Many e2e_proof artefacts are roll-up reports
    rather than per-candidate rows; this projector skips records
    without an identifiable source id."""
    src_id = _bounded_str(
        rec.get("proof_id") or rec.get("candidate_id") or rec.get("id"),
        MAX_SOURCE_ID_LEN,
    )
    if not src_id:
        return None
    title = _bounded_str(rec.get("title") or "", MAX_TITLE_LEN)
    summary = _bounded_str(
        rec.get("summary") or "",
        MAX_SUMMARY_LEN,
    )
    if not _scalar_passes_no_forbidden(title):
        title = ""
    if not _scalar_passes_no_forbidden(summary):
        summary = ""
    return _build_candidate(
        source_module="development_e2e_proof",
        source_id=src_id,
        proposed_kind="e2e_proof",
        proposed_title=title,
        proposed_summary=summary,
    )


def _build_candidate(
    *,
    source_module: str,
    source_id: str,
    proposed_kind: str,
    proposed_title: str,
    proposed_summary: str,
) -> dict[str, Any]:
    """Build the closed-schema A18a candidate row."""
    assert proposed_kind in PROPOSED_KINDS, proposed_kind
    candidate = {
        "generated_candidate_id": _digest(source_module, source_id),
        "source_module": source_module,
        "source_id": source_id,
        "proposed_kind": proposed_kind,
        "proposed_title": proposed_title,
        "proposed_summary": proposed_summary,
        "evidence_hash": _digest(source_module, source_id, "evidence"),
        "admission_preview": "report_only_not_admitted",
        "block_reason": "generated_lane_writer_not_authorized",
        "would_require_operator_go": True,
    }
    assert set(candidate.keys()) == set(GENERATED_CANDIDATE_KEYS), (
        sorted(candidate.keys())
    )
    return candidate


def _candidates_from_artifact(
    payload: dict[str, Any],
    projector: Any,
    limit: int,
) -> list[dict[str, Any]]:
    """Walk the upstream artefact's records / rows / candidates list
    and project up to ``limit`` rows. Tolerant of missing keys."""
    out: list[dict[str, Any]] = []
    for key in ("candidates", "rows", "records"):
        raw = payload.get(key)
        if isinstance(raw, list):
            for r in raw:
                if not isinstance(r, dict):
                    continue
                projected = projector(r)
                if projected is None:
                    continue
                out.append(projected)
                if len(out) >= limit:
                    return out
            if out:
                return out
    return out


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    bugfix_loop_artifact_path: Path | None = None,
    delegation_artifact_path: Path | None = None,
    e2e_proof_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic A18a snapshot. Pure: reads upstream
    artefacts read-only; never writes; never appends to any seed
    file. The caller is responsible for atomic-writing the
    snapshot via :func:`write_outputs`."""
    bp = (
        bugfix_loop_artifact_path
        if bugfix_loop_artifact_path is not None
        else _BUGFIX_LOOP_LATEST
    )
    dp = (
        delegation_artifact_path
        if delegation_artifact_path is not None
        else _DELEGATION_LATEST
    )
    ep = (
        e2e_proof_artifact_path
        if e2e_proof_artifact_path is not None
        else _E2E_PROOF_LATEST
    )
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    warnings: list[str] = []
    sources_read: dict[str, dict[str, Any]] = {}

    # Bugfix loop
    bugfix_payload = _read_json(bp)
    sources_read["bugfix_loop"] = {
        "path": str(bp),
        "available": bugfix_payload is not None,
    }
    if not bp.is_file():
        warnings.append("bugfix_loop_artifact_absent")
    elif bugfix_payload is None:
        warnings.append("bugfix_loop_artifact_unparseable")

    # Delegation
    delegation_payload = _read_json(dp)
    sources_read["delegation"] = {
        "path": str(dp),
        "available": delegation_payload is not None,
    }
    if not dp.is_file():
        warnings.append("delegation_artifact_absent")
    elif delegation_payload is None:
        warnings.append("delegation_artifact_unparseable")

    # E2E proof
    e2e_payload = _read_json(ep)
    sources_read["e2e_proof"] = {
        "path": str(ep),
        "available": e2e_payload is not None,
    }
    if not ep.is_file():
        warnings.append("e2e_proof_artifact_absent")
    elif e2e_payload is None:
        warnings.append("e2e_proof_artifact_unparseable")

    # Round-robin per-source projection up to the global cap.
    per_source_cap = max(1, MAX_GENERATED_CANDIDATES // 3)
    candidates: list[dict[str, Any]] = []
    if bugfix_payload is not None:
        candidates.extend(
            _candidates_from_artifact(
                bugfix_payload, _project_bugfix_candidate, per_source_cap
            )
        )
    if delegation_payload is not None:
        candidates.extend(
            _candidates_from_artifact(
                delegation_payload,
                _project_delegation_candidate,
                per_source_cap,
            )
        )
    if e2e_payload is not None:
        candidates.extend(
            _candidates_from_artifact(
                e2e_payload,
                _project_e2e_proof_candidate,
                per_source_cap,
            )
        )

    # Global cap defense-in-depth.
    if len(candidates) > MAX_GENERATED_CANDIDATES:
        candidates = candidates[:MAX_GENERATED_CANDIDATES]

    if not candidates:
        if all(
            not s["available"] for s in sources_read.values()
        ):
            note = NOTE_NO_SOURCES
        else:
            note = NOTE_NO_CANDIDATES
            warnings.append("no_candidates_from_any_source")
    else:
        note = NOTE_CANDIDATES_PRESENT

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "sources_read": sources_read,
        "validation_warnings": warnings,
        "vocabularies": {
            "proposed_kinds": list(PROPOSED_KINDS),
            "admission_previews": list(ADMISSION_PREVIEWS),
            "block_reasons": list(BLOCK_REASONS),
            "validation_warnings": list(VALIDATION_WARNINGS),
            "generated_candidate_keys": list(GENERATED_CANDIDATE_KEYS),
            "max_generated_candidates": MAX_GENERATED_CANDIDATES,
        },
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "note": note,
    }
    assert_no_secrets(snapshot)
    return snapshot


# ---------------------------------------------------------------------------
# Atomic write (sentinel-restricted)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` atomically; refuse any path outside
    ``logs/development_generated_lane/...``. The substring guard
    also blocks any attempt to write ``seed.jsonl`` /
    ``delegation_seed.jsonl`` / ``generated_seed.jsonl`` because
    those filenames are never under the generated-lane prefix."""
    posix = path.as_posix()
    if _WRITE_PREFIX not in posix and not posix.startswith(_WRITE_PREFIX):
        raise ValueError(
            "development_generated_lane._atomic_write_json refuses "
            f"non-generated-lane output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_generated_lane.",
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
    """Persist the A18a snapshot. ONLY writes
    ``logs/development_generated_lane/latest.json``. Never touches
    any seed file."""
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_generated_lane",
        description=(
            "A18a Generated Queue Lane projector (DRY-RUN / "
            "REPORT-ONLY). Read-only deterministic projector that "
            "inspects existing development_bugfix_loop / "
            "development_delegation / development_e2e_proof "
            "artefacts and emits a bounded dry-run report of "
            "candidate work items at "
            "logs/development_generated_lane/latest.json. "
            "Does NOT create or mutate generated_seed.jsonl, and "
            "does NOT integrate with A17 admission as an active "
            "seed source. Step 5 implementation remains BLOCKED. "
            "Level 6 stays permanently disabled."
        ),
    )
    p.add_argument(
        "--indent", type=int, default=2, help="JSON indent (0 for compact)."
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist "
            "logs/development_generated_lane/latest.json "
            "(stdout only). In neither mode is generated_seed.jsonl "
            "created."
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
