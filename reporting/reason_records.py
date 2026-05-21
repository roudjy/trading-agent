"""Routing / Sampling / Scoring Reason Records — append-only writer + reader.

Implements [docs/governance/reason_records.md] (doctrine) and
[docs/governance/reason_records/schema.v1.md] (schema). Pins
invariants RR-I1..RR-I10.

The module:

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Append-only. No UPDATE / DELETE.
* Idempotent on ``record_id``.
* Deterministic ``record_id`` over (decision_kind, subject_id,
  inputs_digest).
* Three closed ``decision_kind`` families (routing, sampling,
  scoring) written to three separate JSONLs.
* Closed ``decision`` vocab per family.
* Closed ``reason_codes`` vocab per family.
* Atomic writes (``tmp`` + ``os.replace``).
* Write target restricted to ``logs/reason_records/`` (atomic
  allowlist substring).
* No frozen-contract mutation.
* No imports from execution-side surfaces.

CLI
---

::

    python -m reporting.reason_records --status
    python -m reporting.reason_records --subject <id>
    python -m reporting.reason_records --kind routing|sampling|scoring

There is no execute-safe mode; the CLI never writes.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.16.0"
SCHEMA_VERSION: Final[int] = 1
RECORD_KIND: Final[str] = "reason_record"


# ---------------------------------------------------------------------------
# Closed vocabularies (RR-I5)
# ---------------------------------------------------------------------------


DECISION_KIND_ROUTING: Final[str] = "routing"
DECISION_KIND_SAMPLING: Final[str] = "sampling"
DECISION_KIND_SCORING: Final[str] = "scoring"

DECISION_KINDS: Final[tuple[str, ...]] = (
    DECISION_KIND_ROUTING,
    DECISION_KIND_SAMPLING,
    DECISION_KIND_SCORING,
)


#: Closed ``decision`` vocab for each ``decision_kind``. Mirrors
#: docs/governance/reason_records/schema.v1.md §2 verbatim.
DECISIONS_BY_KIND: Final[Mapping[str, tuple[str, ...]]] = {
    DECISION_KIND_ROUTING: (
        "prioritize",
        "dead_zone_suppress",
        "defer",
        "reject",
    ),
    DECISION_KIND_SAMPLING: (
        "stratify",
        "null_baseline",
        "exclude_region",
        "downsample",
        "upsample",
    ),
    DECISION_KIND_SCORING: (
        "keep",
        "filter_tail",
        "filter_entropy",
        "filter_null",
        "filter_cost",
        "undecided",
    ),
}


#: Closed ``reason_codes`` anchor vocab per family. Mirrors
#: docs/governance/reason_records/schema.v1.md §3.
REASON_CODES_BY_KIND: Final[Mapping[str, frozenset[str]]] = {
    DECISION_KIND_ROUTING: frozenset({
        "info_gain_high",
        "info_gain_low",
        "dead_zone_dwell_exceeded",
        "dependency_unmet",
        "multiplicity_budget_exceeded",
        "operator_directive",
    }),
    DECISION_KIND_SAMPLING: frozenset({
        "coverage_imbalance",
        "regime_mismatch",
        "null_baseline_required",
        "multiplicity_budget_remaining",
        "operator_directive",
    }),
    DECISION_KIND_SCORING: frozenset({
        "null_p_value_above_threshold",
        "null_p_value_below_threshold",
        "tail_fragility_high",
        "tail_fragility_low",
        "entropy_regime_compatible",
        "entropy_regime_incompatible",
        "cost_gate_pass",
        "cost_gate_fail",
        "dsr_threshold_pass",
        "dsr_threshold_fail",
        "operator_directive",
    }),
}


#: Maximum reason-text length (RR-I10 helper bound).
MAX_REASON_TEXT_LEN: Final[int] = 300

#: Maximum subject_id length (per schema §1).
MAX_SUBJECT_ID_LEN: Final[int] = 64

#: Maximum serialised record size (RR-I10).
MAX_RECORD_BYTES: Final[int] = 2048

#: Schema field set, exact and ordered (for byte-identical
#: serialisation per schema.v1.md "Record shape").
RECORD_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "decision",
    "decision_kind",
    "inputs_digest",
    "reason_codes",
    "reason_text",
    "record_id",
    "schema_version",
    "subject_id",
    "ts_utc",
)

#: Secret-keyword denylist applied to reason_text (RR-I8-style).
_SECRET_PATTERNS: Final[tuple[str, ...]] = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "private_key",
)


# ---------------------------------------------------------------------------
# Artifact paths (atomic-write allowlist)
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "reason_records"
JSONL_PATH_BY_KIND: Final[Mapping[str, Path]] = {
    DECISION_KIND_ROUTING: ARTIFACT_DIR / "routing_v1.jsonl",
    DECISION_KIND_SAMPLING: ARTIFACT_DIR / "sampling_v1.jsonl",
    DECISION_KIND_SCORING: ARTIFACT_DIR / "scoring_v1.jsonl",
}
MANIFEST_PATH: Final[Path] = ARTIFACT_DIR / "manifest.v1.json"

#: Atomic-write allowlist substring. Any write target whose
#: normalised path does not contain this substring raises
#: ``ValueError``. RR-I8.
_WRITE_PREFIX: Final[str] = "logs/reason_records/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_write_target(path: Path) -> None:
    """Refuse any write target that does not pass through
    ``_WRITE_PREFIX``. Mirrors the discipline in
    ``reporting/roadmap_priority.py``. RR-I8."""
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            f"reason_records: refusing write outside allowlist: {path!r}"
        )


def _has_secret_pattern(text: str) -> bool:
    """Return True if ``text`` contains any case-insensitive
    secret-keyword pattern. Conservative; rejects rather than
    risks leaking."""
    low = text.lower()
    return any(p in low for p in _SECRET_PATTERNS)


def _canonical_json(obj: Mapping[str, Any]) -> str:
    """Sorted keys, no whitespace, UTF-8. Per schema §5."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_record_id(
    decision_kind: str, subject_id: str, inputs_digest: str
) -> str:
    """Deterministic record_id over (decision_kind, subject_id,
    inputs_digest). RR-I4."""
    h = hashlib.sha256()
    h.update(decision_kind.encode("utf-8"))
    h.update(b"\x1f")
    h.update(subject_id.encode("utf-8"))
    h.update(b"\x1f")
    h.update(inputs_digest.encode("utf-8"))
    return "rr_" + h.hexdigest()[:16]


