"""v3.15.9 — funnel evidence artifact (non-frozen).

Pure builder module. No I/O inside the builder; the sidecar
write happens in ``run_research`` via
``research._sidecar_io.write_sidecar_atomic``.

Design rationale (REV 3 §6):

  * ``screening_evidence_latest.v1.json`` is **not** a frozen
    contract. v3.15.10 reads it; v3.15.11+ may extend it under a
    bumped schema_version.
  * Every per-candidate record carries:
      - phase + criteria split (passed / failed / diagnostic_only),
      - metrics (JSON-safe finite floats),
      - failure_reasons + near_pass distance,
      - sampling block (from v3.15.8),
      - promotion_guard (from v3.15.7 + paper signals),
      - evidence_fingerprint for v3.15.10 dedupe.
  * Identity fallback: a malformed candidate dict NEVER crashes
    the run. The builder synthesises a deterministic
    ``fb_<sha1prefix>`` candidate_id and counts the fallback in
    ``summary.identity_fallbacks`` so operators can spot a real
    upstream defect.
  * Ownership: ``col_campaign_id`` is the authoritative owner;
    ``campaign_id`` is a redundant alias in this release. v3.15.10
    matches on ``col_campaign_id`` first, falling back to
    ``campaign_id``.
  * NaN safety: every float passes through
    ``to_json_safe_float`` (NaN/inf -> None) before the canonical
    dump runs with ``allow_nan=False``. A direct unsanitised NaN
    therefore raises ``ValueError`` rather than silently
    corrupting the artifact.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research.screening_criteria import (
    EXPLORATORY_MAX_DRAWDOWN,
    EXPLORATORY_MIN_EXPECTANCY,
    EXPLORATORY_MIN_PROFIT_FACTOR,
)


SCREENING_EVIDENCE_PATH: Final[Path] = Path(
    "research/screening_evidence_latest.v1.json"
)
SCREENING_EVIDENCE_SCHEMA_VERSION: Final[str] = "1.0"


# v3.15.9 near-pass band constants (REV 3 §6.10).
EXPLORATORY_EXPECTANCY_NEAR_BAND: Final[float] = 0.0005
EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND: Final[float] = 0.05
EXPLORATORY_DRAWDOWN_NEAR_REL_BAND: Final[float] = 0.05


NEAR_PASS_ELIGIBLE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "expectancy_not_positive",
        "profit_factor_below_floor",
        "drawdown_above_exploratory_limit",
    }
)
NEAR_PASS_INELIGIBLE_REASONS: Final[frozenset[str]] = frozenset(
    {
        "insufficient_trades",
        "no_oos_samples",
        "candidate_budget_exceeded",
        "screening_candidate_error",
    }
)


# Stage-result string codes (REV 3 §6.7).
STAGE_RESULT_BASE_PASS: Final[str] = "screening_pass"
STAGE_RESULT_BASE_NEAR: Final[str] = "near_pass"
STAGE_RESULT_BASE_REJECT: Final[str] = "screening_reject"
STAGE_RESULT_UNKNOWN: Final[str] = "unknown"
STAGE_RESULT_DOWNSTREAM_PROMOTION: Final[str] = "promotion_candidate"
STAGE_RESULT_DOWNSTREAM_NEEDS_INV: Final[str] = "needs_investigation"
STAGE_RESULT_DOWNSTREAM_PAPER_BLOCK: Final[str] = "paper_blocked"


# Closed top-level key set; pinned by tests.
TOP_LEVEL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "generated_at_utc",
        "git_revision",
        "run_id",
        "campaign_id",
        "col_campaign_id",
        "preset_name",
        "screening_phase",
        "artifact_fingerprint",
        "summary",
        "candidates",
    }
)

# Closed per-candidate key set; pinned by tests.
PER_CANDIDATE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "candidate_id",
        "identity_fallback_used",
        "strategy_id",
        "strategy_name",
        "asset",
        "interval",
        "hypothesis_id",
        "preset_name",
        "screening_phase",
        "stage_result",
        "pass_kind",
        "screening_criteria_set",
        "metrics",
        "criteria",
        "failure_reasons",
        "near_pass",
        "sampling",
        "promotion_guard",
        "evidence_fingerprint",
    }
)


def to_json_safe_float(value: Any) -> float | None:
    """Coerce a metric value to a finite ``float`` or ``None``.

    ``None``, NaN and ±inf collapse to ``None``; primitives that
    can be cast to float are preserved as floats.
    """
    if value is None:
        return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(as_float) or math.isinf(as_float):
        return None
    return as_float


def _canonical_dump(payload: Any) -> str:
    """Canonical JSON dump used for fingerprints. ``allow_nan=False``
    is explicit: any unsanitised NaN/inf reaching this call is a
    programmer bug and raises immediately.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def artifact_fingerprint(payload_without_fingerprint: dict[str, Any]) -> str:
    """sha1 hex of the canonical-JSON payload, with the
    ``artifact_fingerprint`` key removed.
    """
    snapshot = dict(payload_without_fingerprint)
    snapshot.pop("artifact_fingerprint", None)
    return hashlib.sha1(_canonical_dump(snapshot).encode("utf-8")).hexdigest()


