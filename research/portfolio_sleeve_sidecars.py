"""v3.14 portfolio / sleeve façade.

Mirrors the v3.12 and v3.13 patterns exactly: a frozen build-context
dataclass plus a single ``build_and_write_*`` entry point that the
runner calls once. All writes go through
:func:`research._sidecar_io.write_sidecar_atomic` so every artifact
is canonical and byte-reproducible.

The façade is the only place that orchestrates v3.14's four new
sidecars:

- ``research/sleeve_registry_latest.v1.json``
- ``research/candidate_returns_latest.v1.json``
- ``research/portfolio_diagnostics_latest.v1.json``
- ``research/regime_width_distributions_latest.v1.json``
  (emitted when width-feed data is attached to the context)

Graceful missing-state: when the registry v2 is missing or empty
every sidecar is written with an empty ``entries``/``memberships``
payload so consumers always see a stable schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic
from research.candidate_returns_feed import (
    CandidateReturnsRecord,
    build_payload as build_candidate_returns_payload,
)
from research.portfolio_diagnostics import (
    build_portfolio_diagnostics_payload,
    compute_diagnostics,
)
from research.regime_classifier import REGIME_CLASSIFIER_VERSION
from research.regime_width_feed import WIDTH_FEED_VERSION, WidthFeedResult
from research.sleeve_registry import (
    SleeveRegistry,
    assign_sleeves,
    build_sleeve_registry_payload,
)


SLEEVE_REGISTRY_PATH = Path("research/sleeve_registry_latest.v1.json")
CANDIDATE_RETURNS_PATH = Path("research/candidate_returns_latest.v1.json")
PORTFOLIO_DIAGNOSTICS_PATH = Path("research/portfolio_diagnostics_latest.v1.json")
WIDTH_DISTRIBUTIONS_PATH = Path("research/regime_width_distributions_latest.v1.json")

WIDTH_DISTRIBUTIONS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class PortfolioSleeveBuildContext:
    """All inputs the v3.14 façade needs.

    ``width_feed_result`` is optional: when present the façade also
    writes the ``regime_width_distributions`` sidecar. The actual
    width dict should be threaded into the v3.13 façade
    (``regime_sidecars``) separately by the runner.
    """

    run_id: str
    generated_at_utc: str
    git_revision: str
    registry_v2: dict[str, Any]
    regime_overlay: dict[str, Any] | None
    candidate_returns: list[CandidateReturnsRecord]
    width_feed_result: WidthFeedResult | None = None


def _build_width_distributions_payload(
    *,
    feed: WidthFeedResult,
    generated_at_utc: str,
    run_id: str,
    git_revision: str,
) -> dict[str, Any]:
    entries = [
        {
            "candidate_id": candidate_id,
            "buckets": dict(buckets),
        }
        for candidate_id, buckets in sorted(feed.distributions.items())
    ]
    return {
        "schema_version": WIDTH_DISTRIBUTIONS_SCHEMA_VERSION,
        "classifier_version": REGIME_CLASSIFIER_VERSION,
        "width_feed_version": WIDTH_FEED_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "source_registry": "research/candidate_registry_latest.v2.json",
        "entries": entries,
        "lineage": list(feed.lineage),
    }


def build_and_write_portfolio_sleeve_sidecars(
    ctx: PortfolioSleeveBuildContext,
    *,
    sleeve_registry_path: Path = SLEEVE_REGISTRY_PATH,
    candidate_returns_path: Path = CANDIDATE_RETURNS_PATH,
    portfolio_diagnostics_path: Path = PORTFOLIO_DIAGNOSTICS_PATH,
    width_distributions_path: Path = WIDTH_DISTRIBUTIONS_PATH,
) -> dict[str, Path]:
    """Produce and write every v3.14 sidecar atomically.

    Returns a dict mapping logical artifact name to its written path.
    """
    paths: dict[str, Path] = {}

    sleeves = assign_sleeves(
        registry_v2=ctx.registry_v2,
        regime_overlay=ctx.regime_overlay,
    )
    sleeve_payload = build_sleeve_registry_payload(
        registry=sleeves,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )
    write_sidecar_atomic(sleeve_registry_path, sleeve_payload)
    paths["sleeve_registry"] = sleeve_registry_path

    returns_payload = build_candidate_returns_payload(
        records=list(ctx.candidate_returns),
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )
    write_sidecar_atomic(candidate_returns_path, returns_payload.to_payload())
    paths["candidate_returns"] = candidate_returns_path

    diagnostics_body = compute_diagnostics(
        registry_v2=ctx.registry_v2,
        sleeve_registry=sleeves,
        candidate_returns=ctx.candidate_returns,
        regime_overlay=ctx.regime_overlay,
    )
    diagnostics_payload = build_portfolio_diagnostics_payload(
        body=diagnostics_body,
        generated_at_utc=ctx.generated_at_utc,
        run_id=ctx.run_id,
        git_revision=ctx.git_revision,
    )
    write_sidecar_atomic(portfolio_diagnostics_path, diagnostics_payload)
    paths["portfolio_diagnostics"] = portfolio_diagnostics_path

    if ctx.width_feed_result is not None:
        width_payload = _build_width_distributions_payload(
            feed=ctx.width_feed_result,
            generated_at_utc=ctx.generated_at_utc,
            run_id=ctx.run_id,
            git_revision=ctx.git_revision,
        )
        write_sidecar_atomic(width_distributions_path, width_payload)
        paths["regime_width_distributions"] = width_distributions_path

    return paths


def _empty_sleeve_registry() -> SleeveRegistry:
    return SleeveRegistry(sleeves=[], memberships=[])


__all__ = [
    "CANDIDATE_RETURNS_PATH",
    "PORTFOLIO_DIAGNOSTICS_PATH",
    "SLEEVE_REGISTRY_PATH",
    "WIDTH_DISTRIBUTIONS_PATH",
    "WIDTH_DISTRIBUTIONS_SCHEMA_VERSION",
    "PortfolioSleeveBuildContext",
    "build_and_write_portfolio_sleeve_sidecars",
]
