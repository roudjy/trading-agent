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

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Final, Sequence

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
# Advisory priority weights (PR-C)
# ---------------------------------------------------------------------------

#: Information-gain bucket → priority weight. Named constants per
#: CLAUDE.md. Higher is better.
INFO_GAIN_BUCKET_WEIGHTS: Final[dict[str, int]] = {
    BUCKET_NONE: 0,
    BUCKET_LOW: 1,
    BUCKET_MEDIUM: 2,
    BUCKET_HIGH: 3,
}

#: Orthogonality bucket → priority weight. Higher is better.
ORTHOGONALITY_BUCKET_WEIGHTS: Final[dict[str, int]] = {
    ORTHOGONALITY_SATURATED: 0,
    ORTHOGONALITY_ADJACENT: 1,
    ORTHOGONALITY_NOVEL: 2,
}

#: IG dominates orthogonality. Multiplier is intentionally larger than
#: ``max(ORTHOGONALITY_BUCKET_WEIGHTS.values())`` so an IG step always
#: outranks any orthogonality difference.
INFO_GAIN_PRIORITY_MULTIPLIER: Final[int] = 10

#: A campaign with ``advisory_suppression_reason != None`` receives this
#: priority score so it sinks below every non-suppressed campaign in
#: ``advisory_rank``. The artifact's ``queue_ordering_effect`` is still
#: ``none`` — this is a *recommendation only*.
SUPPRESSED_PRIORITY_SCORE: Final[int] = -1


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


def derive_advisory_suppression_reason(
    *,
    dead_zone_status: str,
    near_duplicate_group: str | None,
    is_first_in_group: bool,
) -> str | None:
    """Pure derivation of the advisory suppression reason.

    Resolution order:

    1. ``dead_zone`` if and only if ``dead_zone_status == DEAD_ZONE_DEAD``.
       Statuses in ``NEVER_SUPPRESS_DEAD_ZONE_STATUSES`` *never*
       trigger suppression.
    2. ``near_duplicate`` if and only if the campaign is part of a
       near-duplicate group AND is **not** the first member of that
       group (the first member always keeps ``None``).
    3. ``None`` otherwise.

    The framing remains advisory: the artifact still carries
    ``routing_effect = "advisory_only"``. Downstream queue ordering
    is not changed.
    """
    if dead_zone_status == DEAD_ZONE_DEAD:
        return SUPPRESSION_DEAD_ZONE
    if near_duplicate_group is not None and not is_first_in_group:
        return SUPPRESSION_NEAR_DUPLICATE
    return None


def compute_advisory_priority_score(
    *,
    advisory_suppression_reason: str | None,
    info_gain_bucket: str,
    orthogonality_bucket: str,
) -> int:
    """Pure derivation of the advisory priority score.

    Suppressed campaigns receive ``SUPPRESSED_PRIORITY_SCORE`` so they
    always rank below non-suppressed campaigns. Non-suppressed
    campaigns receive ``ig_weight * INFO_GAIN_PRIORITY_MULTIPLIER +
    ortho_weight``. Higher is better. Unknown bucket names map to
    weight 0 (defensive fallback).
    """
    if advisory_suppression_reason is not None:
        return SUPPRESSED_PRIORITY_SCORE
    ig_weight = INFO_GAIN_BUCKET_WEIGHTS.get(info_gain_bucket, 0)
    ortho_weight = ORTHOGONALITY_BUCKET_WEIGHTS.get(orthogonality_bucket, 0)
    return ig_weight * INFO_GAIN_PRIORITY_MULTIPLIER + ortho_weight


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
# Read-only input paths (PR-B)
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

CAMPAIGN_QUEUE_PATH: Final[Path] = (
    REPO_ROOT / "research" / "campaign_queue_latest.v1.json"
)
CAMPAIGN_REGISTRY_PATH: Final[Path] = (
    REPO_ROOT / "research" / "campaign_registry_latest.v1.json"
)
DEAD_ZONES_PATH: Final[Path] = (
    REPO_ROOT / "research" / "campaigns" / "evidence"
    / "dead_zones_latest.v1.json"
)
INFORMATION_GAIN_PATH: Final[Path] = (
    REPO_ROOT / "research" / "campaigns" / "evidence"
    / "information_gain_latest.v1.json"
)

