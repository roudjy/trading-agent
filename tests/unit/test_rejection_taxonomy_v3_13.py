"""v3.13-specific extensions to research.rejection_taxonomy.

The v3.12 tests already pin the eight-code taxonomy and the legacy
flag-source behaviour. These tests cover the v3.13 classifier-output
derivation path:

- sidecar present + sufficient + above threshold → emit
  ``regime_concentrated`` with ``derivation_method="classifier_output"``
- sidecar present + sufficient + below threshold → stay silent
- sidecar present + insufficient evidence → stay silent
- sidecar absent → fall back to legacy flag-source path unchanged
"""

from __future__ import annotations

from research.rejection_taxonomy import derive_taxonomy


def _intelligence_entry(
    candidate_id: str,
    *,
    assessment: str,
    scores: dict[str, float | None],
) -> dict:
    return {
        "entries": [
            {
                "candidate_id": candidate_id,
                "regime_assessment_status": assessment,
                "regime_dependency_scores": scores,
            }
        ]
    }


def _v1_entry_for(candidate_id: str) -> dict:
    return {
        "strategy_name": "sma_crossover",
        "asset": "NVDA",
        "interval": "4h",
        "strategy_id": candidate_id,
        "reasoning": {"failed": [], "escalated": []},
    }


def test_classifier_output_emits_regime_concentrated_above_threshold() -> None:
    entry = _v1_entry_for("cid-1")
    intel = _intelligence_entry(
        "cid-1",
        assessment="sufficient",
        scores={"trend": 0.92, "vol": 0.4, "width": None, "overall": 0.92},
    )
    codes, derivations = derive_taxonomy(
        entry,
        regime_diag=None,
        cost_sens=None,
        regime_intelligence=intel,
    )
    assert "regime_concentrated" in codes
    (d,) = [d for d in derivations if d.taxonomy_code == "regime_concentrated"]
    assert d.derivation_method == "classifier_output"
    assert "regime_dependency_score_trend" in d.observed_sources


def test_classifier_output_silent_below_threshold() -> None:
    entry = _v1_entry_for("cid-2")
    intel = _intelligence_entry(
        "cid-2",
        assessment="sufficient",
        scores={"trend": 0.4, "vol": 0.3, "width": None, "overall": 0.4},
    )
    codes, _ = derive_taxonomy(
        entry,
        regime_diag=None,
        cost_sens=None,
        regime_intelligence=intel,
    )
    assert "regime_concentrated" not in codes


def test_classifier_silent_when_evidence_insufficient_even_if_flag_legacy_true() -> None:
    entry = _v1_entry_for("cid-3")
    intel = _intelligence_entry(
        "cid-3",
        assessment="insufficient_regime_evidence",
        scores={"trend": None, "vol": None, "width": None, "overall": None},
    )
    legacy_flag = {"sma_crossover|NVDA|4h": {"flag": True}}
    codes, _ = derive_taxonomy(
        entry,
        regime_diag=legacy_flag,
        cost_sens=None,
        regime_intelligence=intel,
    )
    # Intelligence sidecar present → overrides legacy path, stays silent
    assert "regime_concentrated" not in codes


def test_legacy_flag_source_path_still_works_when_intelligence_absent() -> None:
    entry = _v1_entry_for("cid-4")
    legacy_flag = {"sma_crossover|NVDA|4h": {"flag": True}}
    codes, derivations = derive_taxonomy(
        entry,
        regime_diag=legacy_flag,
        cost_sens=None,
        regime_intelligence=None,
    )
    assert "regime_concentrated" in codes
    (d,) = [d for d in derivations if d.taxonomy_code == "regime_concentrated"]
    assert d.derivation_method == "flag_source"


def test_classifier_without_matching_candidate_falls_back_to_legacy() -> None:
    entry = _v1_entry_for("cid-5")
    # intelligence exists but carries a different candidate
    intel = _intelligence_entry(
        "other-candidate",
        assessment="sufficient",
        scores={"trend": 0.9, "vol": 0.5, "width": None, "overall": 0.9},
    )
    legacy_flag = {"sma_crossover|NVDA|4h": {"flag": True}}
    codes, derivations = derive_taxonomy(
        entry,
        regime_diag=legacy_flag,
        cost_sens=None,
        regime_intelligence=intel,
    )
    assert "regime_concentrated" in codes
    (d,) = [d for d in derivations if d.taxonomy_code == "regime_concentrated"]
    # candidate not in intelligence → legacy path wins
    assert d.derivation_method == "flag_source"
