"""A18b — generated_seed.jsonl writer (default-disabled, env-gated).

Append-only, atomic, sentinel-restricted writer that registers
bounded closed-schema records into ``generated_seed.jsonl``.

Hard, default-deny posture
--------------------------

The writer is **disabled by default**. It only writes when the
operator has explicitly exported the exact-string env value::

    ADE_GENERATED_LANE_WRITER_ENABLED=true

Anything else — empty, ``"false"``, ``"1"``, ``"yes"``, ``"True"``,
``"TRUE"``, unset — leaves the writer in zero-write mode. The
public ``append_generated_seed_record`` returns
``status="skipped"`` / ``stop_status="writer_disabled"`` and
performs **no** file I/O at all (neither to the seed file nor to
the audit log).

What this writer is NOT
-----------------------

* It is **not** an admission engine. The A17 queue admission
  policy remains the only authority that admits work into the
  queue. A18b registers metadata only.
* It is **not** an executor. No work is started by this module.
* It is **not** a PR / branch / merge / deploy surface. None of
  those touch this file.
* It is **not** an A18c integration point. A18c (A17 reading
  ``generated_seed.jsonl`` as an additional source) remains a
  separate future slice with its own operator-go.
* It is **not** an A18a modification. A18a's projector
  (``reporting.development_generated_lane``) remains byte-
  identical and report-only. A18b imports A18a only to consume
  its read-only closed vocabularies.

Hard guarantees pinned by the companion test
--------------------------------------------

* Writer disabled unless the env var matches the exact literal
  string ``true`` (case-sensitive, no aliases).
* Writes only to ``generated_seed.jsonl`` at the repo root. The
  filename and parent directory are checked twice (sentinel
  basename match + parent equality). Any other path is rejected
  with the closed-vocab ``path_refused`` block_reason.
* ``seed.jsonl`` and ``delegation_seed.jsonl`` are explicitly
  enumerated in ``_FORBIDDEN_SEED_BASENAMES`` and refused by
  the path-sentinel check. Those filenames appear in this
  module ONLY inside the blocklist constant — there is no
  function that opens, writes, appends, or atomically replaces
  either path.
* Audit JSONL goes only to ``logs/development_generated_lane_writer/audit.jsonl``.
* Record schema is closed and exact (12 keys).
* ``assert_no_secrets`` runs on every record AND every audit
  envelope before write.
* Existing-file default-deny: if any line in the current
  ``generated_seed.jsonl`` does not parse as JSON, the writer
  refuses to append (closed-vocab ``existing_file_malformed``).
  An audit row records the refusal; the seed file is untouched.
* Duplicate ``generated_candidate_id`` → hard reject with
  ``duplicate_candidate_id``. An audit row IS appended to record
  the rejection attempt (forensic trail, bounded fields only).
* Duplicate ``evidence_hash`` with a *different*
  ``generated_candidate_id`` → soft warning
  ``duplicate_evidence_hash``; the record is appended; the audit
  row carries the warning.
* Cap of 256 records: 257th attempt is rejected with
  ``max_records_reached``.
* No env read at import time. No file write at import time. No
  global mutable state. The module is safe to import even when
  ``ADE_GENERATED_LANE_WRITER_ENABLED=true`` is already set —
  no write happens until ``append_generated_seed_record(...)``
  is called explicitly.
* No subprocess, no network, no GitHub CLI, no ``git``, no
  ``approval-token`` runtime/gate import.
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final, Mapping

from reporting import development_generated_lane as a18a
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A18b"
REPORT_KIND: Final[str] = "development_generated_lane_writer"


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Env-gate constants
#
# The exact-string match is deliberate. We refuse to enable on the
# common boolean aliases (1 / yes / True / on) so the operator's
# intent must be unambiguous.
# ---------------------------------------------------------------------------

ENV_WRITER_ENABLED: Final[str] = "ADE_GENERATED_LANE_WRITER_ENABLED"
_WRITER_ENABLED_VALUE: Final[str] = "true"


# ---------------------------------------------------------------------------
# Write paths + sentinels
#
# ``seed.jsonl`` and ``delegation_seed.jsonl`` are listed here in
# the blocklist constant ONLY. No other code in this module opens
# or writes either filename. The path-sentinel function refuses
# them explicitly with ``path_refused``.
# ---------------------------------------------------------------------------

#: The single canonical seed file this writer is allowed to touch.
GENERATED_SEED_PATH: Final[Path] = REPO_ROOT / "generated_seed.jsonl"

#: Directory + file path for the append-only audit log.
AUDIT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "development_generated_lane_writer"
)
AUDIT_PATH: Final[Path] = AUDIT_DIR / "audit.jsonl"

#: Required filename (basename) for the seed file. Defends against
#: ``generated_seed.jsonl_evil`` style smuggling.
_ALLOWED_SEED_BASENAME: Final[str] = "generated_seed.jsonl"

#: Required path-prefix for the audit log file.
_ALLOWED_AUDIT_PREFIX: Final[str] = "logs/development_generated_lane_writer/"

#: Filenames that are EXPLICITLY refused — even if an override
#: kwarg attempts to point the writer at them. The literals appear
#: only here, in this blocklist constant, never as a write target.
_FORBIDDEN_SEED_BASENAMES: Final[tuple[str, ...]] = (
    "seed.jsonl",
    "delegation_seed.jsonl",
)


# ---------------------------------------------------------------------------
# Cap + bounds
# ---------------------------------------------------------------------------

#: Maximum records retained / accepted in any single seed file.
#: The 257th append attempt is rejected with ``max_records_reached``.
MAX_GENERATED_SEED_RECORDS: Final[int] = 256

#: Bounded scalar lengths inside a record. Tighter than upstream
#: A18a schemas; the registration metadata is not the record body.
MAX_GENERATED_CANDIDATE_ID_LEN: Final[int] = 128
MAX_SOURCE_MODULE_LEN: Final[int] = 200
MAX_SOURCE_ID_LEN: Final[int] = 200
MAX_PROPOSED_TITLE_LEN: Final[int] = 120
MAX_PROPOSED_SUMMARY_LEN: Final[int] = 300
MAX_EVIDENCE_HASH_LEN: Final[int] = 128


# ---------------------------------------------------------------------------
# Closed vocabularies — A18b extensions of A18a
#
# A18a's source vocabularies (``ADMISSION_PREVIEWS``,
# ``BLOCK_REASONS``) are single-value tuples by design. A18b
# extends them additively; A18a's source is not modified.
# ---------------------------------------------------------------------------

#: Closed admission_preview vocab as the WRITER may emit. A
#: registered record carries ``generated_seed_written``;
#: anything that is rejected or skipped carries
#: ``report_only_not_admitted``.
WRITER_ADMISSION_PREVIEWS: Final[tuple[str, ...]] = (
    "report_only_not_admitted",
    "generated_seed_written",
)

#: Closed block_reason vocab as the WRITER may emit. ``none`` is
#: the success case; all other values describe a specific
#: failure mode pinned by tests.
WRITER_BLOCK_REASONS: Final[tuple[str, ...]] = (
    "none",
    "writer_disabled",
    "invalid_record_schema",
    "duplicate_candidate_id",
    "max_records_reached",
    "path_refused",
    "secret_detected",
    "existing_file_malformed",
    "generated_lane_writer_not_authorized",
)

#: Closed soft-warning vocab. Warnings do not cause rejection.
WRITER_WARNINGS: Final[tuple[str, ...]] = (
    "duplicate_evidence_hash",
)

#: Closed audit attempt_kind vocab. Every audit row carries
#: exactly one of these values to label the attempt outcome.
AUDIT_ATTEMPT_KINDS: Final[tuple[str, ...]] = (
    "written",
    "rejected_duplicate_candidate_id",
    "rejected_existing_file_malformed",
    "rejected_invalid_record_schema",
    "rejected_max_records_reached",
    "rejected_path_refused",
    "rejected_secret_detected",
    "skipped_writer_disabled",
)


# ---------------------------------------------------------------------------
# Closed record schema — 12 keys, exact and ordered
# ---------------------------------------------------------------------------

GENERATED_RECORD_KEYS: Final[tuple[str, ...]] = (
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
    "generated_at_utc",
    "writer_module_version",
)


# ---------------------------------------------------------------------------
# Discipline invariants — exact 14-key dict, emitted into every
# return envelope.
# ---------------------------------------------------------------------------

_DISCIPLINE_INVARIANTS: Final[dict[str, bool | str]] = {
    "default_disabled": True,
    "writes_only_generated_seed_jsonl": True,
    "writes_seed_jsonl": False,
    "writes_delegation_seed_jsonl": False,
    "admits_queue_items": False,
    "executes_work": False,
    "creates_branches": False,
    "opens_prs": False,
    "merges_prs": False,
    "deploys": False,
    "calls_network": False,
    "uses_subprocess": False,
    "touches_step5_flags": False,
    "level6_enabled": False,
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


def _bounded(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    return value[:max_len]


def _make_envelope(
    *,
    status: str,
    stop_status: str,
    generated_candidate_id: str,
    generated_seed_path: Path,
    audit_path: Path,
    writer_enabled_flag: bool,
    warnings: list[str],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the closed-shape return envelope. Always carries the
    discipline invariants so the operator can verify the writer's
    posture from the response."""
    env: dict[str, Any] = {
        "status": status,
        "stop_status": stop_status,
        "generated_candidate_id": generated_candidate_id,
        "generated_seed_path": str(generated_seed_path),
        "audit_path": str(audit_path),
        "writer_enabled": writer_enabled_flag,
        "warnings": list(warnings),
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "generated_at_utc": generated_at_utc,
    }
    # Defense-in-depth: never echo a token, never a PEM block, never
    # a VPS IP. The envelope contains only the bounded id + closed-
    # vocab values, but we run the redactor anyway.
    assert_no_secrets(env)
    return env


