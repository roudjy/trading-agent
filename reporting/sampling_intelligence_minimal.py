"""Minimal v3.15.17 Sampling Intelligence slice (reset deliverable).

Implements the **minimal slice** declared by queue item 3 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3, established by the
roadmap reset in PR #264 / #266, the research-quality sprint in
PR #267, and the routing slice in PR #268).

This module is the **sampling sibling** to
:mod:`reporting.intelligent_routing_minimal`. It applies the same
patterns:

* deterministic, pure projection over operator-provided sampling
  candidates;
* a deterministic decision ladder with explicit precedence;
* one structured sampling reason record per candidate, emitted via
  :mod:`reporting.reason_records`;
* atomic-write digest under ``logs/sampling_intelligence_minimal/``;
* read-only CLI for operator inspection;
* hard-coded ``safe_to_execute = false`` at the digest level.

Scope (binding, "minimal"):

* stratified sampling over existing coverage (closed-form
  imbalance comparison);
* null-baseline control sampling (deterministic gating on an
  operator-supplied flag);
* one sampling reason record per candidate;
* read-only digest writer + CLI for operator inspection.

Out of scope (explicit; ADDENDUMS DEFERRED):

* tail-aware / entropy-aware / phase-transition-aware sampling
  (Addendum 1 — DEFERRED);
* barrier / resonance / network / post-shock sampling families
  (Addendum 1 — DEFERRED);
* state-aware / retrieval-aware / knowledge-aware sampling
  (Addendum 2 — DEFERRED);
* source-quality-aware sampling (Addendum 3 — DEFERRED);
* adaptive / stochastic sampling, hidden ranking authority;
* any execution-side feed;
* any frozen-contract mutation.

The module:

* is stdlib-only (no ``subprocess``, no ``gh``, no ``git``, no
  network);
* is pure / deterministic — two runs on the same input produce a
  byte-identical ``items`` list (modulo ``generated_at_utc``);
* never invokes the producer of any upstream artefact;
* writes only under ``logs/sampling_intelligence_minimal/`` (atomic
  allowlist substring);
* never imports execution-side modules;
* mutates no frozen contract.

CLI
---

::

    python -m reporting.sampling_intelligence_minimal --status
    python -m reporting.sampling_intelligence_minimal --no-write

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
MODULE_VERSION: Final[str] = "v3.15.17-minimal-reset-2026-05-21"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "sampling_intelligence_minimal_digest"


# ---------------------------------------------------------------------------
# Heuristic constants (deterministic; pinned).
# ---------------------------------------------------------------------------


#: Symmetric coverage-imbalance threshold. A stratum is considered
#: imbalanced if ``|coverage_actual - coverage_target| > threshold``.
#: Pinned by tests.
DEFAULT_COVERAGE_IMBALANCE_THRESHOLD: Final[float] = 0.10

#: Closed sampling decision vocab. Mirrors
#: ``reporting.reason_records.DECISIONS_BY_KIND['sampling']``.
SAMPLING_DECISIONS: Final[tuple[str, ...]] = (
    "stratify",
    "null_baseline",
    "exclude_region",
    "downsample",
    "upsample",
)


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "sampling_intelligence_minimal"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"

#: Atomic-write allowlist substring.
_WRITE_PREFIX: Final[str] = "logs/sampling_intelligence_minimal/"


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


#: Closed set of fields the caller must provide per candidate.
INPUT_CANDIDATE_KEYS: Final[tuple[str, ...]] = (
    "stratum_id",
    "coverage_actual",
    "coverage_target",
    "regime_match",
    "null_baseline_required",
    "multiplicity_budget_remaining",
)

#: Closed set of fields the digest emits per candidate.
OUTPUT_CANDIDATE_KEYS: Final[tuple[str, ...]] = (
    "stratum_id",
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
            "sampling_intelligence_minimal: refusing write outside "
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
            "sampling_intelligence_minimal: candidates must be a "
            f"list/tuple, got {type(candidates).__name__}"
        )
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(
            "sampling_intelligence_minimal: too many candidates "
            f"({len(candidates)} > {MAX_CANDIDATES})"
        )
    seen: set[str] = set()
    for i, c in enumerate(candidates):
        if not isinstance(c, Mapping):
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"candidate[{i}] must be a mapping"
            )
        missing = set(INPUT_CANDIDATE_KEYS) - set(c.keys())
        if missing:
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"candidate[{i}] missing fields: {sorted(missing)}"
            )
        sid = c["stratum_id"]
        if not isinstance(sid, str) or not sid:
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"candidate[{i}].stratum_id must be a non-empty str"
            )
        if sid in seen:
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"duplicate stratum_id {sid!r}"
            )
        seen.add(sid)
        if not isinstance(c["regime_match"], bool):
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"candidate[{i}].regime_match must be a bool"
            )
        if not isinstance(c["null_baseline_required"], bool):
            raise ValueError(
                "sampling_intelligence_minimal: "
                f"candidate[{i}].null_baseline_required must be a bool"
            )


# ---------------------------------------------------------------------------
# Decision logic (deterministic; six-rule ladder)
# ---------------------------------------------------------------------------


def _classify_one(
    c: Mapping[str, Any],
    *,
    coverage_imbalance_threshold: float,
) -> tuple[str, list[str], str, float]:
    """Return ``(decision, reason_codes, reason_text, priority_score)``
    for one stratum candidate. Pure.

    Precedence (first match wins; deterministic):

    1. ``multiplicity_budget_remaining <= 0`` -> ``exclude_region``
       (``multiplicity_budget_remaining``) — budget exhausted.
    2. ``null_baseline_required`` -> ``null_baseline``
       (``null_baseline_required``) — control sampling owed.
    3. ``regime_match`` is False -> ``exclude_region``
       (``regime_mismatch``).
    4. ``coverage_actual < coverage_target - threshold`` ->
       ``upsample`` (``coverage_imbalance``).
    5. ``coverage_actual > coverage_target + threshold`` ->
       ``downsample`` (``coverage_imbalance``).
    6. otherwise -> ``stratify`` (``multiplicity_budget_remaining``).
    """
    coverage_actual = _bounded_float(c["coverage_actual"])
    coverage_target = _bounded_float(c["coverage_target"])
    regime_match = bool(c["regime_match"])
    null_baseline_required = bool(c["null_baseline_required"])
    budget = _bounded_int(c["multiplicity_budget_remaining"])

    delta = coverage_target - coverage_actual
    imbalance_magnitude = abs(delta)

    if budget <= 0:
        return (
            "exclude_region",
            ["multiplicity_budget_remaining"],
            (
                "Multiplicity budget exhausted; sampling excludes "
                "this stratum until the budget is renewed."
            ),
            0.0,
        )
    if null_baseline_required:
        return (
            "null_baseline",
            ["null_baseline_required"],
            (
                "Null-baseline control sampling owed for this "
                "stratum; sampling allocates a null-baseline draw."
            ),
            imbalance_magnitude,
        )
    if not regime_match:
        return (
            "exclude_region",
            ["regime_mismatch"],
            (
                "Operator-declared regime does not match this "
                "stratum; sampling excludes the region."
            ),
            0.0,
        )
    if coverage_actual + coverage_imbalance_threshold < coverage_target:
        return (
            "upsample",
            ["coverage_imbalance"],
            (
                f"Coverage {coverage_actual:.4f} is below target "
                f"{coverage_target:.4f} by more than "
                f"{coverage_imbalance_threshold:.4f}; sampling upsamples."
            ),
            imbalance_magnitude,
        )
    if coverage_actual > coverage_target + coverage_imbalance_threshold:
        return (
            "downsample",
            ["coverage_imbalance"],
            (
                f"Coverage {coverage_actual:.4f} exceeds target "
                f"{coverage_target:.4f} by more than "
                f"{coverage_imbalance_threshold:.4f}; sampling "
                f"downsamples."
            ),
            imbalance_magnitude,
        )
    return (
        "stratify",
        ["multiplicity_budget_remaining"],
        (
            f"Coverage {coverage_actual:.4f} within "
            f"{coverage_imbalance_threshold:.4f} of target "
            f"{coverage_target:.4f}; sampling stratifies."
        ),
        imbalance_magnitude,
    )


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def collect_snapshot(
    candidates: Sequence[Mapping[str, Any]] | None = None,
    *,
    coverage_imbalance_threshold: float = DEFAULT_COVERAGE_IMBALANCE_THRESHOLD,
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
    the CLI when no upstream artefact exists yet).
    """
    items_in: Sequence[Mapping[str, Any]] = candidates or []
    validate_candidates(items_in)

    ts = frozen_utc or _utcnow()

    classified: list[dict[str, Any]] = []
    for c in items_in:
        decision, reason_codes, reason_text, score = _classify_one(
            c,
            coverage_imbalance_threshold=coverage_imbalance_threshold,
        )

        inputs_payload: dict[str, Any] = {
            "stratum_id": c["stratum_id"],
            "coverage_actual": _bounded_float(c["coverage_actual"]),
            "coverage_target": _bounded_float(c["coverage_target"]),
            "regime_match": bool(c["regime_match"]),
            "null_baseline_required": bool(c["null_baseline_required"]),
            "multiplicity_budget_remaining": _bounded_int(
                c["multiplicity_budget_remaining"]
            ),
            "coverage_imbalance_threshold": coverage_imbalance_threshold,
        }
        record = _rr.build_record(
            decision_kind=_rr.DECISION_KIND_SAMPLING,
            subject_id=str(c["stratum_id"]),
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
                "stratum_id": str(c["stratum_id"]),
                "decision": decision,
                "priority_score": round(score, 6),
                "rank": -1,
                "reason_codes": list(reason_codes),
                "reason_text": reason_text,
                "record_id": record["record_id"],
            }
        )

    # Deterministic sort: actionable sampling decisions first, by
    # descending priority_score (imbalance magnitude), with
    # deterministic tiebreaker by stratum_id.
    decision_rank = {
        "stratify": 0,
        "null_baseline": 1,
        "upsample": 2,
        "downsample": 3,
        "exclude_region": 4,
    }
    classified.sort(
        key=lambda it: (
            decision_rank.get(it["decision"], 99),
            -it["priority_score"],
            it["stratum_id"],
        )
    )
    for i, it in enumerate(classified):
        it["rank"] = i

    counts_by_decision = {d: 0 for d in SAMPLING_DECISIONS}
    for it in classified:
        counts_by_decision[it["decision"]] = (
            counts_by_decision.get(it["decision"], 0) + 1
        )

    actionable = (
        counts_by_decision.get("stratify", 0)
        + counts_by_decision.get("null_baseline", 0)
        + counts_by_decision.get("upsample", 0)
        + counts_by_decision.get("downsample", 0)
    )

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "thresholds": {
            "coverage_imbalance_threshold": coverage_imbalance_threshold,
        },
        "counts": {
            "total": len(classified),
            "by_decision": counts_by_decision,
            "actionable": actionable,
        },
        "items": classified,
        "final_recommendation": (
            "ready_for_sampling" if actionable > 0 else "nothing_ready"
        ),
        "note": (
            "Minimal v3.15.17 reset slice. Six-rule decision ladder "
            "only; no tail / entropy / phase / barrier / resonance "
            "/ network / post-shock sampling families "
            "(Addendums 1/2/3 are deferred)."
        ),
    }
    return snapshot


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    """Atomic write of ``latest.json`` + timestamped copy +
    history append. Mirrors ``reporting.intelligent_routing_minimal``.
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
    base = artifact_dir or ARTIFACT_DIR
    p = base / ARTIFACT_LATEST.name
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
        prog="reporting.sampling_intelligence_minimal",
        description=(
            "Minimal v3.15.17 Sampling Intelligence reset slice — "
            "deterministic projection. The CLI never executes "
            "anything; safe_to_execute is hard-coded false."
        ),
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Inspect only; do not write any artefact.",
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