def compute_inputs_digest(payload: Mapping[str, Any]) -> str:
    """sha256 of canonical-json(payload). Pure helper for callers
    that want a digest over their inputs."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_record(record: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` if ``record`` violates schema.v1.md.
    Otherwise return ``None``. Pure."""
    # Field-set match (RR-I5 prerequisite).
    missing = set(RECORD_SCHEMA_KEYS) - set(record.keys())
    if missing:
        raise ValueError(
            f"reason_records: record missing fields: {sorted(missing)}"
        )
    extras = set(record.keys()) - set(RECORD_SCHEMA_KEYS)
    if extras:
        raise ValueError(
            f"reason_records: record has unexpected fields: {sorted(extras)}"
        )

    # schema_version
    sv = record["schema_version"]
    if sv != SCHEMA_VERSION:
        raise ValueError(
            f"reason_records: schema_version must be {SCHEMA_VERSION}, "
            f"got {sv!r}"
        )

    # decision_kind closed (RR-I5)
    dk = record["decision_kind"]
    if dk not in DECISION_KINDS:
        raise ValueError(
            f"reason_records: decision_kind {dk!r} not in {DECISION_KINDS!r}"
        )

    # decision closed per family (RR-I5)
    dec = record["decision"]
    allowed_decisions = DECISIONS_BY_KIND[dk]
    if dec not in allowed_decisions:
        raise ValueError(
            f"reason_records: decision {dec!r} not allowed for kind "
            f"{dk!r}; allowed={allowed_decisions!r}"
        )

    # reason_codes closed per family (RR-I5)
    rcs = record["reason_codes"]
    if not isinstance(rcs, list):
        raise ValueError("reason_records: reason_codes must be a list")
    allowed_codes = REASON_CODES_BY_KIND[dk]
    for code in rcs:
        if not isinstance(code, str) or code not in allowed_codes:
            raise ValueError(
                f"reason_records: reason_code {code!r} not in family "
                f"{dk!r} closed vocab"
            )

    # subject_id length
    sid = record["subject_id"]
    if not isinstance(sid, str) or not sid:
        raise ValueError("reason_records: subject_id must be a non-empty str")
    if len(sid) > MAX_SUBJECT_ID_LEN:
        raise ValueError(
            f"reason_records: subject_id length > {MAX_SUBJECT_ID_LEN}"
        )

    # inputs_digest 64-char hex
    idg = record["inputs_digest"]
    if not isinstance(idg, str) or len(idg) != 64 or not all(
        c in "0123456789abcdef" for c in idg
    ):
        raise ValueError(
            "reason_records: inputs_digest must be 64-char lower hex"
        )

    # record_id derivation match (RR-I4)
    expected_id = compute_record_id(dk, sid, idg)
    if record["record_id"] != expected_id:
        raise ValueError(
            f"reason_records: record_id mismatch; expected {expected_id!r}, "
            f"got {record['record_id']!r}"
        )

    # reason_text length + no-PII
    rt = record["reason_text"]
    if not isinstance(rt, str):
        raise ValueError("reason_records: reason_text must be a str")
    if len(rt) > MAX_REASON_TEXT_LEN:
        raise ValueError(
            f"reason_records: reason_text length > {MAX_REASON_TEXT_LEN}"
        )
    if _has_secret_pattern(rt):
        raise ValueError(
            "reason_records: reason_text contains a forbidden secret keyword"
        )

    # ts_utc parses
    ts = record["ts_utc"]
    if not isinstance(ts, str):
        raise ValueError("reason_records: ts_utc must be a str")
    try:
        _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(
            f"reason_records: ts_utc not parsable: {e}"
        ) from None

    # Total serialised size (RR-I10).
    serialised = _canonical_json(record)
    if len(serialised.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError(
            f"reason_records: serialised record > {MAX_RECORD_BYTES} bytes"
        )


def build_record(
    *,
    decision_kind: str,
    subject_id: str,
    decision: str,
    reason_codes: Sequence[str],
    reason_text: str,
    inputs: Mapping[str, Any] | None = None,
    inputs_digest: str | None = None,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    """Construct a fully-validated record. ``inputs_digest`` may be
    provided by the caller or derived from ``inputs``.

    Pure; idempotent for identical inputs.
    """
    if inputs_digest is None:
        if inputs is None:
            raise ValueError(
                "reason_records: either inputs or inputs_digest required"
            )
        inputs_digest = compute_inputs_digest(inputs)

    ts = frozen_utc or _utcnow()
    rid = compute_record_id(decision_kind, subject_id, inputs_digest)

    record: dict[str, Any] = {
        "decision": decision,
        "decision_kind": decision_kind,
        "inputs_digest": inputs_digest,
        "reason_codes": list(reason_codes),
        "reason_text": reason_text,
        "record_id": rid,
        "schema_version": SCHEMA_VERSION,
        "subject_id": subject_id,
        "ts_utc": ts,
    }
    validate_record(record)
    return record


# ---------------------------------------------------------------------------
# Read API (RR-I7 pure read)
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file. Pure. Skips blank lines. Raises on
    malformed JSON."""
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            out.append(json.loads(s))
    return out


def read_kind(
    decision_kind: str,
    subject_id: str | None = None,
    *,
    artifact_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Return records for the named ``decision_kind``, optionally
    filtered by ``subject_id``. Pure read."""
    if decision_kind not in DECISION_KINDS:
        raise ValueError(
            f"reason_records: unknown decision_kind {decision_kind!r}"
        )
    base = artifact_dir or ARTIFACT_DIR
    path = base / JSONL_PATH_BY_KIND[decision_kind].name
    records = _read_jsonl(path)
    if subject_id is not None:
        records = [r for r in records if r.get("subject_id") == subject_id]
    return records


def fused_for_subject(
    subject_id: str,
    *,
    artifact_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Return time-ordered union of records that reference
    ``subject_id`` across all three families. Pure read."""
    out: list[dict[str, Any]] = []
    for kind in DECISION_KINDS:
        out.extend(
            read_kind(kind, subject_id=subject_id, artifact_dir=artifact_dir)
        )
    out.sort(key=lambda r: (r.get("ts_utc", ""), r.get("record_id", "")))
    return out


def collect_manifest(
    *,
    artifact_dir: Path | None = None,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    """Return a stat-summary of the three reason-record JSONLs.
    Pure read."""
    base = artifact_dir or ARTIFACT_DIR
    by_kind: dict[str, int] = {}
    by_decision: dict[str, dict[str, int]] = {}
    by_subject_counter: dict[str, int] = {}
    first_ts: str | None = None
    last_ts: str | None = None
    total = 0
    for kind in DECISION_KINDS:
        path = base / JSONL_PATH_BY_KIND[kind].name
        records = _read_jsonl(path)
        by_kind[kind] = len(records)
        bd: dict[str, int] = {}
        for r in records:
            total += 1
            dec = str(r.get("decision", ""))
            bd[dec] = bd.get(dec, 0) + 1
            sid = str(r.get("subject_id", ""))
            if sid:
                by_subject_counter[sid] = by_subject_counter.get(sid, 0) + 1
            ts = r.get("ts_utc")
            if isinstance(ts, str):
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
        by_decision[kind] = bd
    # Top-16 most active subjects (deterministic order).
    top = sorted(
        by_subject_counter.items(), key=lambda kv: (-kv[1], kv[0])
    )[:16]
    note = "no_records" if total == 0 else "records_present"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": frozen_utc or _utcnow(),
        "total_records": total,
        "by_kind": by_kind,
        "by_decision": by_decision,
        "by_subject_id_top": {k: v for k, v in top},
        "first_record_ts_utc": first_ts,
        "last_record_ts_utc": last_ts,
        "note": note,
    }


# ---------------------------------------------------------------------------
# Write API (RR-I1 append-only, RR-I2 idempotent)
# ---------------------------------------------------------------------------


def _existing_ids(path: Path) -> set[str]:
    """Return the set of ``record_id``s already present in ``path``.
    Pure read."""
    ids: set[str] = set()
    for r in _read_jsonl(path):
        rid = r.get("record_id")
        if isinstance(rid, str):
            ids.add(rid)
    return ids


def append(
    record: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, Any]:
    """Atomic append of one validated record. Idempotent on
    ``record_id`` (RR-I2). Refuses any write outside the
    atomic-write allowlist (RR-I8).

    Returns a small status dict:

    * ``{"status": "appended", "path": <rel>, "record_id": <rid>}``
      if the record was new.
    * ``{"status": "skipped_duplicate", "record_id": <rid>}``
      if the record_id already exists in the target JSONL.

    Raises ``ValueError`` on any schema violation, oversize
    record, or forbidden write target.
    """
    validate_record(record)
    base = artifact_dir or ARTIFACT_DIR
    kind = record["decision_kind"]
    path = base / JSONL_PATH_BY_KIND[kind].name
    _validate_write_target(path)

    # RR-I2 idempotence.
    rid = record["record_id"]
    if rid in _existing_ids(path):
        return {"status": "skipped_duplicate", "record_id": rid}

    base.mkdir(parents=True, exist_ok=True)
    # RR-I1 append-only: open in append mode; never overwrite.
    line = _canonical_json(record) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)

    # Rebuild the manifest. Atomic via tmp + os.replace.
    manifest_path = base / MANIFEST_PATH.name
    _validate_write_target(manifest_path)
    manifest = collect_manifest(artifact_dir=base)
    payload = json.dumps(manifest, sort_keys=True, indent=2)
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, manifest_path)

    try:
        rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        rel = str(path).replace("\\", "/")
    return {
        "status": "appended",
        "path": rel,
        "record_id": rid,
    }


# ---------------------------------------------------------------------------
# CLI (read-only)
# ---------------------------------------------------------------------------


def _cmd_status() -> dict[str, Any]:
    return collect_manifest()


def _cmd_subject(subject_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "subject_id": subject_id,
        "records": fused_for_subject(subject_id),
    }


def _cmd_kind(decision_kind: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "decision_kind": decision_kind,
        "records": read_kind(decision_kind),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.reason_records",
        description=(
            "Read-only inspector for routing / sampling / scoring "
            "reason records. The CLI never writes."
        ),
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--subject", type=str, default=None)
    parser.add_argument(
        "--kind",
        type=str,
        choices=DECISION_KINDS,
        default=None,
    )
    args = parser.parse_args(argv)

    if args.subject is not None:
        payload = _cmd_subject(args.subject)
    elif args.kind is not None:
        payload = _cmd_kind(args.kind)
    else:
        # --status or default
        payload = _cmd_status()

    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