# ---------------------------------------------------------------------------
# Public API: env-gate
# ---------------------------------------------------------------------------


def writer_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True iff the operator has exported the exact-string
    env value enabling the writer.

    Reads the env mapping at *call time*, not at import time. The
    default ``env=None`` falls back to ``os.environ``, which is
    the only place this module touches the process environment.
    """
    source: Mapping[str, str] = env if env is not None else os.environ
    value = source.get(ENV_WRITER_ENABLED)
    if not isinstance(value, str):
        return False
    # Exact-string match. No alias normalisation.
    return value == _WRITER_ENABLED_VALUE


# ---------------------------------------------------------------------------
# Public API: record validation
# ---------------------------------------------------------------------------


def validate_record(
    record: Any,
) -> tuple[bool, str, list[str]]:
    """Validate a candidate record against the closed schema.

    Returns ``(ok, stop_status, warnings)``. ``stop_status`` is one
    of :data:`WRITER_BLOCK_REASONS`. Warnings are computed only
    against the record itself (cross-record warnings like
    ``duplicate_evidence_hash`` are produced by
    :func:`append_generated_seed_record` after loading the
    existing file).
    """
    if not isinstance(record, dict):
        return (False, "invalid_record_schema", [])
    if set(record.keys()) != set(GENERATED_RECORD_KEYS):
        return (False, "invalid_record_schema", [])

    # Type + bound checks per closed-schema field.
    if not isinstance(record["generated_candidate_id"], str):
        return (False, "invalid_record_schema", [])
    if len(record["generated_candidate_id"]) == 0:
        return (False, "invalid_record_schema", [])
    if len(record["generated_candidate_id"]) > MAX_GENERATED_CANDIDATE_ID_LEN:
        return (False, "invalid_record_schema", [])

    if not isinstance(record["source_module"], str):
        return (False, "invalid_record_schema", [])
    if len(record["source_module"]) == 0:
        return (False, "invalid_record_schema", [])
    if len(record["source_module"]) > MAX_SOURCE_MODULE_LEN:
        return (False, "invalid_record_schema", [])

    if not isinstance(record["source_id"], str):
        return (False, "invalid_record_schema", [])
    if len(record["source_id"]) > MAX_SOURCE_ID_LEN:
        return (False, "invalid_record_schema", [])

    if record["proposed_kind"] not in a18a.PROPOSED_KINDS:
        return (False, "invalid_record_schema", [])

    if not isinstance(record["proposed_title"], str):
        return (False, "invalid_record_schema", [])
    if len(record["proposed_title"]) > MAX_PROPOSED_TITLE_LEN:
        return (False, "invalid_record_schema", [])

    if not isinstance(record["proposed_summary"], str):
        return (False, "invalid_record_schema", [])
    if len(record["proposed_summary"]) > MAX_PROPOSED_SUMMARY_LEN:
        return (False, "invalid_record_schema", [])

    if not isinstance(record["evidence_hash"], str):
        return (False, "invalid_record_schema", [])
    if len(record["evidence_hash"]) > MAX_EVIDENCE_HASH_LEN:
        return (False, "invalid_record_schema", [])

    if record["admission_preview"] not in WRITER_ADMISSION_PREVIEWS:
        return (False, "invalid_record_schema", [])
    if record["block_reason"] not in WRITER_BLOCK_REASONS:
        return (False, "invalid_record_schema", [])
    if not isinstance(record["would_require_operator_go"], bool):
        return (False, "invalid_record_schema", [])
    if not isinstance(record["generated_at_utc"], str):
        return (False, "invalid_record_schema", [])
    if not isinstance(record["writer_module_version"], str):
        return (False, "invalid_record_schema", [])

    return (True, "none", [])


# ---------------------------------------------------------------------------
# Internal: path sentinel — refuse any path other than the canonical
# seed file. The forbidden-basenames list is consulted here ONLY.
# ---------------------------------------------------------------------------


def _seed_path_allowed(path: Path) -> bool:
    """Return True iff ``path`` is the canonical generated-seed
    target. False otherwise — including when the basename matches
    a forbidden seed-file (``seed.jsonl`` / ``delegation_seed.jsonl``)."""
    try:
        resolved = path.resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    if resolved.name in _FORBIDDEN_SEED_BASENAMES:
        return False
    if resolved.name != _ALLOWED_SEED_BASENAME:
        return False
    # Parent directory must be exactly REPO_ROOT.
    try:
        repo_root_resolved = REPO_ROOT.resolve(strict=False)
    except (OSError, RuntimeError):
        return False
    if resolved.parent != repo_root_resolved:
        return False
    return True


def _audit_path_allowed(path: Path) -> bool:
    """Return True iff ``path`` lives under the audit-log prefix."""
    posix = path.as_posix()
    return _ALLOWED_AUDIT_PREFIX in posix


# ---------------------------------------------------------------------------
# Internal: read existing seed file (default-deny on malformed line)
# ---------------------------------------------------------------------------


def _read_existing_records(
    path: Path,
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``("ok", records)`` if the file is absent or fully
    parseable; ``("malformed", [])`` if any line fails to parse as
    a JSON object. Never raises."""
    if not path.is_file():
        return "ok", []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "malformed", []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            return "malformed", []
        if not isinstance(obj, dict):
            return "malformed", []
        out.append(obj)
    return "ok", out


