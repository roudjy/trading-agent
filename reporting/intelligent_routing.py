"""v3.15.16 — Intelligent Routing Layer (advisory).

Read-only, pure, deterministic projection of existing read-only research
artifacts (campaign queue / registry / information gain / dead zones /
viability / stop conditions / evidence ledger / screening evidence) into
a single advisory routing report.

Release framing
---------------

v3.15.16 ships an **advisory** Intelligent Routing Layer artifact:

* No campaign queue ordering change.
* No campaign launcher integration.
* No funnel policy integration.
* No research artifact mutation.
* Queue integration deferred to a later focused release.

Every report carries the top-level fields ``routing_effect ==
"advisory_only"`` and ``queue_ordering_effect == "none"`` so a downstream
reader cannot accidentally interpret the artifact as authoritative.

Behavior coordinates
--------------------

``behavior_coordinates`` are **provisional deterministic routing
coordinates** derived from existing metadata
(``strategy_hypothesis_catalog`` + ``presets`` + ``registry`` via
``research.authority_views``). They are **not** a new behavior taxonomy
and are **not** final behavior tags. v3.15.16 introduces no taxonomy.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib-only. No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``automation.live_gate``, ``agent.risk``,
  ``agent.execution``, ``broker``, ``live``, ``paper``, ``shadow``,
  ``trading``, ``dashboard``.
* Importing this module performs no I/O: no file is opened in write
  mode, no research artifact is read, no research artifact is mutated.
* PR-A defines pure data model + helper functions only. Reading
  artifacts and emitting the report is added in PR-B; advisory
  suppression/priority scoring is added in PR-C; ``--diagnose-id`` and
  the status reporter ship in PR-D.

This module never writes anywhere outside ``logs/intelligent_routing/``.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Final

# ---------------------------------------------------------------------------
# Schema / version pins
# ---------------------------------------------------------------------------

MODULE_VERSION: Final[str] = "v3.15.16"
SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "intelligent_routing"

#: Top-level constant strings the artifact must always carry. Pinned so
#: a downstream reader (or a test) can assert the release framing
#: without parsing free text.
ROUTING_EFFECT_ADVISORY_ONLY: Final[str] = "advisory_only"
QUEUE_ORDERING_EFFECT_NONE: Final[str] = "none"

#: Default fallback string when behaviour-coordinate metadata is absent.
#: Mirrors ``research.dead_zone_detection.UNKNOWN_TIMEFRAME`` and the
#: ``ZONE_UNKNOWN`` sentinel so cross-artifact joins compare cleanly.
UNKNOWN_COORDINATE: Final[str] = "unknown"

# ---------------------------------------------------------------------------
# Information-gain buckets (mirror research.information_gain thresholds)
# ---------------------------------------------------------------------------

#: Buckets are strings, not numbers, by convention with the upstream
#: artifact. Names are pinned constants so tests assert verbatim.
BUCKET_NONE: Final[str] = "none"
BUCKET_LOW: Final[str] = "low"
BUCKET_MEDIUM: Final[str] = "medium"
BUCKET_HIGH: Final[str] = "high"

#: Thresholds copied from research/information_gain.py to keep this
#: module pure and read-free at import time. If the upstream module
#: bumps thresholds, the test ``test_intelligent_routing_pure`` will
#: catch the divergence (the test imports both modules and asserts
#: bucket equivalence on a swept score).
IG_BUCKET_MEDIUM_FLOOR: Final[float] = 0.3
IG_BUCKET_HIGH_FLOOR: Final[float] = 0.7

INFO_GAIN_BUCKETS: Final[tuple[str, ...]] = (
    BUCKET_NONE,
    BUCKET_LOW,
    BUCKET_MEDIUM,
    BUCKET_HIGH,
)

# ---------------------------------------------------------------------------
# Dead-zone status taxonomy (mirror research.dead_zone_detection)
# ---------------------------------------------------------------------------

DEAD_ZONE_INSUFFICIENT_DATA: Final[str] = "insufficient_data"
DEAD_ZONE_UNKNOWN: Final[str] = "unknown"
DEAD_ZONE_ALIVE: Final[str] = "alive"
DEAD_ZONE_WEAK: Final[str] = "weak"
DEAD_ZONE_DEAD: Final[str] = "dead"

DEAD_ZONE_STATUSES: Final[tuple[str, ...]] = (
    DEAD_ZONE_INSUFFICIENT_DATA,
    DEAD_ZONE_UNKNOWN,
    DEAD_ZONE_ALIVE,
    DEAD_ZONE_WEAK,
    DEAD_ZONE_DEAD,
)

#: Statuses that *never* trigger advisory suppression. Anything not in
#: this set (i.e. only ``DEAD_ZONE_DEAD``) may set
#: ``advisory_suppression_reason = "dead_zone"`` in PR-C.
NEVER_SUPPRESS_DEAD_ZONE_STATUSES: Final[frozenset[str]] = frozenset({
    DEAD_ZONE_INSUFFICIENT_DATA,
    DEAD_ZONE_UNKNOWN,
    DEAD_ZONE_ALIVE,
    DEAD_ZONE_WEAK,
})

# ---------------------------------------------------------------------------
# Orthogonality buckets
# ---------------------------------------------------------------------------

ORTHOGONALITY_NOVEL: Final[str] = "novel"
ORTHOGONALITY_ADJACENT: Final[str] = "adjacent"
ORTHOGONALITY_SATURATED: Final[str] = "saturated"

ORTHOGONALITY_BUCKETS: Final[tuple[str, ...]] = (
    ORTHOGONALITY_NOVEL,
    ORTHOGONALITY_ADJACENT,
    ORTHOGONALITY_SATURATED,
)

#: A 3-tuple coordinate is ``novel`` when the active queue + recent
#: completed campaigns have *no* prior campaign sharing the coordinate.
ORTHOGONALITY_NOVEL_MAX_PRIOR: Final[int] = 0
#: ``adjacent`` covers 1-2 prior; ``saturated`` is >= 3.
ORTHOGONALITY_ADJACENT_MAX_PRIOR: Final[int] = 2

# ---------------------------------------------------------------------------
# Advisory suppression vocabulary
# ---------------------------------------------------------------------------

SUPPRESSION_DEAD_ZONE: Final[str] = "dead_zone"
SUPPRESSION_NEAR_DUPLICATE: Final[str] = "near_duplicate"

ADVISORY_SUPPRESSION_REASONS: Final[tuple[str, ...]] = (
    SUPPRESSION_DEAD_ZONE,
    SUPPRESSION_NEAR_DUPLICATE,
)

#: Number of fingerprint hex characters used in the near-duplicate
#: grouping. Read from existing fingerprints; never computed from
#: scratch. 8 hex chars = 32 bits, enough collision resistance for an
#: advisory grouping at queue scale.
NEAR_DUPLICATE_FINGERPRINT_PREFIX_LEN: Final[int] = 8

#: Output prefix length for the group hash. 12 hex chars = 48 bits.
NEAR_DUPLICATE_GROUP_HASH_LEN: Final[int] = 12


# ---------------------------------------------------------------------------
# Pure dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class BehaviorCoordinates:
    """Provisional deterministic routing coordinates.

    Not a behavior taxonomy. Not final tags. Derived from existing
    metadata only. The ``provisional`` boolean is part of the artifact
    so a reader is reminded of the framing.
    """

    family: str
    asset_class: str
    timeframe: str
    provisional: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "family": self.family,
            "asset_class": self.asset_class,
            "timeframe": self.timeframe,
            "provisional": self.provisional,
        }

    def as_tuple(self) -> tuple[str, str, str]:
        """Hashable 3-tuple form used for orthogonality and grouping."""
        return (self.family, self.asset_class, self.timeframe)


@dataclasses.dataclass(frozen=True)
class RoutingDecision:
    """A single advisory routing decision for one campaign.

    Field naming uses ``advisory_`` prefixes for anything that could be
    mistaken for operational suppression or operational priority.
    """

    campaign_id: str
    preset_name: str
    behavior_coordinates: BehaviorCoordinates
    info_gain_score: float
    info_gain_bucket: str
    dead_zone_status: str
    near_duplicate_group: str | None
    orthogonality_bucket: str
    advisory_suppression_reason: str | None
    advisory_priority_score: int
    advisory_rank: int
    tie_break_key: str

    def to_payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "preset_name": self.preset_name,
            "behavior_coordinates": self.behavior_coordinates.to_payload(),
            "info_gain_score": float(self.info_gain_score),
            "info_gain_bucket": self.info_gain_bucket,
            "dead_zone_status": self.dead_zone_status,
            "near_duplicate_group": self.near_duplicate_group,
            "orthogonality_bucket": self.orthogonality_bucket,
            "advisory_suppression_reason": self.advisory_suppression_reason,
            "advisory_priority_score": int(self.advisory_priority_score),
            "advisory_rank": int(self.advisory_rank),
            "tie_break_key": self.tie_break_key,
        }


@dataclasses.dataclass(frozen=True)
class RoutingReportSummary:
    """Aggregate counters for a routing report.

    Field names use ``advisory_`` prefixes per Correction 4.
    """

    total: int
    advisory_suppressed_dead_zone: int
    advisory_suppressed_near_duplicate: int
    high_info_gain: int
    novel_behavior_coordinates: int
    metadata_gaps: int

    def to_payload(self) -> dict[str, int]:
        return {
            "total": int(self.total),
            "advisory_suppressed_dead_zone": int(self.advisory_suppressed_dead_zone),
            "advisory_suppressed_near_duplicate": int(
                self.advisory_suppressed_near_duplicate
            ),
            "high_info_gain": int(self.high_info_gain),
            "novel_behavior_coordinates": int(self.novel_behavior_coordinates),
            "metadata_gaps": int(self.metadata_gaps),
        }


@dataclasses.dataclass(frozen=True)
class RoutingReport:
    """Full advisory routing report.

    Always carries ``routing_effect = "advisory_only"`` and
    ``queue_ordering_effect = "none"``.
    """

    schema_version: str
    report_kind: str
    version: str
    routing_effect: str
    queue_ordering_effect: str
    generated_at_utc: str
    provenance: dict[str, dict[str, str]]
    decisions: tuple[RoutingDecision, ...]
    summary: RoutingReportSummary

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "report_kind": self.report_kind,
            "version": self.version,
            "routing_effect": self.routing_effect,
            "queue_ordering_effect": self.queue_ordering_effect,
            "generated_at_utc": self.generated_at_utc,
            "provenance": dict(sorted(self.provenance.items())),
            "decisions": [d.to_payload() for d in self.decisions],
            "summary": self.summary.to_payload(),
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_str(value: object) -> str:
    """Coerce a metadata field to a non-empty stripped str, or
    ``UNKNOWN_COORDINATE`` if missing/empty.

    Pure. Never raises on unexpected types.
    """
    if value is None:
        return UNKNOWN_COORDINATE
    text = str(value).strip()
    if not text:
        return UNKNOWN_COORDINATE
    return text


def derive_behavior_coordinates(
    *,
    strategy_family: object = None,
    asset_class: object = None,
    timeframe: object = None,
) -> BehaviorCoordinates:
    """Pure derivation of the provisional 3-tuple from existing metadata.

    No new taxonomy is introduced. Missing/empty inputs collapse to
    ``UNKNOWN_COORDINATE``. The ``provisional`` flag is always True so
    downstream readers cannot mistake the coordinates for final
    behavior tags.
    """
    return BehaviorCoordinates(
        family=_safe_str(strategy_family),
        asset_class=_safe_str(asset_class),
        timeframe=_safe_str(timeframe),
        provisional=True,
    )


def bucket_info_gain(score: object) -> str:
    """Pure bucketing of a numeric IG score.

    Mirrors ``research.information_gain._bucket_for`` thresholds. Non-
    numeric or out-of-range inputs collapse to ``BUCKET_NONE`` rather
    than raising, because this module is advisory and must never crash
    the report on a single bad row.
    """
    try:
        value = float(score)
    except (TypeError, ValueError):
        return BUCKET_NONE
    if value != value:  # NaN
        return BUCKET_NONE
    if value <= 0.0:
        return BUCKET_NONE
    if value < IG_BUCKET_MEDIUM_FLOOR:
        return BUCKET_LOW
    if value < IG_BUCKET_HIGH_FLOOR:
        return BUCKET_MEDIUM
    return BUCKET_HIGH


def _normalize_dead_zone_key(
    asset: object, timeframe: object, family: object,
) -> tuple[str, str, str]:
    """Build the (asset, timeframe, family) key matching the upstream
    dead-zone artifact. Pure."""
    return (_safe_str(asset), _safe_str(timeframe), _safe_str(family))


def classify_dead_zone_status(
    coords: BehaviorCoordinates,
    dead_zone_index: dict[tuple[str, str, str], str],
) -> str:
    """Pure lookup of the dead-zone status for a coordinate.

    The index is keyed on (asset, timeframe, family) — the same key the
    upstream artifact uses. Missing entries collapse to
    ``DEAD_ZONE_UNKNOWN``. Returns one of ``DEAD_ZONE_STATUSES``.
    """
    key = _normalize_dead_zone_key(
        coords.asset_class, coords.timeframe, coords.family,
    )
    status = dead_zone_index.get(key, DEAD_ZONE_UNKNOWN)
    if status not in DEAD_ZONE_STATUSES:
        return DEAD_ZONE_UNKNOWN
    return status


def compute_orthogonality_bucket(
    coords: BehaviorCoordinates,
    prior_coordinate_counts: dict[tuple[str, str, str], int],
) -> str:
    """Pure derivation of the orthogonality bucket.

    Inputs:

    * ``coords`` — the campaign's coordinate.
    * ``prior_coordinate_counts`` — count of prior occurrences of each
      coordinate across the active queue + recent completed campaigns.
      The caller is responsible for excluding the campaign itself from
      the count if desired; this function uses the provided count
      verbatim.

    Returns one of ``ORTHOGONALITY_BUCKETS``.
    """
    count = int(prior_coordinate_counts.get(coords.as_tuple(), 0))
    if count <= ORTHOGONALITY_NOVEL_MAX_PRIOR:
        return ORTHOGONALITY_NOVEL
    if count <= ORTHOGONALITY_ADJACENT_MAX_PRIOR:
        return ORTHOGONALITY_ADJACENT
    return ORTHOGONALITY_SATURATED


def compute_near_duplicate_group(
    coords: BehaviorCoordinates,
    fingerprint: object,
) -> str | None:
    """Pure derivation of a deterministic near-duplicate group hash.

    Inputs:

    * ``coords`` — the campaign's coordinate.
    * ``fingerprint`` — an existing artifact fingerprint string from
      the registry record (e.g. ``input_artifact_fingerprint``). Only
      the first ``NEAR_DUPLICATE_FINGERPRINT_PREFIX_LEN`` hex chars
      are read; nothing is computed from raw params.

    Returns ``None`` when the fingerprint is absent or empty. Otherwise
    returns the lowercase hex group hash (length
    ``NEAR_DUPLICATE_GROUP_HASH_LEN``).

    Determinism: ``hashlib.sha256`` over the sorted, ``|``-joined parts.
    """
    if fingerprint is None:
        return None
    text = str(fingerprint).strip()
    if not text:
        return None
    prefix = text[:NEAR_DUPLICATE_FINGERPRINT_PREFIX_LEN].lower()
    parts = sorted(
        [coords.family, coords.asset_class, coords.timeframe, prefix]
    )
    payload = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    return digest[:NEAR_DUPLICATE_GROUP_HASH_LEN]


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "ADVISORY_SUPPRESSION_REASONS",
    "BUCKET_HIGH",
    "BUCKET_LOW",
    "BUCKET_MEDIUM",
    "BUCKET_NONE",
    "BehaviorCoordinates",
    "DEAD_ZONE_ALIVE",
    "DEAD_ZONE_DEAD",
    "DEAD_ZONE_INSUFFICIENT_DATA",
    "DEAD_ZONE_STATUSES",
    "DEAD_ZONE_UNKNOWN",
    "DEAD_ZONE_WEAK",
    "IG_BUCKET_HIGH_FLOOR",
    "IG_BUCKET_MEDIUM_FLOOR",
    "INFO_GAIN_BUCKETS",
    "MODULE_VERSION",
    "NEAR_DUPLICATE_FINGERPRINT_PREFIX_LEN",
    "NEAR_DUPLICATE_GROUP_HASH_LEN",
    "NEVER_SUPPRESS_DEAD_ZONE_STATUSES",
    "ORTHOGONALITY_ADJACENT",
    "ORTHOGONALITY_ADJACENT_MAX_PRIOR",
    "ORTHOGONALITY_BUCKETS",
    "ORTHOGONALITY_NOVEL",
    "ORTHOGONALITY_NOVEL_MAX_PRIOR",
    "ORTHOGONALITY_SATURATED",
    "QUEUE_ORDERING_EFFECT_NONE",
    "REPORT_KIND",
    "ROUTING_EFFECT_ADVISORY_ONLY",
    "RoutingDecision",
    "RoutingReport",
    "RoutingReportSummary",
    "SCHEMA_VERSION",
    "SUPPRESSION_DEAD_ZONE",
    "SUPPRESSION_NEAR_DUPLICATE",
    "UNKNOWN_COORDINATE",
    "bucket_info_gain",
    "classify_dead_zone_status",
    "compute_near_duplicate_group",
    "compute_orthogonality_bucket",
    "derive_behavior_coordinates",
]
