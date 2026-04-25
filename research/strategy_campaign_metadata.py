"""Per-hypothesis campaign metadata sidecar (v3.15.3).

Mirrors ``strategy_hypothesis_catalog`` one-to-one but carries the
fields the v3.15.2 Campaign Operating Layer needs to:

- decide *which* campaign types a hypothesis may participate in
  (``eligible_campaign_types``);
- compute the *cooldown* between consecutive spawns
  (``cooldown_policy``);
- decide whether a *follow-up* campaign should chain (survivor
  confirmation, paper followup, ...)  (``followup_policy``);
- assign the spawned campaign's *priority tier* in the queue
  (``priority_profile``);
- canonicalize strategy-specific failure reasons to the closed
  taxonomy in ``research.strategy_failure_taxonomy``
  (``failure_mode_mapping``).

This module is pure configuration + payload assembly. The campaign
launcher reads the resulting sidecar at tick boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

from research._sidecar_io import (
    require_schema_version,
    write_sidecar_atomic,
)
from research.campaign_os_artifacts import build_pin_block
from research.strategy_failure_taxonomy import (
    canonicalize,
    is_canonical,
)
from research.strategy_hypothesis_catalog import (
    STRATEGY_HYPOTHESIS_CATALOG,
    StrategyHypothesis,
)


CAMPAIGN_METADATA_SCHEMA_VERSION: Final[str] = "1.0"
STRATEGY_CAMPAIGN_METADATA_VERSION: Final[str] = "v0.1"

CAMPAIGN_METADATA_ARTIFACT_PATH: Final[Path] = Path(
    "research/strategy_campaign_metadata_latest.v1.json"
)

# Default cooldown for the active_discovery family (24h). Mirrors the
# ``_DEFAULT_DAILY_PRIMARY_COOLDOWN_S`` in research.campaign_templates
# but expressed locally so this module does not import from the
# templates layer (which would create a cycle if the templates ever
# read metadata back).
_DEFAULT_BASE_COOLDOWN_SECONDS: Final[int] = 24 * 60 * 60


@dataclass(frozen=True)
class HypothesisCampaignMetadata:
    """Per-hypothesis campaign-policy descriptor."""

    hypothesis_id: str
    eligible_campaign_types: tuple[str, ...]
    cooldown_policy: dict[str, int]
    followup_policy: dict[str, bool]
    priority_profile: dict[str, int]
    failure_mode_mapping: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "eligible_campaign_types": list(self.eligible_campaign_types),
            "cooldown_policy": dict(self.cooldown_policy),
            "followup_policy": dict(self.followup_policy),
            "priority_profile": dict(self.priority_profile),
            "failure_mode_mapping": dict(self.failure_mode_mapping),
        }


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

STRATEGY_CAMPAIGN_METADATA: Final[tuple[HypothesisCampaignMetadata, ...]] = (
    HypothesisCampaignMetadata(
        hypothesis_id="trend_pullback_v1",
        eligible_campaign_types=(
            "daily_primary",
            "survivor_confirmation",
            "weekly_retest",
        ),
        cooldown_policy={"base_cooldown_seconds": _DEFAULT_BASE_COOLDOWN_SECONDS},
        followup_policy={
            "survivor_confirmation": True,
            "paper_followup": True,
        },
        priority_profile={"initial_priority_tier": 2},
        failure_mode_mapping={
            "trend_pullback_cost_fragile": "cost_fragile",
            "trend_pullback_parameter_fragile": "parameter_fragile",
            "trend_pullback_no_baseline_edge": "no_baseline_edge",
        },
    ),
    HypothesisCampaignMetadata(
        hypothesis_id="regime_diagnostics_v1",
        eligible_campaign_types=(),
        cooldown_policy={},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={},
    ),
    HypothesisCampaignMetadata(
        hypothesis_id="atr_adaptive_trend_v0",
        eligible_campaign_types=(),
        cooldown_policy={},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={},
    ),
    HypothesisCampaignMetadata(
        hypothesis_id="volatility_compression_breakout_v0",
        eligible_campaign_types=(),
        cooldown_policy={},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={},
    ),
    HypothesisCampaignMetadata(
        hypothesis_id="dynamic_pairs_v0",
        eligible_campaign_types=(),
        cooldown_policy={},
        followup_policy={},
        priority_profile={},
        failure_mode_mapping={},
    ),
)


# ---------------------------------------------------------------------------
# Validation (runs at import)
# ---------------------------------------------------------------------------


class CampaignMetadataError(RuntimeError):
    """Raised when campaign metadata violates an invariant."""


def _validate_metadata(
    metadata: tuple[HypothesisCampaignMetadata, ...],
    catalog: tuple[StrategyHypothesis, ...],
) -> None:
    """Enforce parity with the hypothesis catalog and taxonomy alignment.

    1. Every catalog hypothesis_id has exactly one metadata entry.
    2. No metadata entry references an unknown hypothesis_id.
    3. Every value in any failure_mode_mapping resolves to a canonical
       failure code via ``strategy_failure_taxonomy.canonicalize``.
    """
    catalog_ids = {h.hypothesis_id for h in catalog}
    meta_ids = [m.hypothesis_id for m in metadata]
    if sorted(meta_ids) != sorted(catalog_ids):
        missing = sorted(catalog_ids - set(meta_ids))
        extra = sorted(set(meta_ids) - catalog_ids)
        raise CampaignMetadataError(
            f"campaign metadata / hypothesis catalog mismatch: "
            f"missing={missing}, extra={extra}"
        )
    if len(meta_ids) != len(set(meta_ids)):
        raise CampaignMetadataError(
            f"duplicate hypothesis_id in campaign metadata: {meta_ids}"
        )
    for entry in metadata:
        for raw, canonical in entry.failure_mode_mapping.items():
            # The canonical side must already be canonical; the raw
            # side must canonicalise to the declared canonical code.
            if not is_canonical(canonical):
                raise CampaignMetadataError(
                    f"hypothesis {entry.hypothesis_id!r} maps "
                    f"{raw!r} -> {canonical!r} which is not canonical"
                )
            resolved = canonicalize(raw)
            if resolved != canonical:
                raise CampaignMetadataError(
                    f"hypothesis {entry.hypothesis_id!r} maps "
                    f"{raw!r} -> {canonical!r} but the taxonomy "
                    f"resolves {raw!r} to {resolved!r}"
                )


_validate_metadata(STRATEGY_CAMPAIGN_METADATA, STRATEGY_HYPOTHESIS_CATALOG)


# ---------------------------------------------------------------------------
# Lookups + writer
# ---------------------------------------------------------------------------


def get_metadata(
    hypothesis_id: str,
    *,
    metadata: tuple[HypothesisCampaignMetadata, ...] = STRATEGY_CAMPAIGN_METADATA,
) -> HypothesisCampaignMetadata:
    for entry in metadata:
        if entry.hypothesis_id == hypothesis_id:
            return entry
    raise KeyError(
        f"no campaign metadata for hypothesis_id {hypothesis_id!r}"
    )


def build_campaign_metadata_payload(
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    run_id: str | None = None,
    metadata: tuple[HypothesisCampaignMetadata, ...] = STRATEGY_CAMPAIGN_METADATA,
) -> dict[str, Any]:
    """Return the canonical campaign-metadata payload.

    The ``hypotheses`` field is a dict keyed by hypothesis_id (sorted
    for determinism) so consumers can do O(1) lookup; the catalog is
    the source of ordering when iteration is needed.
    """
    pin = build_pin_block(
        schema_version=CAMPAIGN_METADATA_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=run_id,
    )
    payload = dict(pin)
    payload["strategy_campaign_metadata_version"] = (
        STRATEGY_CAMPAIGN_METADATA_VERSION
    )
    payload["hypotheses"] = {
        entry.hypothesis_id: entry.to_payload()
        for entry in sorted(metadata, key=lambda m: m.hypothesis_id)
    }
    return payload


def write_campaign_metadata_sidecar(
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    run_id: str | None = None,
    path: Path = CAMPAIGN_METADATA_ARTIFACT_PATH,
) -> Path:
    payload = build_campaign_metadata_payload(
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=run_id,
    )
    require_schema_version(payload, CAMPAIGN_METADATA_SCHEMA_VERSION)
    write_sidecar_atomic(path, payload)
    return path


__all__ = [
    "CAMPAIGN_METADATA_ARTIFACT_PATH",
    "CAMPAIGN_METADATA_SCHEMA_VERSION",
    "CampaignMetadataError",
    "HypothesisCampaignMetadata",
    "STRATEGY_CAMPAIGN_METADATA",
    "STRATEGY_CAMPAIGN_METADATA_VERSION",
    "build_campaign_metadata_payload",
    "get_metadata",
    "write_campaign_metadata_sidecar",
]