INPUT_PATHS: Final[tuple[Path, ...]] = (
    CAMPAIGN_QUEUE_PATH,
    CAMPAIGN_REGISTRY_PATH,
    DEAD_ZONES_PATH,
    INFORMATION_GAIN_PATH,
)


# ---------------------------------------------------------------------------
# Output path (PR-B)
# ---------------------------------------------------------------------------

OUTPUT_DIR: Final[Path] = REPO_ROOT / "logs" / "intelligent_routing"
LATEST_OUTPUT_PATH: Final[Path] = OUTPUT_DIR / "latest.json"


# ---------------------------------------------------------------------------
# Provenance + safe loaders (PR-B)
# ---------------------------------------------------------------------------


def _provenance_entry(path: Path) -> dict[str, str]:
    """Sha256 + mtime UTC for a path. Returns the not-available envelope
    when the path is missing or unreadable.

    Pure: never raises. Reads bytes; never opens in write mode.
    """
    try:
        if not path.exists() or not path.is_file():
            return {"status": "not_available"}
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        mtime_dt = _dt.datetime.fromtimestamp(
            path.stat().st_mtime, tz=_dt.timezone.utc,
        )
        return {
            "status": "present",
            "sha256": digest,
            "mtime_utc": mtime_dt.isoformat(),
        }
    except OSError:
        return {"status": "not_available"}


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON object from ``path``. Returns None if the file does
    not exist, is unreadable, or is malformed.

    Never raises. Read-only — never opens the path in write mode.
    """
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


# ---------------------------------------------------------------------------
# Index helpers (PR-B)
# ---------------------------------------------------------------------------


def _index_registry(
    registry_payload: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Project the registry payload to ``{campaign_id: record_dict}``.

    Tolerates absent / malformed payloads. Read-only.
    """
    if not registry_payload:
        return {}
    records = registry_payload.get("campaigns") or registry_payload.get(
        "registry"
    ) or []
    if not isinstance(records, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        cid = rec.get("campaign_id")
        if not isinstance(cid, str) or not cid:
            continue
        out[cid] = rec
    return out


def _index_dead_zones(
    dead_zones_payload: dict[str, Any] | None,
) -> dict[tuple[str, str, str], str]:
    """Project the dead-zones payload to
    ``{(asset, timeframe, strategy_family): zone_status}``.

    Mirrors the upstream artifact's key order. Tolerates malformed
    payloads.
    """
    if not dead_zones_payload:
        return {}
    zones = dead_zones_payload.get("zones") or []
    if not isinstance(zones, list):
        return {}
    out: dict[tuple[str, str, str], str] = {}
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        key = _normalize_dead_zone_key(
            zone.get("asset"),
            zone.get("timeframe"),
            zone.get("strategy_family"),
        )
        status = zone.get("zone_status")
        if not isinstance(status, str):
            continue
        if status not in DEAD_ZONE_STATUSES:
            status = DEAD_ZONE_UNKNOWN
        out[key] = status
    return out


def _index_information_gain(
    ig_payload: dict[str, Any] | None,
) -> dict[str, float]:
    """Project the information-gain payload to ``{campaign_id: score}``.

    The upstream artifact carries a single-campaign payload (one
    ``col_campaign_id`` per file). The lookup is therefore sparse —
    most campaigns will have no entry; ``build_report`` falls back to
    score 0.0 / bucket "none" in that case.
    """
    if not ig_payload:
        return {}
    cid = ig_payload.get("col_campaign_id")
    ig = ig_payload.get("information_gain") or {}
    if not isinstance(cid, str) or not cid:
        return {}
    if not isinstance(ig, dict):
        return {}
    score = ig.get("score")
    try:
        score_f = float(score)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return {}
    return {cid: score_f}


def _queue_entries(
    queue_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not queue_payload:
        return []
    entries = queue_payload.get("queue") or []
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict)]


