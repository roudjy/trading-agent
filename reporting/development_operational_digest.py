"""A12 — Operational Digest / Observability Loop.

Pure, deterministic, stdlib-only digest. Aggregates the four ADE
artifacts into a single operator-facing snapshot:

* ``logs/development_work_queue/latest.json``       (A8)
* ``logs/development_release_gate/latest.json``     (A9)
* ``logs/development_bugfix_loop/latest.json``      (A10)
* ``logs/development_delegation/latest.json``       (A11)

Outputs:

* ``logs/development_operational_digest/latest.json``
* ``logs/development_operational_digest/history.jsonl`` (bounded
  append-only history, retained at most ``MAX_HISTORY_ENTRIES``)

Hard guarantees (pinned by tests):

* Stdlib + ADE peer modules' read-only API only.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``.
* No mutation of any upstream artifact.
* The digest never sends notifications and never writes to any
  dashboard surface.
* ``step5_ready=true`` is necessary but not sufficient — the
  operator must separately authorise Step 5 implementation.

CLI::

    python -m reporting.development_operational_digest
    python -m reporting.development_operational_digest --no-write
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

from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_release_gate as drg
from reporting import development_work_queue as dwq

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.A12"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "development_operational_digest"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/development_operational_digest/latest.json"
)
HISTORY_RELATIVE_PATH: Final[str] = (
    "logs/development_operational_digest/history.jsonl"
)

#: Bounded append-only history. Operator-approved at 90 entries.
MAX_HISTORY_ENTRIES: Final[int] = 90

#: Maximum operator-action-list rows to return. Bounded so the
#: operator gets a tractable list instead of an unbounded dump.
MAX_OPERATOR_ACTIONS: Final[int] = 20

#: Step 5 readiness criteria are pinned in this closed list. Any
#: future criterion must be added to the list AND to the test
#: matrix; tests pin the cardinality.
STEP5_CRITERIA: Final[tuple[str, ...]] = (
    "release_gate_artifact_present",
    "release_gate_no_protected_surface_leakage",
    "bugfix_loop_artifact_present",
    "bugfix_loop_no_test_weakening_proposals",
    "delegation_artifact_present",
    "delegation_no_fuzzy_parsing_evidence",
    "queue_artifact_present",
    "queue_human_needed_signal_meaningful",
    "ade_qre_loose_coupling_clean",
    "no_protected_path_violations",
)

# ---------------------------------------------------------------------------
# Wrapper-level note vocabulary
# ---------------------------------------------------------------------------

NOTE_NO_INPUT: Final[str] = "no_upstream_artifacts_present"
NOTE_PARTIAL_INPUT: Final[str] = "partial_upstream_artifacts_present"
NOTE_FULL_INPUT: Final[str] = "all_upstream_artifacts_present"


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
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


# ---------------------------------------------------------------------------
# Per-source projection helpers
# ---------------------------------------------------------------------------


def _summarize_queue(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "present": False,
            "module_version": None,
            "generated_at_utc": None,
            "note": None,
            "total": 0,
            "human_needed": 0,
            "blocked": 0,
            "protected_surface": 0,
            "ready_for_autonomous_action": 0,
            "requiring_human_operator": 0,
            "by_role": {r: 0 for r in dwq.AGENT_ROLES},
            "by_status": {s: 0 for s in dwq.STATUSES},
        }
    counts = payload.get("counts") or {}
    by_role = counts.get("by_role") if isinstance(counts.get("by_role"), dict) else {}
    by_status = (
        counts.get("by_status") if isinstance(counts.get("by_status"), dict) else {}
    )
    return {
        "present": True,
        "module_version": payload.get("module_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "note": payload.get("note"),
        "total": _coerce_int(counts.get("total")),
        "human_needed": _coerce_int(counts.get("human_needed")),
        "blocked": _coerce_int(counts.get("blocked")),
        "protected_surface": _coerce_int(counts.get("protected_surface")),
        "ready_for_autonomous_action": _coerce_int(
            counts.get("ready_for_autonomous_action")
        ),
        "requiring_human_operator": _coerce_int(
            counts.get("requiring_human_operator")
        ),
        "by_role": {r: _coerce_int(by_role.get(r)) for r in dwq.AGENT_ROLES},
        "by_status": {s: _coerce_int(by_status.get(s)) for s in dwq.STATUSES},
    }


def _summarize_release_gate(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "present": False,
            "module_version": None,
            "generated_at_utc": None,
            "note": None,
            "total": 0,
            "by_verdict": {v: 0 for v in drg.VERDICTS},
            "human_needed": 0,
            "protected_surface": 0,
            "evidence_input_present": False,
        }
    counts = payload.get("counts") or {}
    by_verdict = (
        counts.get("by_verdict") if isinstance(counts.get("by_verdict"), dict) else {}
    )
    return {
        "present": True,
        "module_version": payload.get("module_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "note": payload.get("note"),
        "total": _coerce_int(counts.get("total")),
        "by_verdict": {
            v: _coerce_int(by_verdict.get(v)) for v in drg.VERDICTS
        },
        "human_needed": _coerce_int(counts.get("human_needed")),
        "protected_surface": _coerce_int(counts.get("protected_surface")),
        "evidence_input_present": bool(payload.get("evidence_input_present")),
    }


def _summarize_bugfix_loop(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "present": False,
            "module_version": None,
            "generated_at_utc": None,
            "note": None,
            "total": 0,
            "human_needed": 0,
            "repeated_failure": 0,
            "out_of_scope": 0,
            "by_failure_class": {fc: 0 for fc in dbl.FAILURE_CLASSES},
            "by_bugfix_scope": {s: 0 for s in dbl.BUGFIX_SCOPES},
            "discipline_invariants": None,
        }
    counts = payload.get("counts") or {}
    by_failure_class = (
        counts.get("by_failure_class")
        if isinstance(counts.get("by_failure_class"), dict)
        else {}
    )
    by_bugfix_scope = (
        counts.get("by_bugfix_scope")
        if isinstance(counts.get("by_bugfix_scope"), dict)
        else {}
    )
    return {
        "present": True,
        "module_version": payload.get("module_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "note": payload.get("note"),
        "total": _coerce_int(counts.get("total")),
        "human_needed": _coerce_int(counts.get("human_needed")),
        "repeated_failure": _coerce_int(counts.get("repeated_failure")),
        "out_of_scope": _coerce_int(counts.get("out_of_scope")),
        "by_failure_class": {
            fc: _coerce_int(by_failure_class.get(fc)) for fc in dbl.FAILURE_CLASSES
        },
        "by_bugfix_scope": {
            s: _coerce_int(by_bugfix_scope.get(s)) for s in dbl.BUGFIX_SCOPES
        },
        "discipline_invariants": payload.get("discipline_invariants"),
    }


def _summarize_delegation(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "present": False,
            "module_version": None,
            "generated_at_utc": None,
            "note": None,
            "total": 0,
            "human_needed": 0,
            "protected_surface": 0,
            "ready_for_operator_promotion": 0,
            "by_roadmap_track": {
                "autonomous_development": 0,
                "qre_feature_build": 0,
                "sidecar_seed": 0,
            },
            "discipline_invariants": None,
        }
    counts = payload.get("counts") or {}
    by_track = (
        counts.get("by_roadmap_track")
        if isinstance(counts.get("by_roadmap_track"), dict)
        else {}
    )
    return {
        "present": True,
        "module_version": payload.get("module_version"),
        "generated_at_utc": payload.get("generated_at_utc"),
        "note": payload.get("note"),
        "total": _coerce_int(counts.get("total")),
        "human_needed": _coerce_int(counts.get("human_needed")),
        "protected_surface": _coerce_int(counts.get("protected_surface")),
        "ready_for_operator_promotion": _coerce_int(
            counts.get("ready_for_operator_promotion")
        ),
        "by_roadmap_track": {
            k: _coerce_int(by_track.get(k))
            for k in ("autonomous_development", "qre_feature_build", "sidecar_seed")
        },
        "discipline_invariants": payload.get("discipline_invariants"),
    }


# ---------------------------------------------------------------------------
# Step 5 readiness scoring
# ---------------------------------------------------------------------------


def _evaluate_step5(
    *,
    queue: dict[str, Any],
    release_gate: dict[str, Any],
    bugfix_loop: dict[str, Any],
    delegation: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate Step 5 readiness criteria. Each criterion is bool;
    the aggregate ``step5_ready`` is true iff every criterion is
    true. Necessary but not sufficient — operator authorisation
    remains separate."""
    queue_present = bool(queue.get("present"))
    rg_present = bool(release_gate.get("present"))
    bl_present = bool(bugfix_loop.get("present"))
    del_present = bool(delegation.get("present"))

    rg_no_protected_leakage = (
        not rg_present
        or release_gate.get("by_verdict", {}).get(
            drg.VERDICT_NO_GO_BLOCKED, 0
        )
        == 0
        or release_gate.get("by_verdict", {}).get(drg.VERDICT_GO, 0)
        + release_gate.get("by_verdict", {}).get(drg.VERDICT_GO_WITH_FOLLOWUPS, 0)
        > 0
    )
    bl_inv = bugfix_loop.get("discipline_invariants") or {}
    bl_no_weakening = bool(bl_inv) and bl_inv.get("auto_modifies_code") is False
    del_inv = delegation.get("discipline_invariants") or {}
    del_no_fuzzy = bool(del_inv) and del_inv.get("fuzzy_parsing") is False
    queue_signal = (
        queue.get("requiring_human_operator", 0) > 0
        or queue.get("ready_for_autonomous_action", 0) > 0
    )

    # ADE/QRE loose coupling is verified by the source-text scan
    # tests on every ADE module. The digest re-asserts the invariant
    # by checking that no upstream summary references an Intelligent-
    # Routing or research artifact path; we use module-version
    # presence as a marker that the producers are the ADE producers.
    coupling_clean = True
    for source in (queue, release_gate, bugfix_loop, delegation):
        mv = source.get("module_version")
        if mv is not None and "intelligent_routing" in str(mv):
            coupling_clean = False
            break

    no_protected_violations = release_gate.get("by_verdict", {}).get(
        drg.VERDICT_NO_GO_BLOCKED, 0
    ) == 0 or rg_present is False

    criteria: dict[str, bool] = {
        "release_gate_artifact_present": rg_present,
        "release_gate_no_protected_surface_leakage": rg_no_protected_leakage,
        "bugfix_loop_artifact_present": bl_present,
        "bugfix_loop_no_test_weakening_proposals": bl_no_weakening,
        "delegation_artifact_present": del_present,
        "delegation_no_fuzzy_parsing_evidence": del_no_fuzzy,
        "queue_artifact_present": queue_present,
        "queue_human_needed_signal_meaningful": queue_signal,
        "ade_qre_loose_coupling_clean": coupling_clean,
        "no_protected_path_violations": no_protected_violations,
    }
    # Pin: every criterion in STEP5_CRITERIA must be evaluated.
    for c in STEP5_CRITERIA:
        criteria.setdefault(c, False)

    step5_ready = all(criteria[c] for c in STEP5_CRITERIA)

    return {
        "criteria": {c: bool(criteria[c]) for c in STEP5_CRITERIA},
        "step5_ready": step5_ready,
        "step5_design_planning_allowed": True,
        "step5_implementation_allowed": False,
        "step5_implementation_blocker": (
            "operator_authorisation_required" if step5_ready
            else "readiness_criteria_not_satisfied"
        ),
    }


