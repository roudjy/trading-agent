from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_blocked_thesis_lineage_census as census
from reporting import qre_campaign_lineage_materialization as materialization
from reporting import qre_identity_ambiguity_resolution as identity
from reporting import qre_null_control_readiness as controls


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_lineage_identity_and_controls_fail_closed_and_deterministic(tmp_path: Path) -> None:
    registry = {
        "rows": [
            {
                "thesis_id": "qbt_vol",
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "behavior_family": "volatility_compression_breakout",
                "mechanism": "compressed range breaks into expansion",
                "universe": "existing_preset_bound_universes_only",
                "null_controls": ["shuffle_returns"],
                "provenance_refs": ["registry:vol"],
            },
            {
                "thesis_id": "qbt_atr",
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "behavior_family": "trend_continuation",
                "mechanism": "atr adaptive trend filter",
                "universe": "blocked:campaign_scope_pending_registry_maturation",
                "null_controls": ["blocked:null_controls:behavior_not_research_ready"],
                "provenance_refs": ["registry:atr"],
            },
        ]
    }
    lineage_payload = {
        "rows": [
            {
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "missing_lineage_fields": ["campaign_identity", "source_identity"],
                "graph_nodes": {"campaign": []},
                "supporting_evidence_refs": ["evidence:vol"],
                "contradicting_evidence_refs": [],
                "provenance_refs": ["lineage:vol"],
            },
            {
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "missing_lineage_fields": ["campaign_identity"],
                "graph_nodes": {"campaign": []},
                "supporting_evidence_refs": [],
                "contradicting_evidence_refs": [],
                "provenance_refs": ["lineage:atr"],
            },
        ]
    }
    operator = {
        "rows": [
            {
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "final_decision": "BLOCKED",
                "primary_reasons": ["missing campaign lineage"],
                "null_controls": {"status": "controls_incomplete", "missing_control_ids": ["null_holdout"]},
                "provenance_refs": ["operator:vol"],
            },
            {
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "final_decision": "BLOCKED",
                "primary_reasons": ["missing bounded campaign metadata"],
                "null_controls": {"status": "controls_incomplete", "missing_control_ids": []},
                "provenance_refs": ["operator:atr"],
            },
        ]
    }
    identity_payload = {
        "rows": [
            {
                "behavior_id": "volatility_compression_breakout",
                "resolution_status": "VERIFIED",
                "authority_status": "blocked_identity_inventory_missing",
                "provider_symbol": "SPY",
                "symbol": "SPY",
                "instrument_identity_status": "missing",
                "source_quality_status": "ready",
                "provenance": ["identity:vol"],
            }
        ]
    }
    cache_payload = {"coverage": [{"instrument": "SPY", "timeframe": "4h", "ready": True}]}
    metadata = {
        "hypotheses": {
            "volatility_compression_breakout_v0": {"eligible_campaign_types": ["daily_primary"]},
            "atr_adaptive_trend_v0": {"eligible_campaign_types": []},
        }
    }
    templates = {
        "templates": [
            {
                "template_id": "daily_primary__vol_compression_breakout_crypto_4h",
                "preset_name": "vol_compression_breakout_crypto_4h",
                "campaign_type": "daily_primary",
            }
        ]
    }
    presets_source = """
PRESETS = (
    ResearchPreset(name="vol_compression_breakout_crypto_4h", universe=("BTC-USD",), timeframe="4h", hypothesis_id="volatility_compression_breakout_v0", enabled=True, status="stable"),
)
"""
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research" / "presets.py").write_text(presets_source, encoding="utf-8")
    census_snapshot = census.collect_snapshot(
        repo_root=tmp_path,
        registry_path=_write_json(tmp_path / "registry.json", registry),
        lineage_path=_write_json(tmp_path / "lineage.json", lineage_payload),
        operator_path=_write_json(tmp_path / "operator.json", operator),
        identity_path=_write_json(tmp_path / "identity.json", identity_payload),
        cache_path=_write_json(tmp_path / "cache.json", cache_payload),
        campaign_metadata_path=_write_json(tmp_path / "metadata.json", metadata),
        templates_path=_write_json(tmp_path / "templates.json", templates),
        presets_path=Path("research/presets.py"),
    )
    assert census_snapshot["summary"]["thesis_count"] == 2
    by_hypothesis = {row["source_hypothesis_id"]: row for row in census_snapshot["rows"]}
    assert by_hypothesis["volatility_compression_breakout_v0"]["lineage_status"] == "IDENTITY_BLOCKED"
    assert by_hypothesis["atr_adaptive_trend_v0"]["lineage_status"] == "IMPLEMENTATION_MISSING"
    identity_snapshot = identity.collect_snapshot(
        repo_root=tmp_path,
        census_path=_write_json(tmp_path / "census.json", census_snapshot),
        identity_path=_write_json(tmp_path / "identity_latest.json", identity_payload),
    )
    identity_rows = {row["source_hypothesis_id"]: row for row in identity_snapshot["rows"]}
    assert identity_rows["volatility_compression_breakout_v0"]["resolution_state"] == "BLOCKED"
    assert identity_rows["atr_adaptive_trend_v0"]["resolution_state"] == "MISSING"
    materialization_snapshot = materialization.collect_snapshot(
        repo_root=tmp_path,
        census_path=_write_json(tmp_path / "census_latest.json", census_snapshot),
        identity_path=_write_json(tmp_path / "identity_resolved.json", identity_snapshot),
    )
    materialization_rows = {row["source_hypothesis_id"]: row for row in materialization_snapshot["rows"]}
    assert materialization_rows["volatility_compression_breakout_v0"]["materialization_state"] == "IDENTITY_BLOCKED"
    assert materialization_rows["atr_adaptive_trend_v0"]["materialization_state"] == "IMPLEMENTATION_MISSING"
    controls_snapshot = controls.collect_snapshot(
        repo_root=tmp_path,
        lineage_path=_write_json(tmp_path / "materialization.json", materialization_snapshot),
        registry_path=_write_json(tmp_path / "registry_latest.json", registry),
        operator_path=_write_json(tmp_path / "operator_latest.json", operator),
    )
    controls_rows = {row["source_hypothesis_id"]: row for row in controls_snapshot["rows"]}
    assert controls_rows["volatility_compression_breakout_v0"]["completeness_state"] == "IMPLEMENTATION_MISSING"
    assert controls_rows["atr_adaptive_trend_v0"]["completeness_state"] == "IMPLEMENTATION_MISSING"
    repeat = census.collect_snapshot(
        repo_root=tmp_path,
        registry_path=Path("registry.json"),
        lineage_path=Path("lineage.json"),
        operator_path=Path("operator.json"),
        identity_path=Path("identity.json"),
        cache_path=Path("cache.json"),
        campaign_metadata_path=Path("metadata.json"),
        templates_path=Path("templates.json"),
        presets_path=Path("research/presets.py"),
    )
    assert repeat["lineage_census_identity"] == census_snapshot["lineage_census_identity"]
