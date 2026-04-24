"""Candidate-family-level active policy state (v3.15.2 COL).

Derives per ``(strategy_family, asset_class)`` policy state from the
evidence ledger. Used by §R3.2 step 5 filter 3: suppresses
``survivor_confirmation`` / ``paper_followup`` for families that show
repeated divergence failures.

Rules (R3.5 §7.2):

| Trigger                                                                     | Effect                                  |
|-----------------------------------------------------------------------------|-----------------------------------------|
| 3× ``paper_blocked`` / ``excessive_divergence`` across any preset in family | ``deprioritized`` — suppress survivor_confirmation |
| 5× same                                                                     | ``frozen`` — also suppress paper_followup |

Windows are days-based and read from the ledger's ``at_utc`` field.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_evidence_ledger import family_outcome_counts
from research.campaign_os_artifacts import build_pin_block

FAMILY_POLICY_SCHEMA_VERSION: str = "1.0"
FAMILY_POLICY_ARTIFACT_PATH: Path = Path(
    "research/candidate_family_policy_state_latest.v1.json"
)

FamilyPolicyStateLiteral = Literal["active", "deprioritized", "frozen"]
FAMILY_POLICY_STATES: tuple[str, ...] = ("active", "deprioritized", "frozen")

_THRESH_DEPRIORITIZE = 3
_THRESH_FREEZE = 5
_DEFAULT_WINDOW_DAYS = 14


@dataclass(frozen=True)
class FamilyPolicyState:
    strategy_family: str
    asset_class: str
    policy_state: FamilyPolicyStateLiteral
    reason: str
    divergence_count: int
    window_days: int
    at_utc: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def key(self) -> str:
        return f"{self.strategy_family}|{self.asset_class}"


def derive_family_state(
    events: list[dict[str, Any]],
    *,
    strategy_family: str,
    asset_class: str,
    now_utc: datetime,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> FamilyPolicyState:
    counts = family_outcome_counts(
        events,
        strategy_family=strategy_family,
        asset_class=asset_class,
        window_days=window_days,
        now_utc=now_utc,
    )
    divergence = int(counts.get("excessive_divergence", 0))
    at_utc = now_utc.astimezone(tz=None).isoformat()
    if divergence >= _THRESH_FREEZE:
        return FamilyPolicyState(
            strategy_family=strategy_family,
            asset_class=asset_class,
            policy_state="frozen",
            reason="excessive_divergence_family_freeze",
            divergence_count=divergence,
            window_days=window_days,
            at_utc=at_utc,
        )
    if divergence >= _THRESH_DEPRIORITIZE:
        return FamilyPolicyState(
            strategy_family=strategy_family,
            asset_class=asset_class,
            policy_state="deprioritized",
            reason="excessive_divergence_family_deprioritize",
            divergence_count=divergence,
            window_days=window_days,
            at_utc=at_utc,
        )
    return FamilyPolicyState(
        strategy_family=strategy_family,
        asset_class=asset_class,
        policy_state="active",
        reason="baseline",
        divergence_count=divergence,
        window_days=window_days,
        at_utc=at_utc,
    )


def derive_family_states(
    events: list[dict[str, Any]],
    *,
    families: list[tuple[str, str]],
    now_utc: datetime,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, FamilyPolicyState]:
    out: dict[str, FamilyPolicyState] = {}
    for strategy_family, asset_class in sorted(set(families)):
        state = derive_family_state(
            events,
            strategy_family=strategy_family,
            asset_class=asset_class,
            now_utc=now_utc,
            window_days=window_days,
        )
        out[state.key] = state
    return out


def build_family_policy_payload(
    states: dict[str, FamilyPolicyState],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
) -> dict[str, Any]:
    pins = build_pin_block(
        schema_version=FAMILY_POLICY_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    return {
        **pins,
        "families": {
            key: states[key].to_payload() for key in sorted(states)
        },
    }


def write_family_policy(
    states: dict[str, FamilyPolicyState],
    *,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    path: Path = FAMILY_POLICY_ARTIFACT_PATH,
) -> None:
    payload = build_family_policy_payload(
        states,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
    )
    write_sidecar_atomic(path, payload)


__all__ = [
    "FAMILY_POLICY_ARTIFACT_PATH",
    "FAMILY_POLICY_SCHEMA_VERSION",
    "FAMILY_POLICY_STATES",
    "FamilyPolicyState",
    "FamilyPolicyStateLiteral",
    "build_family_policy_payload",
    "derive_family_state",
    "derive_family_states",
    "write_family_policy",
]