def _coords_for_campaign(
    cid: str,
    registry_index: dict[str, dict[str, Any]],
) -> tuple[BehaviorCoordinates, str, str | None, bool]:
    """Return (coords, preset_name, fingerprint, has_full_metadata).

    ``has_full_metadata`` is False when at least one of the three
    coordinate fields was missing or empty in the registry record —
    used to populate ``summary.metadata_gaps``.
    """
    rec = registry_index.get(cid, {})
    family = rec.get("strategy_family")
    asset_class = rec.get("asset_class")
    extra = rec.get("extra") if isinstance(rec.get("extra"), dict) else {}
    timeframe = (
        rec.get("timeframe")
        or rec.get("interval")
        or extra.get("timeframe")
        or extra.get("interval")
    )
    coords = derive_behavior_coordinates(
        strategy_family=family,
        asset_class=asset_class,
        timeframe=timeframe,
    )
    has_full = (
        coords.family != UNKNOWN_COORDINATE
        and coords.asset_class != UNKNOWN_COORDINATE
        and coords.timeframe != UNKNOWN_COORDINATE
    )
    preset_name = rec.get("preset_name")
    if not isinstance(preset_name, str) or not preset_name:
        preset_name = UNKNOWN_COORDINATE
    fingerprint = rec.get("input_artifact_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        fingerprint = None
    return coords, preset_name, fingerprint, has_full


# ---------------------------------------------------------------------------
# Report builder (PR-B)
# ---------------------------------------------------------------------------


def _now_utc_default() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.timezone.utc)


