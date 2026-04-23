"""End-to-end tests for the v3.13 regime sidecar façade.

These exercise ``build_and_write_regime_sidecars`` against a tmp_path
and verify:

- both sidecars are written
- overlay joins cleanly on ``candidate_id``
- missing-state is graceful (absent regime_diagnostics → every
  candidate gets ``insufficient_regime_evidence``)
- rerun with identical inputs is byte-identical
"""

from __future__ import annotations

import json
from pathlib import Path

from research.regime_sidecars import (
    REGIME_INTELLIGENCE_SCHEMA_VERSION,
    REGIME_OVERLAY_SCHEMA_VERSION,
    RegimeSidecarBuildContext,
    build_and_write_regime_sidecars,
)


def _registry_v2(candidate_ids: list[str]) -> dict:
    return {
        "schema_version": "2.0",
        "entries": [
            {
                "candidate_id": cid,
                "strategy_name": "sma_crossover",
                "asset": "NVDA",
                "interval": "4h",
            }
            for cid in candidate_ids
        ],
    }


def _regime_diag(candidate_id: str) -> dict:
    """Sufficient-evidence breakdown for a single candidate."""
    return {
        "strategies": [
            {
                "strategy_id": candidate_id,
                "regime_breakdown": {
                    "trend": [
                        {
                            "label": "trending",
                            "coverage_count": 60,
                            "arithmetic_return_contribution": 5.0,
                            "trade_count": 15,
                            "trade_metrics": {"total_pnl": 5.0},
                        },
                        {
                            "label": "non_trending",
                            "coverage_count": 40,
                            "arithmetic_return_contribution": 1.0,
                            "trade_count": 5,
                            "trade_metrics": {"total_pnl": 1.0},
                        },
                    ],
                    "volatility": [
                        {
                            "label": "high_vol",
                            "coverage_count": 30,
                            "arithmetic_return_contribution": 4.0,
                            "trade_count": 10,
                            "trade_metrics": {"total_pnl": 4.0},
                        },
                        {
                            "label": "low_vol",
                            "coverage_count": 70,
                            "arithmetic_return_contribution": 2.0,
                            "trade_count": 10,
                            "trade_metrics": {"total_pnl": 2.0},
                        },
                    ],
                },
            }
        ]
    }


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_both_sidecars_are_written(tmp_path: Path) -> None:
    intel = tmp_path / "intel.json"
    overlay = tmp_path / "overlay.json"
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(["cid-a", "cid-b"]),
        regime_diagnostics=_regime_diag("cid-a"),
    )
    paths = build_and_write_regime_sidecars(
        ctx, intelligence_path=intel, overlay_path=overlay
    )
    assert paths["regime_intelligence"] == intel
    assert paths["regime_overlay"] == overlay
    assert intel.exists()
    assert overlay.exists()


def test_intelligence_schema_and_overlay_schema_versions_are_pinned(tmp_path: Path) -> None:
    intel = tmp_path / "intel.json"
    overlay = tmp_path / "overlay.json"
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(["cid-a"]),
        regime_diagnostics=None,
    )
    build_and_write_regime_sidecars(ctx, intelligence_path=intel, overlay_path=overlay)
    intel_payload = _read(intel)
    overlay_payload = _read(overlay)
    assert intel_payload["schema_version"] == REGIME_INTELLIGENCE_SCHEMA_VERSION
    assert overlay_payload["schema_version"] == REGIME_OVERLAY_SCHEMA_VERSION


def test_overlay_joins_every_entry_on_candidate_id(tmp_path: Path) -> None:
    intel = tmp_path / "intel.json"
    overlay = tmp_path / "overlay.json"
    candidate_ids = ["cid-a", "cid-b", "cid-c"]
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(candidate_ids),
        regime_diagnostics=None,
    )
    build_and_write_regime_sidecars(ctx, intelligence_path=intel, overlay_path=overlay)
    intel_payload = _read(intel)
    overlay_payload = _read(overlay)
    intel_ids = {e["candidate_id"] for e in intel_payload["entries"]}
    overlay_ids = {e["candidate_id"] for e in overlay_payload["entries"]}
    assert intel_ids == set(candidate_ids)
    assert overlay_ids == set(candidate_ids)
    # Every overlay entry points at the v2 registry file
    assert overlay_payload["source_registry"] == "research/candidate_registry_latest.v2.json"


def test_missing_regime_diagnostics_leaves_all_candidates_insufficient(tmp_path: Path) -> None:
    intel = tmp_path / "intel.json"
    overlay = tmp_path / "overlay.json"
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(["cid-a"]),
        regime_diagnostics=None,
    )
    build_and_write_regime_sidecars(ctx, intelligence_path=intel, overlay_path=overlay)
    intel_payload = _read(intel)
    assert intel_payload["summary"]["candidates_with_sufficient_evidence"] == 0
    overlay_payload = _read(overlay)
    assert (
        overlay_payload["entries"][0]["regime_concentrated_status"] == "absent_sidecar"
    )


def test_rerun_produces_byte_identical_sidecars(tmp_path: Path) -> None:
    intel_a = tmp_path / "intel_a.json"
    intel_b = tmp_path / "intel_b.json"
    overlay_a = tmp_path / "overlay_a.json"
    overlay_b = tmp_path / "overlay_b.json"
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(["cid-a", "cid-b"]),
        regime_diagnostics=_regime_diag("cid-a"),
    )
    build_and_write_regime_sidecars(
        ctx, intelligence_path=intel_a, overlay_path=overlay_a
    )
    build_and_write_regime_sidecars(
        ctx, intelligence_path=intel_b, overlay_path=overlay_b
    )
    assert intel_a.read_bytes() == intel_b.read_bytes()
    assert overlay_a.read_bytes() == overlay_b.read_bytes()


def test_best_rule_is_always_null_in_v3_13(tmp_path: Path) -> None:
    intel = tmp_path / "intel.json"
    overlay = tmp_path / "overlay.json"
    ctx = RegimeSidecarBuildContext(
        run_id="rid",
        generated_at_utc="2026-04-23T12:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=_registry_v2(["cid-a"]),
        regime_diagnostics=_regime_diag("cid-a"),
    )
    build_and_write_regime_sidecars(ctx, intelligence_path=intel, overlay_path=overlay)
    overlay_payload = _read(overlay)
    for entry in overlay_payload["entries"]:
        assert entry["regime_gating_summary"]["best_rule"] is None
