"""Minimal v3.15.16 Intelligent Routing slice (reset deliverable).

Implements the **minimal slice** declared by queue item 2 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3, established by the
roadmap reset in PR #264 / #266 and the research-quality sprint in
PR #267).

This module is a **sibling** to ``reporting.intelligent_routing``
(the v3.15.16 advisory layer). They coexist:

* ``reporting.intelligent_routing`` — read-only advisory digest
  over the existing research artefacts; ``routing_effect ==
  "advisory_only"``; no decision ladder, no reason-records
  emission.
* ``reporting.intelligent_routing_minimal`` (this module) —
  deterministic five-rule decision ladder with explicit
  routing-reason-record emission via
  :mod:`reporting.reason_records`.

Scope (binding, "minimal"):

* deterministic routing prioritisation by expected information
  gain;
* dead-zone suppression by deterministic dwell threshold;
* deferral on unmet dependencies;
* rejection on exhausted multiplicity budget;
* one structured routing reason record per candidate;
* read-only digest writer + CLI for operator inspection.

Out of scope (explicit; ADDENDUMS DEFERRED):

* diagnostic-aware routing (Addendum 1 — DEFERRED);
* state-aware routing, retrieval-aware routing, knowledge-aware
  routing (Addendum 2 — DEFERRED);
* source-quality-aware routing (Addendum 3 — DEFERRED);
* adaptive routing / stochastic routing / hidden ranking
  authority;
* any execution-side feed;
* any frozen-contract mutation.

The module:

* is stdlib-only (no ``subprocess``, no ``gh``, no ``git``, no
  network);
* is pure / deterministic — two runs on the same input produce a
  byte-identical ``items`` list (modulo ``generated_at_utc``);
* never invokes the producer of any upstream artifact;
* writes only under ``logs/intelligent_routing_minimal/`` (atomic
  allowlist substring);
* never imports execution-side modules;
* mutates no frozen contract.

CLI
---

::

    python -m reporting.intelligent_routing_minimal --status
    python -m reporting.intelligent_routing_minimal --no-write

There is no execute-safe mode; ``safe_to_execute`` is hard-coded
``false`` at the digest level.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from reporting import reason_records as _rr

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.16-minimal-reset-2026-05-21"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "intelligent_routing_minimal_digest"


# ---------------------------------------------------------------------------
# Heuristic constants (deterministic; pinned).
# ---------------------------------------------------------------------------


#: Dead-zone dwell at or above this many ticks suppresses the
#: candidate. Pinned by tests.
DEFAULT_DEAD_ZONE_DWELL_THRESHOLD: Final[int] = 3

#: Below this expected information gain (closed interval
#: ``[0.0, 1.0]``) the candidate is deferred rather than
#: prioritised. Pinned by tests.
DEFAULT_LOW_INFO_GAIN_THRESHOLD: Final[float] = 0.15

#: Closed routing decision vocab. Mirrors
#: ``reporting.reason_records.DECISIONS_BY_KIND['routing']``.
ROUTING_DECISIONS: Final[tuple[str, ...]] = (
    "prioritize",
    "dead_zone_suppress",
    "defer",
    "reject",
)


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "intelligent_routing_minimal"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"

#: Atomic-write allowlist substring.
_WRITE_PREFIX: Final[str] = "logs/intelligent_routing_minimal/"


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


#: Closed set of fields the caller must provide per candidate.
INPUT_CANDIDATE_KEYS: Final[tuple[str, ...]] = (
    "campaign_id",
    "info_gain_estimate",
    "dead_zone_dwell",
    "dependency_unmet",
    "multiplicity_budget_remaining",
)

#: Closed set of fields the digest emits per candidate.
OUTPUT_CANDIDATE_KEYS: Final[tuple[str, ...]] = (
    "campaign_id",
    "decision",
    "priority_score",
    "rank",
    "reason_codes",
    "reason_text",
    "record_id",
)

#: Maximum number of candidates accepted in a single snapshot.
#: Pinned to keep operator surfaces bounded.
MAX_CANDIDATES: Final[int] = 256


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
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "intelligent_routing_minimal: refusing write outside "
            f"allowlist: {path!r}"
        )


def _bounded_float(value: Any) -> float:
    """Coerce to a float in ``[0.0, 1.0]``."""
    if not isinstance(value, (int, float)):
        return 0.0
    f = float(value)
    if f != f:  # NaN
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _bounded_int(value: Any) -> int:
    if not isinstance(value, (int, float)):
        return 0
    return int(value)


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> None:
    """Raise ``ValueError`` on any malformed candidate. Pure."""
    if not isinstance(candidates, (list, tuple)):
        raise ValueError(
            "intelligent_routing_minimal: candidates must be a "
            f"list/tuple, got {type(candidates).__name__}"
        )
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(
            "intelligent_routing_minimal: too many candidates "
            f"({len(candidates)} > {MAX_CANDIDATES})"
        )
    seen: set[str] = set()
    for i, c in enumerate(candidates):
        if not isinstance(c, Mapping):
            raise ValueError(
                "intelligent_routing_minimal: "
                f"candidate[{i}] must be a mapping"
            )
        missing = set(INPUT_CANDIDATE_KEYS) - set(c.keys())
        if missing:
            raise ValueError(
                "intelligent_routing_minimal: "
                f"candidate[{i}] missing fields: {sorted(missing)}"
            )
        cid = c["campaign_id"]
        if not isinstance(cid, str) or not cid:
            raise ValueError(
                "intelligent_routing_minimal: "
                f"candidate[{i}].campaign_id must be a non-empty str"
            )
        if cid in seen:
            raise ValueError(
                "intelligent_routing_minimal: "
                f"duplicate campaign_id {cid!r}"
            )
        seen.add(cid)
        if not isinstance(c["dependency_unmet"], bool):
            raise ValueError(
                "intelligent_routing_minimal: "
                f"candidate[{i}].dependency_unmet must be a bool"
            )


# ---------------------------------------------------------------------------
# Decision logic (deterministic; five-rule ladder)
# ---------------------------------------------------------------------------


def _classify_one(
    c: Mapping[str, Any],
    *,
    dead_zone_threshold: int,
    low_info_threshold: float,
) -> tuple[str, list[str], str, float]:
    """Return ``(decision, reason_codes, reason_text, priority_score)``
    for one candidate. Pure.

    Precedence (first match wins; deterministic):

    1. ``multiplicity_budget_remaining <= 0`` -> ``reject``
       (``multiplicity_budget_exceeded``).
    2. ``dependency_unmet`` -> ``defer`` (``dependency_unmet``).
    3. ``dead_zone_dwell >= dead_zone_threshold`` ->
       ``dead_zone_suppress`` (``dead_zone_dwell_exceeded``).
    4. ``info_gain_estimate < low_info_threshold`` -> ``defer``
       (``info_gain_low``).
    5. otherwise -> ``prioritize`` (``info_gain_high``).
    """
    info_gain = _bounded_float(c["info_gain_estimate"])
    dwell = _bounded_int(c["dead_zone_dwell"])
    dep_unmet = bool(c["dependency_unmet"])
    budget = _bounded_int(c["multiplicity_budget_remaining"])

    if budget <= 0:
        return (
            "reject",
            ["multiplicity_budget_exceeded"],
            (
                "Multiplicity budget exhausted; routing rejects until "
                "budget is renewed."
            ),
            0.0,
        )
    if dep_unmet:
        return (
            "defer",
            ["dependency_unmet"],
            "Unmet dependency; routing defers until cleared.",
            info_gain,
        )
    if dwell >= dead_zone_threshold:
        return (
            "dead_zone_suppress",
            ["dead_zone_dwell_exceeded"],
            (
                f"Dead-zone dwell {dwell} >= threshold "
                f"{dead_zone_threshold}; routing suppresses."
            ),
            0.0,
        )
    if info_gain < low_info_threshold:
        return (
            "defer",
            ["info_gain_low"],
            (
                f"Estimated information gain {info_gain:.4f} < threshold "
                f"{low_info_threshold:.4f}; routing defers."
            ),
            info_gain,
        )
    return (
        "prioritize",
        ["info_gain_high"],
        (
            f"Estimated information gain {info_gain:.4f} >= threshold "
            f"{low_info_threshold:.4f}; routing prioritises."
        ),
        info_gain,
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    candidates: Sequence[Mapping[str, Any]] | None = None,
    *,
    dead_zone_threshold: int = DEFAULT_DEAD_ZONE_DWELL_THRESHOLD,
    low_info_threshold: float = DEFAULT_LOW_INFO_GAIN_THRESHOLD,
    frozen_utc: str | None = None,
    artifact_dir_for_reasons: Path | None = None,
    emit_reason_records: bool = True,
) -> dict[str, Any]:
    """Pure, deterministic projection over ``candidates``.

    If ``emit_reason_records`` is True (default) the function
    appends one reason record per candidate via
    :func:`reporting.reason_records.append`. The append is
    idempotent on ``record_id`` (RR-I2), so re-running the
    snapshot is safe.

    ``candidates is None`` is treated as an empty list (used by
    the CLI when no upstream artifact exists yet).
    """
    items_in: Sequence[Mapping[str, Any]] = candidates or []
    validate_candidates(items_in)

    ts = frozen_utc or _utcnow()

    classified: list[dict[str, Any]] = []
    for c in items_in:
        decision, reason_codes, reason_text, score = _classify_one(
            c,
            dead_zone_threshold=dead_zone_threshold,
            low_info_threshold=low_info_threshold,
        )

        inputs_payload: dict[str, Any] = {
            "campaign_id": c["campaign_id"],
            "info_gain_estimate": _bounded_float(c["info_gain_estimate"]),
            "dead_zone_dwell": _bounded_int(c["dead_zone_dwell"]),
            "dependency_unmet": bool(c["dependency_unmet"]),
            "multiplicity_budget_remaining": _bounded_int(
                c["multiplicity_budget_remaining"]
            ),
            "dead_zone_threshold": dead_zone_threshold,
            "low_info_threshold": low_info_threshold,
        }
        record = _rr.build_record(
            decision_kind=_rr.DECISION_KIND_ROUTING,
            subject_id=str(c["campaign_id"]),
            decision=decision,
            reason_codes=reason_codes,
            reason_text=reason_text,
            inputs=inputs_payload,
            frozen_utc=ts,
        )

        if emit_reason_records:
            _rr.append(record, artifact_dir=artifact_dir_for_reasons)

        classified.append(
            {
                "campaign_id": str(c["campaign_id"]),
                "decision": decision,
                "priority_score": round(score, 6),
                "rank": -1,
                "reason_codes": list(reason_codes),
                "reason_text": reason_text,
                "record_id": record["record_id"],
            }
        )

    # Deterministic sort: prioritised items first, by descending
    # priority_score; deterministic tiebreaker by campaign_id.
    decision_rank = {
        "prioritize": 0,
        "defer": 1,
        "dead_zone_suppress": 2,
        "reject": 3,
    }
    classified.sort(
        key=lambda it: (
            decision_rank.get(it["decision"], 99),
            -it["priority_score"],
            it["campaign_id"],
        )
    )
    for i, it in enumerate(classified):
        it["rank"] = i

    counts_by_decision = {d: 0 for d in ROUTING_DECISIONS}
    for it in classified:
        counts_by_decision[it["decision"]] = (
            counts_by_decision.get(it["decision"], 0) + 1
        )

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "thresholds": {
            "dead_zone_dwell_threshold": dead_zone_threshold,
            "low_info_gain_threshold": low_info_threshold,
        },
        "counts": {
            "total": len(classified),
            "by_decision": counts_by_decision,
        },
        "items": classified,
        "final_recommendation": (
            "ready_for_implementation"
            if counts_by_decision.get("prioritize", 0) > 0
            else "nothing_ready"
        ),
        "note": (
            "Minimal v3.15.16 reset slice. Five-rule decision ladder "
            "only; no diagnostic / state / retrieval / source-aware "
            "routing (Addendums 1/2/3 are deferred)."
        ),
    }
    return snapshot


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    """Atomic write of ``latest.json`` + timestamped copy +
    history append. Mirrors ``reporting.roadmap_priority``.
    """
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    json_now = base / f"{ts}.json"
    json_latest = base / ARTIFACT_LATEST.name
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    _validate_write_target(json_now)
    _validate_write_target(json_latest)
    _validate_write_target(history)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot(
    *, artifact_dir: Path | None = None
) -> dict[str, Any] | None:
    p = (artifact_dir / ARTIFACT_LATEST.name) if artifact_dir else ARTIFACT_LATEST
    if not p.is_file():
        return None
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.intelligent_routing_minimal",
        description=(
            "Minimal v3.15.16 Intelligent Routing reset slice — "
            "deterministic projection. The CLI never executes "
            "anything; safe_to_execute is hard-coded false."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Inspect only; do not write any artifact.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Read the latest digest without re-running.",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=("dry-run",),
        help="Only dry-run is allowed.",
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin the timestamp for deterministic tests.",
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "module_version": MODULE_VERSION,
                        "final_recommendation": "not_available",
                        "note": "no latest snapshot",
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
            return 0
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    # CLI dry-run runs over an empty input set as a smoke check.
    # Operator-driven wiring passes ``candidates=...`` via Python.
    snap = collect_snapshot(
        candidates=[],
        frozen_utc=args.frozen_utc,
        emit_reason_records=False,
    )

    if not args.no_write:
        out = write_outputs(snap)
        snap["_artifact_paths"] = out

    print(json.dumps(snap, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
