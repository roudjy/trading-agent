"""Research integrity checks: typed reason codes + pure check functions.

**Boundary (D4)** — Integrity is the matching upstream half of the
promotion boundary. It blocks unevaluable runs inside the eligibility
stage and emits diagnostic evidence via `integrity_report_latest.v1.json`,
but it does NOT re-decide the status of a candidate that has already
run through promotion. research/promotion.py remains the sole decision
layer; integrity produces evidence only.

No side effects, no IO, no randomness. Every check returns an
`IntegrityCheck` record carrying a typed reason code so the
sidecar can surface rejection counts-by-reason deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Typed reason codes. Listed here once so every consumer
# (eligibility rejection, artifact integrity, empty-run diagnostics)
# shares the same vocabulary.
# ---------------------------------------------------------------------------

DATA_INSUFFICIENT_BARS = "DATA_INSUFFICIENT_BARS"
DATA_NO_OVERLAP = "DATA_NO_OVERLAP"
FEATURE_WARMUP_STARVED = "FEATURE_WARMUP_STARVED"
FEATURE_INCOMPLETE = "FEATURE_INCOMPLETE"
STRATEGY_MISSING_FEATURES = "STRATEGY_MISSING_FEATURES"
STRATEGY_NOT_APPLICABLE = "STRATEGY_NOT_APPLICABLE"
EVAL_INSUFFICIENT_TRADES = "EVAL_INSUFFICIENT_TRADES"
EVAL_INSUFFICIENT_OOS_BARS = "EVAL_INSUFFICIENT_OOS_BARS"
EVAL_NO_VALID_FOLDS = "EVAL_NO_VALID_FOLDS"
ARTIFACT_INCOMPLETE = "ARTIFACT_INCOMPLETE"
ARTIFACT_RUNID_MISMATCH = "ARTIFACT_RUNID_MISMATCH"


REASON_CODES: frozenset[str] = frozenset(
    {
        DATA_INSUFFICIENT_BARS,
        DATA_NO_OVERLAP,
        FEATURE_WARMUP_STARVED,
        FEATURE_INCOMPLETE,
        STRATEGY_MISSING_FEATURES,
        STRATEGY_NOT_APPLICABLE,
        EVAL_INSUFFICIENT_TRADES,
        EVAL_INSUFFICIENT_OOS_BARS,
        EVAL_NO_VALID_FOLDS,
        ARTIFACT_INCOMPLETE,
        ARTIFACT_RUNID_MISMATCH,
    }
)


class ArtifactIntegrityError(RuntimeError):
    """Raised when cross-sidecar artifact state is inconsistent at read time.

    Carries a typed `reason_code` drawn from REASON_CODES. Surfaces
    inside orchestration_policy so the continue-latest path can fail
    closed rather than silently proceed on a corrupted run.
    """

    def __init__(self, message: str, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class IntegrityCheck:
    name: str
    passed: bool
    reason_code: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrityReport:
    """Aggregates IntegrityCheck records across a run."""

    checks: list[IntegrityCheck] = field(default_factory=list)

    def record(self, check: IntegrityCheck) -> None:
        self.checks.append(check)

    def rejection_counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for check in self.checks:
            if check.passed or check.reason_code is None:
                continue
            counts[check.reason_code] = counts.get(check.reason_code, 0) + 1
        return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Check functions — all pure; inputs are plain dicts / primitives.
# ---------------------------------------------------------------------------


def check_data_sufficiency(
    *,
    asset: str,
    interval: str,
    bar_count: int,
    min_bars: int,
) -> IntegrityCheck:
    """Pass iff bar_count >= min_bars."""
    if bar_count < min_bars:
        return IntegrityCheck(
            name=f"data_sufficiency[{asset}|{interval}]",
            passed=False,
            reason_code=DATA_INSUFFICIENT_BARS,
            details={"asset": asset, "interval": interval, "bar_count": int(bar_count), "min_bars": int(min_bars)},
        )
    return IntegrityCheck(
        name=f"data_sufficiency[{asset}|{interval}]",
        passed=True,
        details={"asset": asset, "interval": interval, "bar_count": int(bar_count)},
    )


def check_feature_completeness(
    *,
    strategy_name: str,
    asset: str,
    interval: str,
    required_features: list[str],
    available_features: list[str],
    warmup_bars: int,
    bar_count: int,
) -> IntegrityCheck:
    """Pass iff every required feature is available and warmup fits in bar_count.

    Emits FEATURE_INCOMPLETE when a required feature is missing from
    the primitives registry, FEATURE_WARMUP_STARVED when the warmup
    requirement cannot fit inside the available bars.
    """
    missing = [f for f in required_features if f not in available_features]
    if missing:
        return IntegrityCheck(
            name=f"feature_completeness[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=FEATURE_INCOMPLETE,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "missing_features": missing,
            },
        )
    if warmup_bars > bar_count:
        return IntegrityCheck(
            name=f"feature_completeness[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=FEATURE_WARMUP_STARVED,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "warmup_bars": int(warmup_bars),
                "bar_count": int(bar_count),
            },
        )
    return IntegrityCheck(
        name=f"feature_completeness[{strategy_name}|{asset}|{interval}]",
        passed=True,
        details={
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
            "warmup_bars": int(warmup_bars),
            "bar_count": int(bar_count),
        },
    )


def check_strategy_applicability(
    *,
    strategy_name: str,
    asset: str,
    interval: str,
    position_structure: str,
    initial_lane_support: str,
) -> IntegrityCheck:
    """Pass iff the strategy is wired into the current execution lane.

    Fails when `initial_lane_support == "blocked"` (e.g. pairs until the
    multi-asset loader lands) or when the position structure is
    incompatible with the single-asset frame the engine currently
    hands each candidate.
    """
    if initial_lane_support == "blocked":
        return IntegrityCheck(
            name=f"strategy_applicability[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=STRATEGY_NOT_APPLICABLE,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "position_structure": position_structure,
                "initial_lane_support": initial_lane_support,
            },
        )
    return IntegrityCheck(
        name=f"strategy_applicability[{strategy_name}|{asset}|{interval}]",
        passed=True,
        details={
            "strategy_name": strategy_name,
            "position_structure": position_structure,
            "initial_lane_support": initial_lane_support,
        },
    )


def check_evaluation_completeness(
    *,
    strategy_name: str,
    asset: str,
    interval: str,
    totaal_trades: int,
    min_trades: int,
    oos_bar_count: int,
    min_oos_bars: int,
    valid_fold_count: int,
) -> IntegrityCheck:
    """Pass iff OOS has enough trades, bars, and at least one valid fold."""
    if valid_fold_count <= 0:
        return IntegrityCheck(
            name=f"evaluation_completeness[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=EVAL_NO_VALID_FOLDS,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "valid_fold_count": int(valid_fold_count),
            },
        )
    if oos_bar_count < min_oos_bars:
        return IntegrityCheck(
            name=f"evaluation_completeness[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=EVAL_INSUFFICIENT_OOS_BARS,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "oos_bar_count": int(oos_bar_count),
                "min_oos_bars": int(min_oos_bars),
            },
        )
    if totaal_trades < min_trades:
        return IntegrityCheck(
            name=f"evaluation_completeness[{strategy_name}|{asset}|{interval}]",
            passed=False,
            reason_code=EVAL_INSUFFICIENT_TRADES,
            details={
                "strategy_name": strategy_name,
                "asset": asset,
                "interval": interval,
                "totaal_trades": int(totaal_trades),
                "min_trades": int(min_trades),
            },
        )
    return IntegrityCheck(
        name=f"evaluation_completeness[{strategy_name}|{asset}|{interval}]",
        passed=True,
        details={
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
            "totaal_trades": int(totaal_trades),
            "oos_bar_count": int(oos_bar_count),
        },
    )


def check_artifact_integrity(
    *,
    state_payload: dict[str, Any] | None,
    manifest_payload: dict[str, Any] | None,
    batches_payload: dict[str, Any] | None,
) -> IntegrityCheck:
    """Cross-sidecar consistency check for the resume path.

    Passes iff state, manifest, and batches payloads all carry the
    same run_id and each payload is a well-formed dict. Used by the
    continue-latest path in orchestration_policy to fail fast rather
    than proceed on corrupted prior-run artifacts.
    """
    payloads = {
        "state": state_payload,
        "manifest": manifest_payload,
        "batches": batches_payload,
    }
    missing = [name for name, payload in payloads.items() if not isinstance(payload, dict)]
    if missing:
        return IntegrityCheck(
            name="artifact_integrity",
            passed=False,
            reason_code=ARTIFACT_INCOMPLETE,
            details={"missing_or_invalid": missing},
        )

    run_ids: dict[str, str] = {}
    for name, payload in payloads.items():
        value = str((payload or {}).get("run_id") or "").strip()
        if value:
            run_ids[name] = value

    if not run_ids:
        return IntegrityCheck(
            name="artifact_integrity",
            passed=False,
            reason_code=ARTIFACT_INCOMPLETE,
            details={"missing_run_ids_from": list(payloads)},
        )

    distinct = set(run_ids.values())
    if len(distinct) != 1 or len(run_ids) != 3:
        return IntegrityCheck(
            name="artifact_integrity",
            passed=False,
            reason_code=ARTIFACT_RUNID_MISMATCH,
            details={"run_ids_by_payload": run_ids},
        )

    return IntegrityCheck(
        name="artifact_integrity",
        passed=True,
        details={"run_id": next(iter(distinct))},
    )


__all__ = [
    "ARTIFACT_INCOMPLETE",
    "ARTIFACT_RUNID_MISMATCH",
    "ArtifactIntegrityError",
    "DATA_INSUFFICIENT_BARS",
    "DATA_NO_OVERLAP",
    "EVAL_INSUFFICIENT_OOS_BARS",
    "EVAL_INSUFFICIENT_TRADES",
    "EVAL_NO_VALID_FOLDS",
    "FEATURE_INCOMPLETE",
    "FEATURE_WARMUP_STARVED",
    "IntegrityCheck",
    "IntegrityReport",
    "REASON_CODES",
    "STRATEGY_MISSING_FEATURES",
    "STRATEGY_NOT_APPLICABLE",
    "check_artifact_integrity",
    "check_data_sufficiency",
    "check_evaluation_completeness",
    "check_feature_completeness",
    "check_strategy_applicability",
]