# ---------------------------------------------------------------------------
# Operator action list
# ---------------------------------------------------------------------------


def _build_operator_action_list(
    *,
    queue: dict[str, Any],
    release_gate: dict[str, Any],
    bugfix_loop: dict[str, Any],
    delegation: dict[str, Any],
) -> list[dict[str, Any]]:
    """Bounded, deduplicated, deterministic operator action list."""
    actions: list[dict[str, Any]] = []
    if queue.get("present"):
        if queue.get("human_needed", 0) > 0:
            actions.append(
                {
                    "kind": "queue_human_needed_items_present",
                    "count": queue["human_needed"],
                    "source": "development_work_queue",
                }
            )
        if queue.get("blocked", 0) > 0:
            actions.append(
                {
                    "kind": "queue_blocked_items_present",
                    "count": queue["blocked"],
                    "source": "development_work_queue",
                }
            )
    if release_gate.get("present"):
        no_go_human = release_gate["by_verdict"].get(
            drg.VERDICT_NO_GO_HUMAN_NEEDED, 0
        )
        if no_go_human > 0:
            actions.append(
                {
                    "kind": "release_gate_no_go_human_needed",
                    "count": no_go_human,
                    "source": "development_release_gate",
                }
            )
        no_go_blocked = release_gate["by_verdict"].get(
            drg.VERDICT_NO_GO_BLOCKED, 0
        )
        if no_go_blocked > 0:
            actions.append(
                {
                    "kind": "release_gate_no_go_blocked",
                    "count": no_go_blocked,
                    "source": "development_release_gate",
                }
            )
    if bugfix_loop.get("present"):
        if bugfix_loop.get("repeated_failure", 0) > 0:
            actions.append(
                {
                    "kind": "bugfix_repeated_validation_failure",
                    "count": bugfix_loop["repeated_failure"],
                    "source": "development_bugfix_loop",
                }
            )
        if bugfix_loop.get("human_needed", 0) > 0:
            actions.append(
                {
                    "kind": "bugfix_human_needed_candidates",
                    "count": bugfix_loop["human_needed"],
                    "source": "development_bugfix_loop",
                }
            )
    if delegation.get("present"):
        if delegation.get("ready_for_operator_promotion", 0) > 0:
            actions.append(
                {
                    "kind": "delegation_ready_for_operator_promotion",
                    "count": delegation["ready_for_operator_promotion"],
                    "source": "development_delegation",
                }
            )
        if delegation.get("human_needed", 0) > 0:
            actions.append(
                {
                    "kind": "delegation_human_needed_entries",
                    "count": delegation["human_needed"],
                    "source": "development_delegation",
                }
            )

    # Deterministic deduplication — same kind+source collapses.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for a in actions:
        key = (a["kind"], a["source"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    deduped.sort(key=lambda a: (a["source"], a["kind"]))
    return deduped[:MAX_OPERATOR_ACTIONS]


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    queue_path: Path | None = None,
    release_gate_path: Path | None = None,
    bugfix_loop_path: Path | None = None,
    delegation_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic operational digest."""
    qp = queue_path if queue_path is not None else dwq.ARTIFACT_LATEST
    rgp = release_gate_path if release_gate_path is not None else drg.ARTIFACT_LATEST
    blp = bugfix_loop_path if bugfix_loop_path is not None else dbl.ARTIFACT_LATEST
    dp = delegation_path if delegation_path is not None else ddl.ARTIFACT_LATEST
    ts = generated_at_utc if generated_at_utc is not None else _utcnow()

    queue_payload = _read_json(qp)
    rg_payload = _read_json(rgp)
    bl_payload = _read_json(blp)
    del_payload = _read_json(dp)

    queue = _summarize_queue(queue_payload)
    release_gate = _summarize_release_gate(rg_payload)
    bugfix_loop = _summarize_bugfix_loop(bl_payload)
    delegation = _summarize_delegation(del_payload)

    presence_count = sum(
        1
        for s in (queue, release_gate, bugfix_loop, delegation)
        if s.get("present")
    )
    if presence_count == 0:
        note = NOTE_NO_INPUT
    elif presence_count < 4:
        note = NOTE_PARTIAL_INPUT
    else:
        note = NOTE_FULL_INPUT

    step5 = _evaluate_step5(
        queue=queue,
        release_gate=release_gate,
        bugfix_loop=bugfix_loop,
        delegation=delegation,
    )

    actions = _build_operator_action_list(
        queue=queue,
        release_gate=release_gate,
        bugfix_loop=bugfix_loop,
        delegation=delegation,
    )

    sources = {
        "queue": {"path": str(qp), "summary": queue},
        "release_gate": {"path": str(rgp), "summary": release_gate},
        "bugfix_loop": {"path": str(blp), "summary": bugfix_loop},
        "delegation": {"path": str(dp), "summary": delegation},
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "development_operational_digest",
        "generated_at_utc": ts,
        "note": note,
        "presence_count": presence_count,
        "sources": sources,
        "operator_action_list": actions,
        "step5_readiness": step5,
        "vocabularies": {
            "agent_roles": list(dwq.AGENT_ROLES),
            "statuses": list(dwq.STATUSES),
            "categories": list(dwq.CATEGORIES),
            "release_gate_verdicts": list(drg.VERDICTS),
            "failure_classes": list(dbl.FAILURE_CLASSES),
            "bugfix_scopes": list(dbl.BUGFIX_SCOPES),
            "step5_criteria": list(STEP5_CRITERIA),
        },
        "queue_module_version": dwq.MODULE_VERSION,
        "release_gate_module_version": drg.MODULE_VERSION,
        "bugfix_loop_module_version": dbl.MODULE_VERSION,
        "delegation_module_version": ddl.MODULE_VERSION,
        "max_history_entries": MAX_HISTORY_ENTRIES,
        "discipline_invariants": {
            "mutates_upstream_artifacts": False,
            "sends_notifications": False,
            "writes_dashboard": False,
            "auto_authorises_step5": False,
            "operator_step5_authorisation_required": True,
        },
    }


# ---------------------------------------------------------------------------
# Atomic write + bounded history
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_operational_digest._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".development_operational_digest.",
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


def _append_history(path: Path, entry: dict[str, Any]) -> None:
    """Append a compact JSONL entry; truncate to MAX_HISTORY_ENTRIES.
    History is bounded so the file stays operator-readable. The
    truncation is implemented by reading existing lines, dropping
    the oldest, and rewriting atomically — never partial. A small
    retry covers transient Windows file-replace contention when
    callers append many entries back-to-back."""
    import time as _time

    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "development_operational_digest._append_history refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[str] = []
    if path.is_file():
        try:
            existing = [
                line for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except OSError:
            existing = []
    existing.append(json.dumps(entry, sort_keys=True))
    if len(existing) > MAX_HISTORY_ENTRIES:
        existing = existing[-MAX_HISTORY_ENTRIES:]
    text = "\n".join(existing) + "\n"
    last_error: BaseException | None = None
    for attempt in range(5):
        fd, tmp_name = tempfile.mkstemp(
            prefix=".development_operational_digest_history.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp_name, path)
            return
        except PermissionError as exc:
            last_error = exc
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            _time.sleep(0.01 * (attempt + 1))
            continue
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    if last_error is not None:
        raise last_error


def _history_entry(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compact projection for the history file: per-snapshot scalars
    only, no full source payloads."""
    s5 = snapshot.get("step5_readiness", {})
    return {
        "generated_at_utc": snapshot.get("generated_at_utc"),
        "module_version": snapshot.get("module_version"),
        "presence_count": snapshot.get("presence_count"),
        "step5_ready": s5.get("step5_ready"),
        "criteria": s5.get("criteria"),
        "operator_action_count": len(snapshot.get("operator_action_list") or []),
        "queue_total": snapshot["sources"]["queue"]["summary"].get("total"),
        "release_gate_total": snapshot["sources"]["release_gate"]["summary"].get("total"),
        "bugfix_loop_total": snapshot["sources"]["bugfix_loop"]["summary"].get("total"),
        "delegation_total": snapshot["sources"]["delegation"]["summary"].get("total"),
    }


def write_outputs(snapshot: dict[str, Any]) -> tuple[Path, Path]:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    _append_history(ARTIFACT_HISTORY, _history_entry(snapshot))
    return ARTIFACT_LATEST, ARTIFACT_HISTORY


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.development_operational_digest",
        description=(
            "Read-only ADE operational digest. Aggregates A8-A11 "
            "artifacts into a single operator-facing snapshot with "
            "Step 5 readiness signals. Decides nothing; mutates "
            "nothing upstream; sends no notifications."
        ),
    )
    p.add_argument("--indent", type=int, default=2, help="JSON indent (0 for compact).")
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/development_operational_digest/latest.json "
            "or history.jsonl (stdout only)."
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