def build_report(
    *,
    now_utc: Callable[[], _dt.datetime] | _dt.datetime | None = None,
    queue_path: Path = CAMPAIGN_QUEUE_PATH,
    registry_path: Path = CAMPAIGN_REGISTRY_PATH,
    dead_zones_path: Path = DEAD_ZONES_PATH,
    information_gain_path: Path = INFORMATION_GAIN_PATH,
) -> RoutingReport:
    """Pure (modulo file reads) builder for the advisory routing report.

    No I/O writes anywhere. ``now_utc`` is an injectable seam for
    deterministic tests: pass either a callable returning a tz-aware
    datetime, a frozen datetime, or ``None`` (defaults to
    ``datetime.now(tz=UTC)``).

    PR-B: populates behavior_coordinates, info_gain_score/bucket,
    dead_zone_status, near_duplicate_group, orthogonality_bucket.

    PR-C: derives ``advisory_suppression_reason`` (dead-zone or
    near-duplicate annotation only — queue is **not** mutated),
    ``advisory_priority_score`` (deterministic int) and
    ``advisory_rank`` (1-indexed total ordering). The artifact still
    carries ``routing_effect = "advisory_only"`` and
    ``queue_ordering_effect = "none"``.
    """
    if callable(now_utc):
        as_of = now_utc()
    elif isinstance(now_utc, _dt.datetime):
        as_of = now_utc
    else:
        as_of = _now_utc_default()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=_dt.timezone.utc)

    queue_payload = _read_json(queue_path)
    registry_payload = _read_json(registry_path)
    dead_zones_payload = _read_json(dead_zones_path)
    ig_payload = _read_json(information_gain_path)

    queue = _queue_entries(queue_payload)
    registry_index = _index_registry(registry_payload)
    dead_zone_index = _index_dead_zones(dead_zones_payload)
    ig_index = _index_information_gain(ig_payload)

    # First pass: per-campaign coords + metadata.
    coord_records: list[tuple[dict[str, Any], BehaviorCoordinates, str, str | None, bool]] = []
    for entry in queue:
        cid = entry.get("campaign_id")
        if not isinstance(cid, str) or not cid:
            continue
        coords, preset_name, fp, has_full = _coords_for_campaign(
            cid, registry_index,
        )
        coord_records.append((entry, coords, preset_name, fp, has_full))

    # Prior-coordinate counts across the whole input set. The bucket
    # uses *prior* count, so a coord seen N times in the queue should
    # use N-1 as its prior. Build the count table once, then subtract
    # 1 for self when classifying each entry.
    coord_counts: Counter[tuple[str, str, str]] = Counter()
    for _, coords, _, _, _ in coord_records:
        coord_counts[coords.as_tuple()] += 1

    # First pass: build provisional per-campaign rows without
    # advisory_* fields.
    provisional_rows: list[dict[str, Any]] = []
    metadata_gaps = 0
    for entry, coords, preset_name, fp, has_full in coord_records:
        cid = str(entry.get("campaign_id"))
        spawned_at = str(entry.get("spawned_at_utc") or "")
        score = float(ig_index.get(cid, 0.0))
        bucket = bucket_info_gain(score)
        zone_status = classify_dead_zone_status(coords, dead_zone_index)
        if not has_full:
            metadata_gaps += 1
        prior_total = max(0, coord_counts[coords.as_tuple()] - 1)
        ortho = compute_orthogonality_bucket(
            coords, {coords.as_tuple(): prior_total},
        )
        group = compute_near_duplicate_group(coords, fp)
        provisional_rows.append({
            "campaign_id": cid,
            "preset_name": preset_name,
            "coords": coords,
            "score": round(score, 4),
            "bucket": bucket,
            "zone_status": zone_status,
            "group": group,
            "ortho": ortho,
            "tie_break_key": f"{spawned_at}|{cid}",
        })

    # Second pass: identify the first member of each near-duplicate
    # group by tie_break_key. Within a group, the first-by-
    # (spawned_at_utc, campaign_id) row keeps suppression=None; the
    # rest get advisory_suppression_reason="near_duplicate" — UNLESS
    # the dead-zone status already set the reason to "dead_zone".
    group_members: dict[str, list[str]] = {}
    for row in provisional_rows:
        gid = row["group"]
        if gid is None:
            continue
        group_members.setdefault(gid, []).append(row["tie_break_key"])
    first_member_in_group: dict[str, str] = {
        gid: min(keys) for gid, keys in group_members.items()
    }

    # Third pass: derive advisory_suppression_reason +
    # advisory_priority_score per row.
    enriched: list[RoutingDecision] = []
    for row in provisional_rows:
        gid = row["group"]
        if gid is None:
            is_first = True
        else:
            is_first = first_member_in_group[gid] == row["tie_break_key"]
        reason = derive_advisory_suppression_reason(
            dead_zone_status=row["zone_status"],
            near_duplicate_group=gid,
            is_first_in_group=is_first,
        )
        priority = compute_advisory_priority_score(
            advisory_suppression_reason=reason,
            info_gain_bucket=row["bucket"],
            orthogonality_bucket=row["ortho"],
        )
        enriched.append(
            RoutingDecision(
                campaign_id=row["campaign_id"],
                preset_name=row["preset_name"],
                behavior_coordinates=row["coords"],
                info_gain_score=row["score"],
                info_gain_bucket=row["bucket"],
                dead_zone_status=row["zone_status"],
                near_duplicate_group=gid,
                orthogonality_bucket=row["ortho"],
                advisory_suppression_reason=reason,
                advisory_priority_score=priority,
                advisory_rank=0,  # filled in below
                tie_break_key=row["tie_break_key"],
            )
        )

    # Fourth pass: total ordering by (-advisory_priority_score,
    # tie_break_key). Higher priority first; ties broken by
    # (spawned_at_utc, campaign_id) ascending. Assign 1-indexed
    # advisory_rank.
    enriched.sort(
        key=lambda d: (-d.advisory_priority_score, d.tie_break_key)
    )
    decisions: list[RoutingDecision] = []
    for idx, d in enumerate(enriched, start=1):
        decisions.append(
            dataclasses.replace(d, advisory_rank=idx)
        )

    summary = RoutingReportSummary(
        total=len(decisions),
        advisory_suppressed_dead_zone=sum(
            1 for d in decisions
            if d.advisory_suppression_reason == SUPPRESSION_DEAD_ZONE
        ),
        advisory_suppressed_near_duplicate=sum(
            1 for d in decisions
            if d.advisory_suppression_reason == SUPPRESSION_NEAR_DUPLICATE
        ),
        high_info_gain=sum(
            1 for d in decisions if d.info_gain_bucket == BUCKET_HIGH
        ),
        novel_behavior_coordinates=sum(
            1 for d in decisions if d.orthogonality_bucket == ORTHOGONALITY_NOVEL
        ),
        metadata_gaps=metadata_gaps,
    )

    provenance: dict[str, dict[str, str]] = {}
    for path in (queue_path, registry_path, dead_zones_path, information_gain_path):
        try:
            rel = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            rel = str(path)
        provenance[rel] = _provenance_entry(path)

    return RoutingReport(
        schema_version=SCHEMA_VERSION,
        report_kind=REPORT_KIND,
        version=MODULE_VERSION,
        routing_effect=ROUTING_EFFECT_ADVISORY_ONLY,
        queue_ordering_effect=QUEUE_ORDERING_EFFECT_NONE,
        generated_at_utc=as_of.astimezone(_dt.timezone.utc).isoformat(),
        provenance=provenance,
        decisions=tuple(decisions),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Atomic writer (PR-B)
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic JSON write to ``path``. Creates parent dir if needed.

    Determinism: ``sort_keys=True``, indent=2, trailing newline. The
    write goes through a temp file in the *same* directory so the
    final ``os.replace`` is atomic on the same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_path, path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI (PR-B)
# ---------------------------------------------------------------------------

CLI_DESCRIPTION: Final[str] = (
    "v3.15.16 advisory Intelligent Routing Layer reporter. "
    "Default: --no-write (prints JSON, writes nothing). "
    "Pass --write to persist logs/intelligent_routing/latest.json. "
    "Routing effect: advisory_only. Queue ordering effect: none."
)


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.intelligent_routing",
        description=CLI_DESCRIPTION,
    )
    write_group = parser.add_mutually_exclusive_group()
    write_group.add_argument(
        "--no-write",
        dest="write",
        action="store_false",
        help=(
            "Print the report to stdout and do not write any artifact "
            "(default)."
        ),
    )
    write_group.add_argument(
        "--write",
        dest="write",
        action="store_true",
        help=(
            "Persist logs/intelligent_routing/latest.json (single "
            "file; no timestamped siblings)."
        ),
    )
    parser.set_defaults(write=False)
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout (default: 2).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns process exit code (0 on success).

    Default behavior is ``--no-write``: prints the JSON report to
    stdout and writes nothing. ``--write`` persists exactly one file
    at ``logs/intelligent_routing/latest.json``.
    """
    parser = _build_argparser()
    args = parser.parse_args(argv)
    report = build_report()
    payload = report.to_payload()
    if args.write:
        _atomic_write_json(LATEST_OUTPUT_PATH, payload)
    sys.stdout.write(
        json.dumps(payload, indent=int(args.indent), sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "ADVISORY_SUPPRESSION_REASONS",
    "BUCKET_HIGH",
    "CAMPAIGN_QUEUE_PATH",
    "CAMPAIGN_REGISTRY_PATH",
    "DEAD_ZONES_PATH",
    "INFORMATION_GAIN_PATH",
    "INPUT_PATHS",
    "LATEST_OUTPUT_PATH",
    "OUTPUT_DIR",
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
    "INFO_GAIN_BUCKET_WEIGHTS",
    "INFO_GAIN_PRIORITY_MULTIPLIER",
    "MODULE_VERSION",
    "NEAR_DUPLICATE_FINGERPRINT_PREFIX_LEN",
    "NEAR_DUPLICATE_GROUP_HASH_LEN",
    "NEVER_SUPPRESS_DEAD_ZONE_STATUSES",
    "ORTHOGONALITY_ADJACENT",
    "ORTHOGONALITY_ADJACENT_MAX_PRIOR",
    "ORTHOGONALITY_BUCKETS",
    "ORTHOGONALITY_NOVEL",
    "ORTHOGONALITY_BUCKET_WEIGHTS",
    "ORTHOGONALITY_NOVEL_MAX_PRIOR",
    "ORTHOGONALITY_SATURATED",
    "QUEUE_ORDERING_EFFECT_NONE",
    "REPORT_KIND",
    "ROUTING_EFFECT_ADVISORY_ONLY",
    "RoutingDecision",
    "RoutingReport",
    "RoutingReportSummary",
    "SCHEMA_VERSION",
    "SUPPRESSED_PRIORITY_SCORE",
    "SUPPRESSION_DEAD_ZONE",
    "SUPPRESSION_NEAR_DUPLICATE",
    "UNKNOWN_COORDINATE",
    "bucket_info_gain",
    "build_report",
    "classify_dead_zone_status",
    "compute_advisory_priority_score",
    "compute_near_duplicate_group",
    "compute_orthogonality_bucket",
    "derive_advisory_suppression_reason",
    "derive_behavior_coordinates",
    "main",
]
