"""A9 — Agentic Release-Gate Integration.

Pure, deterministic, stdlib-only release-gate scorer for ADE work
items in ``category=release`` with ``status=validation_needed``.

The scorer consumes two read-only inputs and emits a closed-vocabulary
verdict per qualifying queue item:

1. The A8 development work queue artifact at
   ``logs/development_work_queue/latest.json``.
2. A structured **evidence input contract** at
   ``logs/release_gate_input/latest.json`` (or any path the caller
   supplies).

The evidence input contract is an additive, closed-vocabulary JSON
file. **ADE core never collects evidence itself.** Future
collectors/adapters that invoke ``gh``/``git``/CI APIs live outside
ADE core (preferred location: ``scripts/``). They produce the
evidence input file; this module reads it. Until such a collector
exists, the operator may populate the file by hand. The architecture
explicitly preserves the future collector path (see
``docs/governance/development_release_gate.md``).

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` + ``reporting.approval_policy`` +
  ``reporting.development_work_queue`` (read-only API only).
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* Pure functions. No mutation of any upstream artifact.
* Bounded scalars only — no PR text, no diffs, no body content.
* Atomic write only under ``logs/development_release_gate/latest.json``.

CLI::

    python -m reporting.development_release_gate
    python -m reporting.development_release_gate --indent 2
    python -m reporting.development_release_gate --no-write
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

from reporting import development_work_queue as dwq
from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A9"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: 5 release-gate verdicts.
VERDICTS: Final[tuple[str, ...]] = (
    "go",
    "go_with_followups",
    "no_go_blocked",
    "no_go_human_needed",
    "not_evaluated",
)

VERDICT_GO: Final[str] = "go"
VERDICT_GO_WITH_FOLLOWUPS: Final[str] = "go_with_followups"
VERDICT_NO_GO_BLOCKED: Final[str] = "no_go_blocked"
VERDICT_NO_GO_HUMAN_NEEDED: Final[str] = "no_go_human_needed"
VERDICT_NOT_EVALUATED: Final[str] = "not_evaluated"

#: Closed verdict_reason vocabulary. Each verdict has documented
#: reasons; all reasons map back to exactly one verdict.
VERDICT_REASONS: Final[tuple[str, ...]] = (
    # go
    "all_required_evidence_clean",
    # go_with_followups
    "clean_with_advisory_followups",
    # no_go_blocked
    "ci_failed",
    "smoke_failed",
    "governance_lint_failed",
    "frozen_contract_change_detected",
    "protected_path_modification_detected",
    "queue_cross_reference_inconsistent",
    # no_go_human_needed
    "protected_surface_present",
    "execution_authority_needs_human",
    "execution_authority_permanently_denied",
    # not_evaluated
    "evidence_input_missing",
    "required_evidence_absent",
    "ci_status_pending",
    "queue_artifact_missing",
    "queue_item_not_release_validation_needed",
)

#: 6 evidence keys the gate evaluates. Closed; additive only.
EVIDENCE_KEYS: Final[tuple[str, ...]] = (
    "ci_status",
    "smoke_status",
    "governance_lint_status",
    "frozen_hash_status",
    "no_touch_path_delta_status",
    "queue_cross_reference_status",
)

#: Closed value vocabulary per evidence key. Each key MUST report one
#: of these values when ``present=true``.
EVIDENCE_VALUE_VOCAB: Final[dict[str, tuple[str, ...]]] = {
    "ci_status": ("green", "red", "pending", "unknown"),
    "smoke_status": ("passed", "failed", "unknown"),
    "governance_lint_status": ("ok", "fail", "unknown"),
    "frozen_hash_status": ("stable", "drift", "unknown"),
    "no_touch_path_delta_status": ("clean", "violation", "unknown"),
    "queue_cross_reference_status": ("consistent", "missing_item", "unknown"),
}

#: Per-row schema keys; exact and ordered.
ROW_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "gate_id",
    "queue_item_id",
    "title",
    "verdict",
    "verdict_reason",
    "evidence_inputs",
    "missing_evidence",
    "required_followups",
    "human_needed",
    "human_needed_reason",
    "execution_authority_decision",
    "risk_level",
    "protected_surface",
    "created_at_placeholder",
    "updated_at_placeholder",
    "notes",
)

ITEM_TIME_PLACEHOLDER: Final[str] = "deterministic_seed_placeholder"

DEFAULT_QUEUE_ARTIFACT_PATH: Final[Path] = dwq.ARTIFACT_LATEST
DEFAULT_EVIDENCE_INPUT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "release_gate_input" / "latest.json"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_release_gate"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/development_release_gate/latest.json"

#: Bounded length for free-text fields.
MAX_TITLE_LEN: Final[int] = 200
MAX_NOTES_LEN: Final[int] = 1000
MAX_FOLLOWUPS: Final[int] = 16
MAX_FOLLOWUP_LINE_LEN: Final[int] = 200

#: Wrapper-level note vocabulary.
NOTE_NO_QUEUE_ARTIFACT: Final[str] = "queue_artifact_missing"
NOTE_NO_QUALIFYING_ITEMS: Final[str] = "no_release_validation_needed_items"
NOTE_NO_EVIDENCE_INPUT: Final[str] = "evidence_input_absent"
NOTE_VERDICTS_PRESENT: Final[str] = "verdicts_present"

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


def _bounded_str_list(value: Any, max_items: int, max_line_len: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value[:max_items]:
        if isinstance(v, str):
            out.append(_bounded_str(v, max_line_len))
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _deterministic_gate_id(queue_item_id: str, evidence_snapshot_id: str) -> str:
    h = hashlib.sha256()
    h.update(queue_item_id.encode("utf-8"))
    h.update(b"\x1f")
    h.update(evidence_snapshot_id.encode("utf-8"))
    return "rg_" + h.hexdigest()[:12]


def _evidence_snapshot_id(evidence: dict[str, Any]) -> str:
    """Deterministic id for the evidence payload. Used to make
    ``gate_id`` stable across runs with identical evidence."""
    canonical = json.dumps(evidence, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Evidence input parsing
# ---------------------------------------------------------------------------


def _normalize_evidence(raw: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    """Project the raw evidence input onto the closed vocabulary.

    Returns ``(normalized_evidence, warnings)``. Unknown keys are
    dropped; unknown values become ``unknown``."""
    warnings: list[str] = []
    normalized: dict[str, Any] = {}
    if not isinstance(raw, dict):
        for key in EVIDENCE_KEYS:
            normalized[key] = {"present": False, "value": "unknown"}
        if raw is not None:
            warnings.append("evidence_input_not_an_object")
        return normalized, warnings

    payload = raw.get("evidence")
    if not isinstance(payload, dict):
        for key in EVIDENCE_KEYS:
            normalized[key] = {"present": False, "value": "unknown"}
        warnings.append("evidence_block_missing")
        return normalized, warnings

    for key in EVIDENCE_KEYS:
        block = payload.get(key)
        if not isinstance(block, dict):
            normalized[key] = {"present": False, "value": "unknown"}
            continue
        present_raw = block.get("present")
        present = bool(present_raw) if isinstance(present_raw, bool) else False
        value_raw = block.get("value")
        allowed = EVIDENCE_VALUE_VOCAB[key]
        if isinstance(value_raw, str) and value_raw in allowed:
            value = value_raw
        else:
            value = "unknown"
            if present_raw is True:
                warnings.append(f"evidence_{key}_value_invalid")
        normalized[key] = {"present": present, "value": value}

    extra_keys = sorted(k for k in payload if k not in EVIDENCE_KEYS)
    for k in extra_keys[:8]:
        warnings.append(f"evidence_unknown_key_{k}")

    return normalized, warnings


# ---------------------------------------------------------------------------
# Verdict scoring
# ---------------------------------------------------------------------------


def _score_item(
    item: dict[str, Any],
    evidence: dict[str, Any],
    *,
    evidence_input_present: bool,
) -> tuple[str, str, list[str], list[str], list[str]]:
    """Return ``(verdict, verdict_reason, evidence_inputs,
    missing_evidence, required_followups)``.

    Precedence is intentionally first-match:
    1. queue item's protected_surface or NEEDS_HUMAN/PERMANENTLY_DENIED
       authority -> no_go_human_needed.
    2. queue artifact / evidence file totally absent -> not_evaluated.
    3. hard-block evidence violations -> no_go_blocked.
    4. pending evidence -> not_evaluated.
    5. missing required evidence -> not_evaluated.
    6. otherwise -> go (or go_with_followups when followups present)."""
    eaa = item.get("execution_authority")
    protected = bool(item.get("protected_surface"))

    if protected:
        return (
            VERDICT_NO_GO_HUMAN_NEEDED,
            "protected_surface_present",
            [],
            [],
            [],
        )

    if eaa == ea.DECISION_PERMANENTLY_DENIED:
        return (
            VERDICT_NO_GO_HUMAN_NEEDED,
            "execution_authority_permanently_denied",
            [],
            [],
            [],
        )
    if eaa == ea.DECISION_NEEDS_HUMAN:
        return (
            VERDICT_NO_GO_HUMAN_NEEDED,
            "execution_authority_needs_human",
            [],
            [],
            [],
        )

    if not evidence_input_present:
        return (
            VERDICT_NOT_EVALUATED,
            "evidence_input_missing",
            [],
            list(EVIDENCE_KEYS),
            [],
        )

    evidence_inputs: list[str] = []
    missing: list[str] = []
    for key in EVIDENCE_KEYS:
        block = evidence.get(key) or {}
        if block.get("present"):
            evidence_inputs.append(key)
        else:
            missing.append(key)

    # Hard-block precedence over not_evaluated: if any evaluated
    # evidence shows a hard violation, the item is no_go_blocked even
    # if some other evidence is missing.
    frozen = (evidence.get("frozen_hash_status") or {}).get("value")
    no_touch = (evidence.get("no_touch_path_delta_status") or {}).get("value")
    ci = (evidence.get("ci_status") or {}).get("value")
    smoke = (evidence.get("smoke_status") or {}).get("value")
    gov = (evidence.get("governance_lint_status") or {}).get("value")
    cross = (evidence.get("queue_cross_reference_status") or {}).get("value")

    frozen_present = (evidence.get("frozen_hash_status") or {}).get("present", False)
    no_touch_present = (
        evidence.get("no_touch_path_delta_status") or {}
    ).get("present", False)
    ci_present = (evidence.get("ci_status") or {}).get("present", False)
    smoke_present = (evidence.get("smoke_status") or {}).get("present", False)
    gov_present = (evidence.get("governance_lint_status") or {}).get("present", False)
    cross_present = (
        evidence.get("queue_cross_reference_status") or {}
    ).get("present", False)

    if frozen_present and frozen == "drift":
        return (
            VERDICT_NO_GO_BLOCKED,
            "frozen_contract_change_detected",
            evidence_inputs,
            missing,
            [],
        )
    if no_touch_present and no_touch == "violation":
        return (
            VERDICT_NO_GO_BLOCKED,
            "protected_path_modification_detected",
            evidence_inputs,
            missing,
            [],
        )
    if ci_present and ci == "red":
        return (
            VERDICT_NO_GO_BLOCKED,
            "ci_failed",
            evidence_inputs,
            missing,
            [],
        )
    if smoke_present and smoke == "failed":
        return (
            VERDICT_NO_GO_BLOCKED,
            "smoke_failed",
            evidence_inputs,
            missing,
            [],
        )
    if gov_present and gov == "fail":
        return (
            VERDICT_NO_GO_BLOCKED,
            "governance_lint_failed",
            evidence_inputs,
            missing,
            [],
        )
    if cross_present and cross == "missing_item":
        return (
            VERDICT_NO_GO_BLOCKED,
            "queue_cross_reference_inconsistent",
            evidence_inputs,
            missing,
            [],
        )

    if ci_present and ci == "pending":
        return (
            VERDICT_NOT_EVALUATED,
            "ci_status_pending",
            evidence_inputs,
            missing,
            [],
        )

    # Required evidence keys for a go verdict: everything must be
    # present and clean. If any required key is absent or unknown,
    # the verdict is not_evaluated.
    if missing:
        return (
            VERDICT_NOT_EVALUATED,
            "required_evidence_absent",
            evidence_inputs,
            missing,
            [],
        )
    unknown_values: list[str] = []
    for key in EVIDENCE_KEYS:
        block = evidence.get(key) or {}
        if block.get("value") == "unknown":
            unknown_values.append(key)
    if unknown_values:
        return (
            VERDICT_NOT_EVALUATED,
            "required_evidence_absent",
            evidence_inputs,
            unknown_values,
            [],
        )

    # All present + clean. Surface advisory follow-ups from the queue
    # item's validation_requirements if any (bounded).
    followups = _bounded_str_list(
        item.get("validation_requirements"), MAX_FOLLOWUPS, MAX_FOLLOWUP_LINE_LEN
    )
    if followups:
        return (
            VERDICT_GO_WITH_FOLLOWUPS,
            "clean_with_advisory_followups",
            evidence_inputs,
            [],
            followups,
        )

    return (
        VERDICT_GO,
        "all_required_evidence_clean",
        evidence_inputs,
        [],
        [],
    )


def _human_needed_for_verdict(verdict: str) -> bool:
    return verdict == VERDICT_NO_GO_HUMAN_NEEDED


def _human_needed_reason_for(item: dict[str, Any], verdict: str) -> str:
    if verdict != VERDICT_NO_GO_HUMAN_NEEDED:
        # Mirror the queue item's own value when available.
        raw = item.get("human_needed_reason")
        if isinstance(raw, str) and raw in dwq.HUMAN_NEEDED_REASONS:
            return raw
        return "none"
    if item.get("protected_surface"):
        return "protected_governance_change"
    eaa = item.get("execution_authority")
    if eaa == ea.DECISION_PERMANENTLY_DENIED:
        return "capital_or_live_execution_related"
    return "ambiguous_scope"


def _build_row(
    item: dict[str, Any],
    *,
    evidence: dict[str, Any],
    evidence_input_present: bool,
    evidence_snapshot_id: str,
) -> dict[str, Any]:
    verdict, reason, ev_inputs, missing, followups = _score_item(
        item, evidence, evidence_input_present=evidence_input_present
    )
    queue_item_id = str(item.get("item_id") or "")
    gate_id = _deterministic_gate_id(queue_item_id, evidence_snapshot_id)
    return {
        "gate_id": gate_id,
        "queue_item_id": queue_item_id,
        "title": _bounded_str(item.get("title"), MAX_TITLE_LEN),
        "verdict": verdict,
        "verdict_reason": reason,
        "evidence_inputs": ev_inputs,
        "missing_evidence": missing,
        "required_followups": followups,
        "human_needed": _human_needed_for_verdict(verdict),
        "human_needed_reason": _human_needed_reason_for(item, verdict),
        "execution_authority_decision": item.get("execution_authority"),
        "risk_level": item.get("risk_level"),
        "protected_surface": bool(item.get("protected_surface")),
        "created_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "updated_at_placeholder": ITEM_TIME_PLACEHOLDER,
        "notes": _bounded_str(item.get("notes"), MAX_NOTES_LEN),
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _qualifying_items(queue_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(queue_payload, dict):
        return []
    items = queue_payload.get("items")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if it.get("category") != "release":
            continue
        if it.get("status") != "validation_needed":
            continue
        out.append(it)
    return out


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_verdict": {v: 0 for v in VERDICTS},
        "by_verdict_reason": {r: 0 for r in VERDICT_REASONS},
        "human_needed": 0,
        "protected_surface": 0,
    }


def _aggregate_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _empty_counts()
    counts["total"] = len(rows)
    for row in rows:
        counts["by_verdict"][row["verdict"]] += 1
        counts["by_verdict_reason"][row["verdict_reason"]] += 1
        if row["human_needed"]:
            counts["human_needed"] += 1
        if row["protected_surface"]:
            counts["protected_surface"] += 1
    return counts


def collect_snapshot(
    *,
    queue_artifact_path: Path | None = None,
    evidence_input_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic release-gate snapshot.

    Args:
        queue_artifact_path: override the default
            ``logs/development_work_queue/latest.json`` source.
        evidence_input_path: override the default
            ``logs/release_gate_input/latest.json`` source.
        generated_at_utc: override the wrapper's report timestamp.
            ``None`` reads the runtime UTC clock; tests pass a fixed
            string to assert byte-stable output.
    """
    qp = queue_artifact_path if queue_artifact_path is not None else DEFAULT_QUEUE_ARTIFACT_PATH
    ep = evidence_input_path if evidence_input_path is not None else DEFAULT_EVIDENCE_INPUT_PATH
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    queue_payload = _read_json(qp)
    queue_present = queue_payload is not None

    evidence_payload = _read_json(ep)
    evidence_input_present = evidence_payload is not None
    normalized_evidence, evidence_warnings = _normalize_evidence(evidence_payload)
    snapshot_id = _evidence_snapshot_id(normalized_evidence)

    items = _qualifying_items(queue_payload)
    rows: list[dict[str, Any]] = []
    for it in items:
        rows.append(
            _build_row(
                it,
                evidence=normalized_evidence,
                evidence_input_present=evidence_input_present,
                evidence_snapshot_id=snapshot_id,
            )
        )

    rows.sort(key=lambda r: r["gate_id"])

    counts = _aggregate_counts(rows)

    if not queue_present:
        note = NOTE_NO_QUEUE_ARTIFACT
    elif not items:
        note = NOTE_NO_QUALIFYING_ITEMS
    elif not evidence_input_present:
        note = NOTE_NO_EVIDENCE_INPUT
    else:
        note = NOTE_VERDICTS_PRESENT

    validation_warnings: list[str] = list(evidence_warnings)
    # If the queue item is missing acceptance criteria, surface that.
    for it in items:
        ac = it.get("acceptance_criteria") or []
        if not isinstance(ac, list) or not ac:
            validation_warnings.append(
                f"queue_item_{it.get('item_id')}_missing_acceptance_criteria"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_release_gate",
        "generated_at_utc": ts,
        "queue_artifact_path": str(qp),
        "queue_artifact_present": queue_present,
        "evidence_input_path": str(ep),
        "evidence_input_present": evidence_input_present,
        "evidence_snapshot_id": snapshot_id,
        "note": note,
        "validation_warnings": validation_warnings,
        "vocabularies": {
            "verdicts": list(VERDICTS),
            "verdict_reasons": list(VERDICT_REASONS),
            "evidence_keys": list(EVIDENCE_KEYS),
            "evidence_value_vocab": {k: list(v) for k, v in EVIDENCE_VALUE_VOCAB.items()},
        },
        "counts": counts,
        "rows": rows,
        "execution_authority_module_version": ea.MODULE_VERSION,
        "queue_module_version": dwq.MODULE_VERSION,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_release_gate._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_release_gate.", suffix=".tmp", dir=str(path.parent)
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
        prog="python -m reporting.development_release_gate",
        description=(
            "Read-only release-gate scorer for ADE work items in "
            "category=release with status=validation_needed. Decides "
            "nothing destructive; mutates nothing. Evidence is "
            "consumed from logs/release_gate_input/latest.json; ADE "
            "core never collects evidence itself."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_release_gate/latest.json "
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