def candidate_evidence_fingerprint(record: dict[str, Any]) -> str:
    """Per-candidate fingerprint over the candidate sub-record
    (minus its own fingerprint key) so v3.15.10 can dedupe spawns
    by candidate identity + evidence content.
    """
    snapshot = dict(record)
    snapshot.pop("evidence_fingerprint", None)
    return hashlib.sha1(_canonical_dump(snapshot).encode("utf-8")).hexdigest()


def is_near_pass(
    *,
    screening_phase: str | None,
    failure_reasons: list[str],
    metrics: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Conservative near-pass classifier (REV 3 §6.10).

    Near-pass fires only when:
      - screening_phase == 'exploratory',
      - exactly ONE failure reason is present,
      - that reason is in NEAR_PASS_ELIGIBLE_REASONS,
      - the relevant metric lies within its near-band.

    Returns ``(False, None)`` for ineligible/multi-reason
    rejections, errors, timeouts, and insufficient_trades.
    """
    if screening_phase != "exploratory":
        return (False, None)
    if len(failure_reasons) != 1:
        return (False, None)
    reason = failure_reasons[0]
    if reason in NEAR_PASS_INELIGIBLE_REASONS:
        return (False, None)
    if reason not in NEAR_PASS_ELIGIBLE_REASONS:
        return (False, None)

    expectancy = to_json_safe_float(metrics.get("expectancy"))
    profit_factor = to_json_safe_float(metrics.get("profit_factor"))
    max_drawdown = to_json_safe_float(metrics.get("max_drawdown"))

    if reason == "expectancy_not_positive":
        if expectancy is not None and -EXPLORATORY_EXPECTANCY_NEAR_BAND <= expectancy <= EXPLORATORY_MIN_EXPECTANCY:
            return True, {
                "nearest_failed_criterion": reason,
                "distance": abs(expectancy),
            }
        return (False, None)

    if reason == "profit_factor_below_floor":
        floor = EXPLORATORY_MIN_PROFIT_FACTOR
        if profit_factor is not None and profit_factor >= floor * (
            1.0 - EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND
        ):
            return True, {
                "nearest_failed_criterion": reason,
                "distance": floor - profit_factor,
            }
        return (False, None)

    if reason == "drawdown_above_exploratory_limit":
        ceiling = EXPLORATORY_MAX_DRAWDOWN
        if max_drawdown is not None and max_drawdown <= ceiling * (
            1.0 + EXPLORATORY_DRAWDOWN_NEAR_REL_BAND
        ):
            return True, {
                "nearest_failed_criterion": reason,
                "distance": max_drawdown - ceiling,
            }
        return (False, None)

    return (False, None)


def dominant_failure_reasons(candidates: list[dict[str, Any]]) -> list[str]:
    """Sorted by frequency descending, alphabetical for tiebreak.

    Counts every distinct reason across all candidates'
    ``failure_reasons`` lists (i.e. multi-reason candidates
    contribute to multiple reason buckets).
    """
    counter: Counter[str] = Counter()
    for record in candidates:
        for reason in record.get("failure_reasons") or []:
            counter[str(reason)] += 1
    return [reason for reason, _count in sorted(
        counter.items(), key=lambda item: (-item[1], item[0])
    )]


def resolve_stage_result(
    *,
    screening_promoted: bool | None,
    is_near: bool,
    pass_kind: str | None,
    promotion_status: str | None,
    paper_blocked: bool,
) -> str:
    """Two-step stage_result resolution (REV 3 §6.7 + MF-5).

    Step 1: base state from screening promotion.
    Step 2: downstream override applies ONLY to a screening pass.

    A rejected near-pass remains ``near_pass``; downstream
    paper_blocked / promotion_candidate / needs_investigation
    cannot override a rejection.
    """
    if screening_promoted is None:
        return STAGE_RESULT_UNKNOWN
    if screening_promoted is False:
        return STAGE_RESULT_BASE_NEAR if is_near else STAGE_RESULT_BASE_REJECT
    # Step 2: only reachable when screening_promoted is True.
    if paper_blocked:
        return STAGE_RESULT_DOWNSTREAM_PAPER_BLOCK
    if pass_kind == "exploratory" or promotion_status == "needs_investigation":
        return STAGE_RESULT_DOWNSTREAM_NEEDS_INV
    if pass_kind in ("standard", "promotion_grade"):
        return STAGE_RESULT_DOWNSTREAM_PROMOTION
    return STAGE_RESULT_BASE_PASS


def _fallback_candidate_id(candidate: dict[str, Any]) -> str:
    """Deterministic ``fb_<sha1prefix>`` id used when the candidate
    dict lacks a usable ``candidate_id``. The prefix length (16
    hex chars / 64 bits) is large enough that collisions across a
    real research run are negligible.
    """
    base = json.dumps(
        {
            "strategy_id": str(
                candidate.get("strategy_id")
                or candidate.get("strategy_name")
                or ""
            ),
            "asset": str(candidate.get("asset") or ""),
            "interval": str(candidate.get("interval") or ""),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return "fb_" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _coerce_metrics(raw: dict[str, Any]) -> dict[str, float | None]:
    """JSON-safe metric block used in evidence records."""
    return {
        "win_rate": to_json_safe_float(raw.get("win_rate")),
        "expectancy": to_json_safe_float(raw.get("expectancy")),
        "profit_factor": to_json_safe_float(raw.get("profit_factor")),
        "max_drawdown": to_json_safe_float(raw.get("max_drawdown")),
        "totaal_trades": to_json_safe_float(raw.get("totaal_trades")),
        "trades_per_maand": to_json_safe_float(raw.get("trades_per_maand")),
        "deflated_sharpe": to_json_safe_float(raw.get("deflated_sharpe")),
        "consistentie": to_json_safe_float(raw.get("consistentie")),
    }


def _criteria_split(
    *,
    screening_phase: str | None,
    failure_reasons: list[str],
) -> dict[str, list[str]]:
    """Static criteria-split per phase (REV 3 §6.3).

    For the exploratory phase: hard gates are the three v3.15.7
    thresholds; diagnostic-only metrics are listed for operator
    visibility. For legacy/standard/promotion_grade we expose the
    legacy AND-gate as the single hard criterion.
    """
    if screening_phase == "exploratory":
        hard = [
            "expectancy_above_zero",
            "profit_factor_at_or_above_floor",
            "drawdown_within_limit",
            "sufficient_trades",
        ]
        diagnostic = ["win_rate", "deflated_sharpe", "consistentie"]
    else:
        hard = ["legacy_goedgekeurd_and_gate"]
        diagnostic = []
    failed = [str(reason) for reason in failure_reasons]
    passed = [name for name in hard if name not in failed]
    return {
        "passed": passed,
        "failed": failed,
        "diagnostic_only": diagnostic,
    }


def _build_candidate_record(
    *,
    candidate: dict[str, Any],
    screening_record: dict[str, Any],
    pass_kind: str | None,
    promotion_status: str | None,
    paper_blocking_reasons: list[str],
    preset_name: str | None,
    screening_phase: str | None,
) -> dict[str, Any]:
    """Build one per-candidate evidence record (without fingerprint).

    Tolerates malformed input: any missing identity field falls
    back to the deterministic ``fb_<sha1>`` id and the record
    flags ``identity_fallback_used=True``.
    """
    raw_id = candidate.get("candidate_id")
    identity_fallback_used = False
    if raw_id is None or not isinstance(raw_id, (str, int)) or str(raw_id).strip() == "":
        candidate_id = _fallback_candidate_id(candidate)
        identity_fallback_used = True
    else:
        candidate_id = str(raw_id)

    metrics = _coerce_metrics(screening_record.get("diagnostic_metrics") or {})
    failure_reasons: list[str] = []
    reason_code = screening_record.get("reason_code")
    if reason_code:
        failure_reasons.append(str(reason_code))
    final_status = screening_record.get("final_status")
    decision = screening_record.get("decision")
    if final_status == "passed" or decision == "promoted_to_validation":
        screening_promoted: bool | None = True
    elif final_status in {"rejected", "timed_out", "errored", "skipped"}:
        screening_promoted = False
    else:
        screening_promoted = None

    near_is_near, near_payload = is_near_pass(
        screening_phase=screening_phase,
        failure_reasons=failure_reasons,
        metrics=metrics,
    )
    near_block: dict[str, Any] = {
        "is_near_pass": bool(near_is_near),
        "distance": None,
        "nearest_failed_criterion": None,
    }
    if near_is_near and near_payload is not None:
        near_block["distance"] = to_json_safe_float(near_payload.get("distance"))
        near_block["nearest_failed_criterion"] = str(
            near_payload.get("nearest_failed_criterion")
        )

    paper_blocked = bool(paper_blocking_reasons)
    stage_result = resolve_stage_result(
        screening_promoted=screening_promoted,
        is_near=near_is_near,
        pass_kind=pass_kind,
        promotion_status=promotion_status,
        paper_blocked=paper_blocked,
    )

    sampling = dict(screening_record.get("sampling") or {})

    promotion_guard = {
        "promotion_allowed": (
            stage_result == STAGE_RESULT_DOWNSTREAM_PROMOTION
            and not paper_blocked
        ),
        "blocked_by": list(paper_blocking_reasons) if paper_blocking_reasons else [],
    }

    record: dict[str, Any] = {
        "candidate_id": candidate_id,
        "identity_fallback_used": identity_fallback_used,
        "strategy_id": str(
            candidate.get("strategy_id")
            or candidate.get("strategy_name")
            or ""
        ) or None,
        "strategy_name": str(candidate.get("strategy_name") or "") or None,
        "asset": str(candidate.get("asset") or "") or None,
        "interval": str(candidate.get("interval") or "") or None,
        "hypothesis_id": (
            str(candidate.get("hypothesis_id"))
            if candidate.get("hypothesis_id") is not None
            else None
        ),
        "preset_name": preset_name,
        "screening_phase": screening_phase,
        "stage_result": stage_result,
        "pass_kind": pass_kind if isinstance(pass_kind, str) else None,
        "screening_criteria_set": str(
            screening_record.get("screening_criteria_set") or "legacy"
        ),
        "metrics": metrics,
        "criteria": _criteria_split(
            screening_phase=screening_phase,
            failure_reasons=failure_reasons,
        ),
        "failure_reasons": failure_reasons,
        "near_pass": near_block,
        "sampling": sampling,
        "promotion_guard": promotion_guard,
    }
    record["evidence_fingerprint"] = candidate_evidence_fingerprint(record)
    return record


def _summarise(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = {
        "total_candidates": len(candidates),
        "passed_screening": 0,
        "rejected_screening": 0,
        "needs_investigation": 0,
        "promotion_grade_candidates": 0,
        "exploratory_passes": 0,
        "near_passes": 0,
        "coverage_warnings": 0,
        "identity_fallbacks": 0,
        "dominant_failure_reasons": dominant_failure_reasons(candidates),
    }
    for record in candidates:
        stage = record.get("stage_result")
        if stage in (
            STAGE_RESULT_BASE_PASS,
            STAGE_RESULT_DOWNSTREAM_PROMOTION,
            STAGE_RESULT_DOWNSTREAM_NEEDS_INV,
            STAGE_RESULT_DOWNSTREAM_PAPER_BLOCK,
        ):
            summary["passed_screening"] += 1
        elif stage in (STAGE_RESULT_BASE_REJECT, STAGE_RESULT_BASE_NEAR):
            summary["rejected_screening"] += 1
        if stage == STAGE_RESULT_DOWNSTREAM_NEEDS_INV:
            summary["needs_investigation"] += 1
        if stage == STAGE_RESULT_DOWNSTREAM_PROMOTION:
            summary["promotion_grade_candidates"] += 1
        if record.get("pass_kind") == "exploratory":
            summary["exploratory_passes"] += 1
        if record.get("near_pass", {}).get("is_near_pass"):
            summary["near_passes"] += 1
        sampling = record.get("sampling") or {}
        if sampling.get("coverage_warning"):
            summary["coverage_warnings"] += 1
        if record.get("identity_fallback_used"):
            summary["identity_fallbacks"] += 1
    return summary


def build_screening_evidence_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    git_revision: str | None,
    campaign_id: str | None,
    col_campaign_id: str | None,
    preset_name: str | None,
    screening_phase: str | None,
    candidates: list[dict[str, Any]],
    screening_records: list[dict[str, Any]],
    screening_pass_kinds: dict[str, str | None],
    paper_blocked_index: dict[str, list[str]],
    promotion_status_index: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the full ``screening_evidence_latest.v1.json`` payload.

    No I/O. Pure transformation of in-memory inputs to a
    JSON-safe dict whose top-level keys are exactly
    ``TOP_LEVEL_KEYS`` (pinned by tests).

    The builder TOLERATES malformed candidate records (missing
    candidate_id, missing screening_record) — see
    ``_build_candidate_record`` for the identity fallback path.
    Operators see ``summary.identity_fallbacks > 0`` as a
    diagnostic signal.
    """
    promotion_status_index = promotion_status_index or {}
    screening_record_by_id: dict[str, dict[str, Any]] = {}
    for record in screening_records:
        cid = record.get("candidate_id")
        if cid is not None:
            screening_record_by_id[str(cid)] = record

    candidate_records: list[dict[str, Any]] = []
    for candidate in candidates:
        raw_id = candidate.get("candidate_id")
        record = (
            screening_record_by_id.get(str(raw_id))
            if raw_id is not None
            else None
        )
        if record is None:
            record = {}
        strategy_id = (
            candidate.get("strategy_id")
            or candidate.get("strategy_name")
            or ""
        )
        pass_kind = screening_pass_kinds.get(str(strategy_id))
        promotion_status = promotion_status_index.get(str(strategy_id))
        paper_blocking_reasons = list(
            paper_blocked_index.get(str(raw_id), [])
            if raw_id is not None
            else []
        )
        candidate_records.append(
            _build_candidate_record(
                candidate=candidate,
                screening_record=record,
                pass_kind=pass_kind,
                promotion_status=promotion_status,
                paper_blocking_reasons=paper_blocking_reasons,
                preset_name=preset_name,
                screening_phase=screening_phase,
            )
        )

    payload: dict[str, Any] = {
        "schema_version": SCREENING_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": str(run_id),
        "campaign_id": str(campaign_id) if campaign_id is not None else None,
        "col_campaign_id": (
            str(col_campaign_id) if col_campaign_id is not None else None
        ),
        "preset_name": preset_name,
        "screening_phase": screening_phase,
        "summary": _summarise(candidate_records),
        "candidates": candidate_records,
    }
    payload["artifact_fingerprint"] = artifact_fingerprint(payload)
    # Defensive deep-copy so callers cannot mutate internals.
    return copy.deepcopy(payload)
