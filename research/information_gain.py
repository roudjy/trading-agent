"""v3.15.11 — Information Gain Engine (advisory observability).

Deterministic, explicit per-campaign information gain score. No ML,
no black-box weighting — every contribution is a named reason with a
constant weight. The score answers "did this campaign teach us
something?" rather than "did it make money?".

Bucketing (REV: research-learning, not P&L):

    score == 0.0            → "none"
    0.0 <  score <  0.3     → "low"
    0.3 <= score <  0.7     → "medium"
    score >= 0.7            → "high"

A campaign is "meaningful" when its bucket is medium or high — i.e.
it surfaced new information, a candidate, or a near-candidate. A
technical failure is never meaningful regardless of other signals
because the run did not actually exercise the hypothesis.

Pure scoring + thin IO wrapper. Read-only consumer of upstream
artifacts; mutates nothing. Coverage bonus is additive and capped at
``IG_COVERAGE_BONUS_MAX`` so coverage alone never reaches the
"medium" bucket — coverage is an enabler of learning, not learning
itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import write_sidecar_atomic

INFORMATION_GAIN_SCHEMA_VERSION: Final[str] = "1.0"
INFORMATION_GAIN_PATH: Final[Path] = Path(
    "research/campaigns/evidence/information_gain_latest.v1.json"
)

# Per-signal weights. Constants live at module top so the policy is
# inspectable without code-walking.
IG_TECHNICAL_FAILURE: Final[float] = 0.0
IG_DUPLICATE_REJECTION: Final[float] = 0.1
IG_NEW_FAILURE_MODE: Final[float] = 0.5
IG_NEAR_CANDIDATE: Final[float] = 0.8
IG_EXPLORATORY_PASS: Final[float] = 0.8
IG_PROMOTION_CANDIDATE: Final[float] = 0.9
IG_PAPER_READY: Final[float] = 1.0

# Coverage adds a small additive bonus on top of the dominant signal.
# Capped low so coverage alone cannot push a duplicate-rejection
# campaign into "medium".
IG_COVERAGE_BONUS_MAX: Final[float] = 0.2
IG_COVERAGE_BONUS_FLOOR: Final[float] = 0.80

# Bucket thresholds.
IG_BUCKET_LOW_FLOOR: Final[float] = 0.0
IG_BUCKET_MEDIUM_FLOOR: Final[float] = 0.3
IG_BUCKET_HIGH_FLOOR: Final[float] = 0.7

BUCKET_NONE: Final[str] = "none"
BUCKET_LOW: Final[str] = "low"
BUCKET_MEDIUM: Final[str] = "medium"
BUCKET_HIGH: Final[str] = "high"


@dataclass(frozen=True)
class InformationGainInputs:
    """Boolean signals + sampling coverage feeding the score.

    Callers compose these from the campaign outcome, the v3.15.9
    screening evidence, the evidence ledger from Phase 1, and the
    v3.15.8 sampling block. Booleans default False so missing data
    is treated as "no signal" rather than crashing.
    """

    new_failure_mode: bool = False
    repeated_failure_mode: bool = False
    exploratory_pass: bool = False
    near_candidate: bool = False
    promotion_candidate: bool = False
    paper_ready: bool = False
    technical_failure: bool = False
    parameter_coverage_pct: float | None = None
    sampled_count: int | None = None
    grid_size: int | None = None


@dataclass(frozen=True)
class InformationGainReason:
    code: str
    weight: float
    explanation: str


@dataclass(frozen=True)
class InformationGainResult:
    score: float
    bucket: str
    is_meaningful_campaign: bool
    reasons: list[InformationGainReason] = field(default_factory=list)


def _bucket_for(score: float) -> str:
    if score <= 0.0:
        return BUCKET_NONE
    if score < IG_BUCKET_MEDIUM_FLOOR:
        return BUCKET_LOW
    if score < IG_BUCKET_HIGH_FLOOR:
        return BUCKET_MEDIUM
    return BUCKET_HIGH


def _coverage_bonus(coverage_pct: float | None) -> float:
    if coverage_pct is None:
        return 0.0
    if coverage_pct < IG_COVERAGE_BONUS_FLOOR:
        return 0.0
    span = 1.0 - IG_COVERAGE_BONUS_FLOOR
    if span <= 0.0:
        return 0.0
    fraction = (coverage_pct - IG_COVERAGE_BONUS_FLOOR) / span
    fraction = max(0.0, min(1.0, fraction))
    return IG_COVERAGE_BONUS_MAX * fraction


def score_information_gain(inputs: InformationGainInputs) -> InformationGainResult:
    """Pure scoring function. Deterministic reason ordering."""
    if inputs.technical_failure:
        return InformationGainResult(
            score=IG_TECHNICAL_FAILURE,
            bucket=BUCKET_NONE,
            is_meaningful_campaign=False,
            reasons=[
                InformationGainReason(
                    code="technical_failure",
                    weight=IG_TECHNICAL_FAILURE,
                    explanation=(
                        "Campaign did not exercise the hypothesis; no "
                        "research learning attributable."
                    ),
                )
            ],
        )

    candidates: list[tuple[str, float, str]] = []
    if inputs.paper_ready:
        candidates.append((
            "paper_ready",
            IG_PAPER_READY,
            "Candidate reached paper-ready state.",
        ))
    if inputs.promotion_candidate:
        candidates.append((
            "promotion_candidate",
            IG_PROMOTION_CANDIDATE,
            "Promotion-grade candidate produced.",
        ))
    if inputs.exploratory_pass:
        candidates.append((
            "exploratory_pass",
            IG_EXPLORATORY_PASS,
            "Exploratory criteria satisfied (needs confirmation).",
        ))
    if inputs.near_candidate:
        candidates.append((
            "near_candidate",
            IG_NEAR_CANDIDATE,
            "Near-pass evidence under v3.15.9 band.",
        ))
    if inputs.new_failure_mode:
        candidates.append((
            "new_failure_mode",
            IG_NEW_FAILURE_MODE,
            "Failure reason not seen in prior evidence ledger.",
        ))
    if inputs.repeated_failure_mode and not (
        inputs.exploratory_pass
        or inputs.promotion_candidate
        or inputs.near_candidate
        or inputs.paper_ready
        or inputs.new_failure_mode
    ):
        candidates.append((
            "repeated_failure_mode",
            IG_DUPLICATE_REJECTION,
            "Duplicate rejection with no new coverage.",
        ))

    candidates.sort(key=lambda c: (-c[1], c[0]))
    reasons = [InformationGainReason(*c) for c in candidates]
    base = max((c[1] for c in candidates), default=0.0)

    bonus = _coverage_bonus(inputs.parameter_coverage_pct)
    if bonus > 0.0:
        reasons.append(
            InformationGainReason(
                code="improved_parameter_coverage",
                weight=bonus,
                explanation=(
                    "Coverage above 80% adds small additive bonus; "
                    "capped to remain non-dominant."
                ),
            )
        )

    score = min(1.0, base + bonus)
    bucket = _bucket_for(score)
    is_meaningful = bucket in (BUCKET_MEDIUM, BUCKET_HIGH)
    return InformationGainResult(
        score=round(score, 4),
        bucket=bucket,
        is_meaningful_campaign=is_meaningful,
        reasons=reasons,
    )


def build_information_gain_payload(
    *,
    run_id: str | None,
    col_campaign_id: str | None,
    preset_name: str | None,
    hypothesis_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    inputs: InformationGainInputs,
) -> dict[str, Any]:
    """Assemble the artifact payload (pure, no I/O)."""
    result = score_information_gain(inputs)
    return {
        "schema_version": INFORMATION_GAIN_SCHEMA_VERSION,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "git_revision": git_revision,
        "run_id": run_id,
        "col_campaign_id": col_campaign_id,
        "preset_name": preset_name,
        "hypothesis_id": hypothesis_id,
        "information_gain": {
            "score": result.score,
            "bucket": result.bucket,
            "is_meaningful_campaign": result.is_meaningful_campaign,
            "reasons": [
                {
                    "code": r.code,
                    "weight": r.weight,
                    "explanation": r.explanation,
                }
                for r in result.reasons
            ],
        },
        "inputs": {
            "new_failure_mode": inputs.new_failure_mode,
            "repeated_failure_mode": inputs.repeated_failure_mode,
            "exploratory_pass": inputs.exploratory_pass,
            "near_candidate": inputs.near_candidate,
            "promotion_candidate": inputs.promotion_candidate,
            "paper_ready": inputs.paper_ready,
            "technical_failure": inputs.technical_failure,
            "parameter_coverage_pct": inputs.parameter_coverage_pct,
            "sampled_count": inputs.sampled_count,
            "grid_size": inputs.grid_size,
        },
    }


def write_information_gain_artifact(
    *,
    run_id: str | None,
    col_campaign_id: str | None,
    preset_name: str | None,
    hypothesis_id: str | None,
    as_of_utc: datetime,
    git_revision: str | None,
    inputs: InformationGainInputs,
    output_path: Path = INFORMATION_GAIN_PATH,
) -> dict[str, Any]:
    """Build and write the artifact via canonical sidecar IO."""
    payload = build_information_gain_payload(
        run_id=run_id,
        col_campaign_id=col_campaign_id,
        preset_name=preset_name,
        hypothesis_id=hypothesis_id,
        as_of_utc=as_of_utc,
        git_revision=git_revision,
        inputs=inputs,
    )
    write_sidecar_atomic(output_path, payload)
    return payload


__all__ = [
    "BUCKET_HIGH",
    "BUCKET_LOW",
    "BUCKET_MEDIUM",
    "BUCKET_NONE",
    "IG_COVERAGE_BONUS_FLOOR",
    "IG_COVERAGE_BONUS_MAX",
    "IG_DUPLICATE_REJECTION",
    "IG_EXPLORATORY_PASS",
    "IG_NEAR_CANDIDATE",
    "IG_NEW_FAILURE_MODE",
    "IG_PAPER_READY",
    "IG_PROMOTION_CANDIDATE",
    "IG_TECHNICAL_FAILURE",
    "INFORMATION_GAIN_PATH",
    "INFORMATION_GAIN_SCHEMA_VERSION",
    "InformationGainInputs",
    "InformationGainReason",
    "InformationGainResult",
    "build_information_gain_payload",
    "score_information_gain",
    "write_information_gain_artifact",
]
