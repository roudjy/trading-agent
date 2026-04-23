"""v3.14 sleeve registry.

A sleeve is a research construct, not an allocator. It groups
candidates that share a ``(strategy_family, asset_class, interval)``
triple so the portfolio-diagnostics layer can ask "how does this
group compose?" instead of "is this candidate good?".

Every sleeve in v3.14 is derived deterministically from the v3.12
candidate registry v2. The assignment rule has an explicit version
constant so future changes to the rule are always deliberate.

Membership logic:

1. A base sleeve ``<family>_<asset_class>_<interval>`` is created
   for every triple that has at least one candidate with
   ``lifecycle_status == "candidate"`` (i.e. the v3.12 canonical
   "candidate" subset — rejected and exploratory entries are not
   sleeve members).
2. When the v3.13 regime overlay is present and the candidate's
   ``regime_assessment_status == "sufficient"``, the candidate is
   additionally mirrored into a research variant sleeve
   ``<family>_<asset_class>_<interval>__regime_filtered``. Base
   membership is preserved; the variant is additive.
3. Sleeves with zero members are never emitted.

Outputs are deterministic: sleeves sorted by ``sleeve_id``, members
sorted by ``candidate_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SLEEVE_REGISTRY_SCHEMA_VERSION = "1.0"
ASSIGNMENT_RULE_VERSION = "v0.1"

# Lifecycle statuses that qualify for sleeve membership.
ELIGIBLE_LIFECYCLE_STATUSES: frozenset[str] = frozenset({"candidate"})

REGIME_FILTERED_SUFFIX = "__regime_filtered"
REGIME_ASSESSMENT_SUFFICIENT = "sufficient"

UNKNOWN_FAMILY = "unknown_family"
UNKNOWN_ASSET_CLASS = "unknown_asset"


@dataclass(frozen=True)
class SleeveMembership:
    sleeve_id: str
    candidate_id: str
    inclusion_reason: str
    regime_assessment_status: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "sleeve_id": self.sleeve_id,
            "candidate_id": self.candidate_id,
            "inclusion_reason": self.inclusion_reason,
            "regime_assessment_status": self.regime_assessment_status,
        }


@dataclass(frozen=True)
class Sleeve:
    sleeve_id: str
    strategy_family: str
    asset_class: str
    interval: str
    is_regime_filtered: bool
    member_count: int
    rationale: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "sleeve_id": self.sleeve_id,
            "strategy_family": self.strategy_family,
            "asset_class": self.asset_class,
            "interval": self.interval,
            "is_regime_filtered": bool(self.is_regime_filtered),
            "member_count": int(self.member_count),
            "rationale": self.rationale,
            "assignment_rule_version": ASSIGNMENT_RULE_VERSION,
        }


@dataclass(frozen=True)
class SleeveRegistry:
    sleeves: list[Sleeve]
    memberships: list[SleeveMembership]


def _split_experiment_family(experiment_family: str | None) -> tuple[str, str]:
    """``{strategy_family}|{asset_type}`` → split components, with
    fallback values so sleeve ids never contain empty segments."""
    if not experiment_family or "|" not in experiment_family:
        return UNKNOWN_FAMILY, UNKNOWN_ASSET_CLASS
    family, _, asset_class = experiment_family.partition("|")
    family = family.strip() or UNKNOWN_FAMILY
    asset_class = asset_class.strip() or UNKNOWN_ASSET_CLASS
    return family, asset_class


def _base_sleeve_id(family: str, asset_class: str, interval: str) -> str:
    return f"{family}_{asset_class}_{interval}"


def _regime_overlay_index(regime_overlay: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index overlay entries by ``candidate_id`` for O(1) look-up."""
    if regime_overlay is None:
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for entry in regime_overlay.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("candidate_id")
        if not candidate_id:
            continue
        indexed[str(candidate_id)] = entry
    return indexed


