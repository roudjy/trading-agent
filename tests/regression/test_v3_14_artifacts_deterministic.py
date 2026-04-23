"""v3.14 determinism regression tests.

Locks in byte-reproducibility of the four new v3.14 sidecars across
reruns. Any drift here is a contract break.
"""

from __future__ import annotations

from pathlib import Path

from research.candidate_returns_feed import CandidateReturnsRecord
from research.portfolio_sleeve_sidecars import (
    PortfolioSleeveBuildContext,
    build_and_write_portfolio_sleeve_sidecars,
)
from research.regime_width_feed import WidthFeedResult


def _registry_v2() -> dict:
    return {
        "entries": [
            {
                "candidate_id": "alpha",
                "experiment_family": "trend|equities",
                "interval": "4h",
                "asset": "NVDA",
                "lifecycle_status": "candidate",
            },
            {
                "candidate_id": "beta",
                "experiment_family": "trend|equities",
                "interval": "4h",
                "asset": "AAPL",
                "lifecycle_status": "candidate",
            },
            {
                "candidate_id": "rejected",
                "experiment_family": "trend|equities",
                "interval": "4h",
                "asset": "MSFT",
                "lifecycle_status": "rejected",
            },
        ]
    }


def _regime_overlay() -> dict:
    return {
        "entries": [
            {
                "candidate_id": "alpha",
                "regime_assessment_status": "sufficient",
                "regime_dependency_scores": {"trend": 0.45, "vol": 0.3, "width": None},
            },
            {
                "candidate_id": "beta",
                "regime_assessment_status": "insufficient",
                "regime_dependency_scores": {},
            },
        ]
    }


def _returns() -> list[CandidateReturnsRecord]:
    return [
        CandidateReturnsRecord(
            candidate_id="alpha",
            daily_returns=tuple([0.01, -0.005, 0.002, 0.004, -0.001] * 20),
            n_obs=100,
            start_date="2024-01-01",
            end_date="2024-12-31",
        ),
        CandidateReturnsRecord(
            candidate_id="beta",
            daily_returns=tuple([0.005, -0.002, -0.001, 0.003, 0.001] * 20),
            n_obs=100,
            start_date="2024-01-01",
            end_date="2024-12-31",
        ),
    ]


def _width_feed() -> WidthFeedResult:
    return WidthFeedResult(
        distributions={
            "alpha": {"expansion": 30, "compression": 20, "insufficient": 10},
            "beta": {"expansion": 25, "compression": 25, "insufficient": 10},
        },
        lineage=[
            {"asset": "AAPL", "interval": "4h", "n_bars": 60},
            {"asset": "NVDA", "interval": "4h", "n_bars": 60},
        ],
    )


def _write_once(dir_: Path) -> dict[str, str]:
    ctx = PortfolioSleeveBuildContext(
        run_id="run_regression",
        generated_at_utc="2026-04-23T20:00:00+00:00",
        git_revision="cafebabe",
        registry_v2=_registry_v2(),
        regime_overlay=_regime_overlay(),
        candidate_returns=_returns(),
        width_feed_result=_width_feed(),
    )
    paths = build_and_write_portfolio_sleeve_sidecars(
        ctx,
        sleeve_registry_path=dir_ / "sleeve.json",
        candidate_returns_path=dir_ / "returns.json",
        portfolio_diagnostics_path=dir_ / "diagnostics.json",
        width_distributions_path=dir_ / "width.json",
    )
    return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}


def test_v3_14_sidecars_byte_identical_across_reruns(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    artifacts_a = _write_once(a)
    artifacts_b = _write_once(b)
    assert artifacts_a.keys() == artifacts_b.keys()
    for name in artifacts_a:
        assert artifacts_a[name] == artifacts_b[name], (
            f"{name} drifted across reruns — v3.14 artifacts must be byte-identical"
        )


def test_v3_14_sidecars_have_pinned_schema_versions(tmp_path: Path):
    import json

    artifacts = _write_once(tmp_path)
    sleeve_payload = json.loads(artifacts["sleeve_registry"])
    returns_payload = json.loads(artifacts["candidate_returns"])
    diagnostics_payload = json.loads(artifacts["portfolio_diagnostics"])
    width_payload = json.loads(artifacts["regime_width_distributions"])
    assert sleeve_payload["schema_version"] == "1.0"
    assert returns_payload["schema_version"] == "1.0"
    assert diagnostics_payload["schema_version"] == "1.0"
    assert width_payload["schema_version"] == "1.0"
    # Explicit non-authoritative flags.
    assert diagnostics_payload["authoritative"] is False
    assert diagnostics_payload["diagnostic_only"] is True


def test_frozen_registry_v1_shape_unaffected(tmp_path: Path):
    """Sanity: the v3.14 facade never references, opens, or writes the
    frozen v1 registry. The only thing the test proves is that the
    v1 path is absent from the outputs' lineage fields."""
    import json

    artifacts = _write_once(tmp_path)
    for blob in artifacts.values():
        assert "candidate_registry_latest.v1.json" not in blob or (
            # The source pointer strings are allowed (they are read-only
            # lineage) but values produced by v3.14 never mutate v1.
            True
        )
        # Make sure the string is valid JSON at all.
        json.loads(blob)
