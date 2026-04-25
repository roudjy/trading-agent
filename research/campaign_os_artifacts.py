"""Shared constants + pin-block helpers for the v3.15.2 Campaign OS.

Every COL (Campaign Operating Layer) artifact carries the same top-level
pin block so downstream consumers can audit the artifact's authoritative
status without guessing. This module is pure: no IO, no clock reads
beyond a single injected ``now`` source.

Pin-block contract (stable across every COL artifact):

- schema_version        : per-artifact semver string
- campaign_os_version   : COL-wide release pin
- authoritative         : always False in v3.15.2
- diagnostic_only       : always True in v3.15.2
- live_eligible         : always False in v3.15.2 (hard invariant)
- generated_at_utc      : ISO-8601 UTC timestamp, injected
- git_revision          : short git hash, best-effort, None if unavailable
- run_id                : the pipeline run that produced this artifact, or None
- artifact_state        : one of ARTIFACT_STATES

Artifacts that are JSONL (only the evidence ledger at present) keep the
pin block in a companion ``*.meta.json`` file — same contract, same
helper.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

CAMPAIGN_OS_VERSION: str = "v0.1"

# Closed vocabulary for the artifact_state pin. Policy tick refuses to
# mutate state when any required upstream artifact is "stale" or
# "corrupt" — surfaces through the digest without crashing.
ArtifactState = Literal["healthy", "stale", "corrupt"]
ARTIFACT_STATES: tuple[str, ...] = ("healthy", "stale", "corrupt")


def iso_utc(ts: datetime) -> str:
    """Return ``ts`` as an ISO-8601 UTC string with a trailing Z.

    Mirrors the format used across research/ sidecars: microsecond
    precision preserved, timezone normalized to UTC.
    """
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_pin_block(
    *,
    schema_version: str,
    generated_at_utc: datetime,
    git_revision: str | None = None,
    run_id: str | None = None,
    artifact_state: ArtifactState = "healthy",
) -> dict[str, Any]:
    """Return the canonical COL pin block dict.

    All fields are required by downstream consumers; callers that do not
    have a ``run_id`` or ``git_revision`` must pass ``None`` explicitly so
    the field is present with a null value (avoids ambiguous schema).
    """
    if artifact_state not in ARTIFACT_STATES:
        raise ValueError(
            f"artifact_state must be one of {ARTIFACT_STATES!r}, "
            f"got {artifact_state!r}"
        )
    return {
        "schema_version": schema_version,
        "campaign_os_version": CAMPAIGN_OS_VERSION,
        "authoritative": False,
        "diagnostic_only": True,
        "live_eligible": False,
        "generated_at_utc": iso_utc(generated_at_utc),
        "git_revision": git_revision,
        "run_id": run_id,
        "artifact_state": artifact_state,
    }


def assert_pin_block_invariants(payload: dict[str, Any]) -> None:
    """Raise if the pin block violates any v3.15.2 hard invariant.

    Intended for test suites and defensive production checks: catches
    accidental ``live_eligible=True``, drifted ``campaign_os_version``,
    or missing fields before the artifact is emitted further downstream.
    """
    required = (
        "schema_version",
        "campaign_os_version",
        "authoritative",
        "diagnostic_only",
        "live_eligible",
        "generated_at_utc",
        "git_revision",
        "run_id",
        "artifact_state",
    )
    missing = [field for field in required if field not in payload]
    if missing:
        raise ValueError(f"pin block missing fields: {sorted(missing)}")

    if payload["campaign_os_version"] != CAMPAIGN_OS_VERSION:
        raise ValueError(
            f"campaign_os_version drift: expected {CAMPAIGN_OS_VERSION!r}, "
            f"got {payload['campaign_os_version']!r}"
        )
    if payload["live_eligible"] is not False:
        raise ValueError("live_eligible must be False in v3.15.2")
    if payload["authoritative"] is not False:
        raise ValueError("authoritative must be False in v3.15.2")
    if payload["diagnostic_only"] is not True:
        raise ValueError("diagnostic_only must be True in v3.15.2")
    if payload["artifact_state"] not in ARTIFACT_STATES:
        raise ValueError(
            f"artifact_state invalid: {payload['artifact_state']!r}"
        )


__all__ = [
    "ARTIFACT_STATES",
    "ArtifactState",
    "CAMPAIGN_OS_VERSION",
    "assert_pin_block_invariants",
    "build_pin_block",
    "iso_utc",
]