def assign_sleeves(
    *,
    registry_v2: dict[str, Any],
    regime_overlay: dict[str, Any] | None = None,
) -> SleeveRegistry:
    """Deterministically derive sleeves + memberships from the v2
    registry and the (optional) v3.13 regime overlay."""
    entries = registry_v2.get("entries") or []
    overlay = _regime_overlay_index(regime_overlay)

    memberships: list[SleeveMembership] = []
    members_by_sleeve: dict[str, list[str]] = {}
    sleeve_keys: dict[str, tuple[str, str, str, bool]] = {}

    def _record(sleeve_id: str, key: tuple[str, str, str, bool], membership: SleeveMembership) -> None:
        memberships.append(membership)
        members_by_sleeve.setdefault(sleeve_id, []).append(membership.candidate_id)
        sleeve_keys.setdefault(sleeve_id, key)

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lifecycle = entry.get("lifecycle_status")
        if lifecycle not in ELIGIBLE_LIFECYCLE_STATUSES:
            continue
        candidate_id = entry.get("candidate_id")
        interval = entry.get("interval")
        experiment_family = entry.get("experiment_family")
        if not candidate_id or not interval:
            continue

        family, asset_class = _split_experiment_family(str(experiment_family) if experiment_family else None)
        interval_str = str(interval)
        base_id = _base_sleeve_id(family, asset_class, interval_str)
        base_key = (family, asset_class, interval_str, False)

        overlay_entry = overlay.get(str(candidate_id))
        regime_status = overlay_entry.get("regime_assessment_status") if overlay_entry else None

        _record(
            base_id,
            base_key,
            SleeveMembership(
                sleeve_id=base_id,
                candidate_id=str(candidate_id),
                inclusion_reason="lifecycle_candidate",
                regime_assessment_status=regime_status,
            ),
        )

        if overlay_entry and regime_status == REGIME_ASSESSMENT_SUFFICIENT:
            variant_id = base_id + REGIME_FILTERED_SUFFIX
            variant_key = (family, asset_class, interval_str, True)
            _record(
                variant_id,
                variant_key,
                SleeveMembership(
                    sleeve_id=variant_id,
                    candidate_id=str(candidate_id),
                    inclusion_reason="regime_sufficient_research_variant",
                    regime_assessment_status=regime_status,
                ),
            )

    sleeves: list[Sleeve] = []
    for sleeve_id in sorted(sleeve_keys):
        family, asset_class, interval_str, is_filtered = sleeve_keys[sleeve_id]
        members = members_by_sleeve.get(sleeve_id) or []
        rationale = (
            "research variant restricted to candidates with sufficient regime evidence"
            if is_filtered
            else f"base sleeve grouping candidates in {family}/{asset_class}/{interval_str}"
        )
        sleeves.append(
            Sleeve(
                sleeve_id=sleeve_id,
                strategy_family=family,
                asset_class=asset_class,
                interval=interval_str,
                is_regime_filtered=is_filtered,
                member_count=len(members),
                rationale=rationale,
            )
        )

    memberships.sort(key=lambda m: (m.sleeve_id, m.candidate_id))
    return SleeveRegistry(sleeves=sleeves, memberships=memberships)


def build_sleeve_registry_payload(
    *,
    registry: SleeveRegistry,
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
    source_registry_posix: str = "research/candidate_registry_latest.v2.json",
    source_regime_overlay_posix: str = "research/candidate_registry_regime_overlay_latest.v1.json",
) -> dict[str, Any]:
    """Wrap a :class:`SleeveRegistry` in the canonical sidecar shape."""
    return {
        "schema_version": SLEEVE_REGISTRY_SCHEMA_VERSION,
        "assignment_rule_version": ASSIGNMENT_RULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "source_registry": source_registry_posix,
        "source_regime_overlay": source_regime_overlay_posix,
        "sleeves": [s.to_payload() for s in registry.sleeves],
        "memberships": [m.to_payload() for m in registry.memberships],
    }


__all__ = [
    "ASSIGNMENT_RULE_VERSION",
    "REGIME_FILTERED_SUFFIX",
    "SLEEVE_REGISTRY_SCHEMA_VERSION",
    "Sleeve",
    "SleeveMembership",
    "SleeveRegistry",
    "assign_sleeves",
    "build_sleeve_registry_payload",
]