# ---------------------------------------------------------------------------
# Internal: atomic append via tmp + os.replace
#
# Full rewrite is cheap because MAX_GENERATED_SEED_RECORDS is 256.
# Atomic across processes on every platform we run on.
# ---------------------------------------------------------------------------


def _atomic_replace_jsonl(
    path: Path,
    *,
    existing_lines: list[str],
    new_line: str,
    write_prefix_check: str,
) -> None:
    """Atomic rewrite of a bounded JSONL file. Sentinel-restricted
    to ``write_prefix_check`` substring match."""
    posix = path.as_posix()
    if write_prefix_check not in posix:
        raise ValueError(
            "development_generated_lane_writer._atomic_replace_jsonl refuses "
            f"non-allowed output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = list(existing_lines) + [new_line]
    text = "\n".join(lines) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_generated_lane_writer.",
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
# Internal: audit row writer
# ---------------------------------------------------------------------------


def _append_audit_row(
    audit_path: Path,
    *,
    attempt_kind: str,
    generated_candidate_id: str,
    stop_status: str,
    warnings: list[str],
    now_utc: str,
) -> None:
    """Append a bounded audit row. The row carries ONLY the closed-
    vocab attempt label, the bounded candidate id, the closed-vocab
    stop_status, a list of closed-vocab warnings, and a timestamp.
    No record body is leaked.
    """
    if not _audit_path_allowed(audit_path):
        # Defense in depth: the path-sentinel is already enforced
        # at the public-API layer, but if a future refactor moves
        # the call site, this guard still refuses.
        raise ValueError(
            "development_generated_lane_writer._append_audit_row refuses "
            f"non-audit output path: {audit_path}"
        )
    if attempt_kind not in AUDIT_ATTEMPT_KINDS:
        raise ValueError(f"unknown audit attempt_kind: {attempt_kind!r}")
    audit_row: dict[str, Any] = {
        "attempt_kind": attempt_kind,
        "generated_candidate_id": _bounded(
            generated_candidate_id, MAX_GENERATED_CANDIDATE_ID_LEN
        ),
        "stop_status": stop_status,
        "warnings": [w for w in warnings if w in WRITER_WARNINGS],
        "writer_module_version": MODULE_VERSION,
        "generated_at_utc": now_utc,
    }
    assert_no_secrets(audit_row)
    # Existing audit lines are preserved verbatim so the audit log
    # remains an append-only forensic trail.
    existing_lines: list[str] = []
    if audit_path.is_file():
        try:
            existing_text = audit_path.read_text(encoding="utf-8")
        except OSError:
            existing_text = ""
        for line in existing_text.splitlines():
            s = line.strip()
            if s:
                existing_lines.append(s)
    new_line = json.dumps(audit_row, sort_keys=True)
    _atomic_replace_jsonl(
        audit_path,
        existing_lines=existing_lines,
        new_line=new_line,
        write_prefix_check=_ALLOWED_AUDIT_PREFIX,
    )


# ---------------------------------------------------------------------------
# Public API: append
# ---------------------------------------------------------------------------


def append_generated_seed_record(
    record: Any,
    *,
    generated_seed_path: Path | None = None,
    audit_path: Path | None = None,
    env: Mapping[str, str] | None = None,
    now_utc: str | None = None,
) -> dict[str, Any]:
    """Append a closed-schema record to ``generated_seed.jsonl``.

    Returns the closed-shape envelope (see :func:`_make_envelope`).
    Never raises for predictable failure modes; raises only when a
    path-sentinel violation is detected after we have already
    branched past the public-API guard.

    Default-disabled: when the env-gate is not satisfied, the
    function returns immediately with ``status="skipped"`` and
    creates no files of any kind (not even the audit log).
    """
    seed_path = (
        generated_seed_path
        if generated_seed_path is not None
        else GENERATED_SEED_PATH
    )
    audit = audit_path if audit_path is not None else AUDIT_PATH
    ts = now_utc if now_utc is not None else _utcnow()
    enabled = writer_enabled(env)

    # Best-effort scrape of the candidate id for the envelope and
    # for audit rows. The schema validation happens later; until
    # then we accept anything string-like, bounded.
    candidate_id_raw: str = ""
    if isinstance(record, dict):
        raw = record.get("generated_candidate_id")
        if isinstance(raw, str):
            candidate_id_raw = _bounded(raw, MAX_GENERATED_CANDIDATE_ID_LEN)

    if not enabled:
        # ZERO-WRITE behaviour. No seed file, no audit row.
        return _make_envelope(
            status="skipped",
            stop_status="writer_disabled",
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=False,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- Path-sentinel checks (writer is enabled) ----
    if not _seed_path_allowed(seed_path):
        # Even if a caller overrides the path, refuse anything that
        # isn't the canonical seed file — including any forbidden
        # seed file.
        _append_audit_row(
            audit,
            attempt_kind="rejected_path_refused",
            generated_candidate_id=candidate_id_raw,
            stop_status="path_refused",
            warnings=[],
            now_utc=ts,
        ) if _audit_path_allowed(audit) else None
        return _make_envelope(
            status="rejected",
            stop_status="path_refused",
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    if not _audit_path_allowed(audit):
        # We cannot safely write the rejection trail anywhere
        # because the audit path is also outside the sentinel.
        # Refuse the whole operation; never write the seed.
        return _make_envelope(
            status="rejected",
            stop_status="path_refused",
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- Schema validation ----
    ok, schema_stop, _validation_warnings = validate_record(record)
    if not ok:
        _append_audit_row(
            audit,
            attempt_kind="rejected_invalid_record_schema",
            generated_candidate_id=candidate_id_raw,
            stop_status=schema_stop,
            warnings=[],
            now_utc=ts,
        )
        return _make_envelope(
            status="rejected",
            stop_status=schema_stop,
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- assert_no_secrets on the candidate record ----
    try:
        assert_no_secrets(record)
    except Exception:
        _append_audit_row(
            audit,
            attempt_kind="rejected_secret_detected",
            generated_candidate_id=candidate_id_raw,
            stop_status="secret_detected",
            warnings=[],
            now_utc=ts,
        )
        return _make_envelope(
            status="rejected",
            stop_status="secret_detected",
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- Read existing records (default-deny on malformed line) ----
    read_status, existing = _read_existing_records(seed_path)
    if read_status == "malformed":
        _append_audit_row(
            audit,
            attempt_kind="rejected_existing_file_malformed",
            generated_candidate_id=candidate_id_raw,
            stop_status="existing_file_malformed",
            warnings=[],
            now_utc=ts,
        )
        return _make_envelope(
            status="rejected",
            stop_status="existing_file_malformed",
            generated_candidate_id=candidate_id_raw,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- Duplicate-candidate-id hard reject ----
    candidate_id = record["generated_candidate_id"]
    for existing_row in existing:
        if existing_row.get("generated_candidate_id") == candidate_id:
            _append_audit_row(
                audit,
                attempt_kind="rejected_duplicate_candidate_id",
                generated_candidate_id=candidate_id,
                stop_status="duplicate_candidate_id",
                warnings=[],
                now_utc=ts,
            )
            return _make_envelope(
                status="rejected",
                stop_status="duplicate_candidate_id",
                generated_candidate_id=candidate_id,
                generated_seed_path=seed_path,
                audit_path=audit,
                writer_enabled_flag=True,
                warnings=[],
                generated_at_utc=ts,
            )

    # ---- Cap check ----
    if len(existing) >= MAX_GENERATED_SEED_RECORDS:
        _append_audit_row(
            audit,
            attempt_kind="rejected_max_records_reached",
            generated_candidate_id=candidate_id,
            stop_status="max_records_reached",
            warnings=[],
            now_utc=ts,
        )
        return _make_envelope(
            status="rejected",
            stop_status="max_records_reached",
            generated_candidate_id=candidate_id,
            generated_seed_path=seed_path,
            audit_path=audit,
            writer_enabled_flag=True,
            warnings=[],
            generated_at_utc=ts,
        )

    # ---- Soft warning: duplicate evidence_hash (different candidate id) ----
    cross_warnings: list[str] = []
    evidence_hash = record["evidence_hash"]
    if evidence_hash:
        for existing_row in existing:
            if (
                existing_row.get("evidence_hash") == evidence_hash
                and existing_row.get("generated_candidate_id") != candidate_id
            ):
                cross_warnings.append("duplicate_evidence_hash")
                break

    # ---- Atomic append to generated_seed.jsonl ----
    existing_lines: list[str] = []
    if seed_path.is_file():
        try:
            text = seed_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        for line in text.splitlines():
            s = line.strip()
            if s:
                existing_lines.append(s)
    new_line = json.dumps(record, sort_keys=True)
    _atomic_replace_jsonl(
        seed_path,
        existing_lines=existing_lines,
        new_line=new_line,
        # Sentinel substring on the seed path is the exact basename.
        # _seed_path_allowed already verified this is the canonical
        # path, but the helper enforces the substring guard again
        # so a future refactor cannot accidentally widen the surface.
        write_prefix_check=_ALLOWED_SEED_BASENAME,
    )

    # ---- Audit row for success ----
    _append_audit_row(
        audit,
        attempt_kind="written",
        generated_candidate_id=candidate_id,
        stop_status="none",
        warnings=cross_warnings,
        now_utc=ts,
    )

    return _make_envelope(
        status="written",
        stop_status="none",
        generated_candidate_id=candidate_id,
        generated_seed_path=seed_path,
        audit_path=audit,
        writer_enabled_flag=True,
        warnings=cross_warnings,
        generated_at_utc=ts,
    )


# ---------------------------------------------------------------------------
# CLI — operator status inspection only. The CLI does NOT accept a
# record on stdin (defense in depth).
# ---------------------------------------------------------------------------


def _status_snapshot(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Pure snapshot of the writer's current posture. Reads the
    env-gate and the on-disk record count, but writes nothing."""
    enabled = writer_enabled(env)
    record_count = 0
    if GENERATED_SEED_PATH.is_file():
        try:
            text = GENERATED_SEED_PATH.read_text(encoding="utf-8")
        except OSError:
            text = ""
        record_count = sum(1 for line in text.splitlines() if line.strip())
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "writer_enabled": enabled,
        "env_var_name": ENV_WRITER_ENABLED,
        "generated_seed_path": str(GENERATED_SEED_PATH),
        "audit_path": str(AUDIT_PATH),
        "record_count": record_count,
        "max_records_cap": MAX_GENERATED_SEED_RECORDS,
        "step5_implementation_allowed": step5_implementation_allowed,
        "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
        "level6_enabled": False,
        "vocabularies": {
            "writer_admission_previews": list(WRITER_ADMISSION_PREVIEWS),
            "writer_block_reasons": list(WRITER_BLOCK_REASONS),
            "writer_warnings": list(WRITER_WARNINGS),
            "audit_attempt_kinds": list(AUDIT_ATTEMPT_KINDS),
            "generated_record_keys": list(GENERATED_RECORD_KEYS),
        },
        "discipline_invariants": dict(_DISCIPLINE_INVARIANTS),
        "generated_at_utc": _utcnow(),
    }
    assert_no_secrets(snapshot)
    return snapshot


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_generated_lane_writer",
        description=(
            "A18b generated_seed.jsonl writer — status inspection "
            "only. The CLI does NOT accept a record on stdin; "
            "appends go through the Python public API "
            "(append_generated_seed_record). NEVER writes when the "
            "env-gate is not exactly 'true'."
        ),
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "No-op flag accepted for parity with sibling reporting "
            "modules. The CLI never writes regardless; this flag "
            "exists so the standard gate command shape applies."
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
    snap = _status_snapshot()
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
