from __future__ import annotations

import json
from pathlib import Path

from research import qre_lineage_graph_v1 as lineage_graph


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _source_lifecycle_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "current_state": "candidate",
        "gate_statuses": {
            "allowed_use_declared": True,
            "forbidden_use_declared": True,
            "historical_lineage_present": True,
            "identity_mapping_present": True,
            "manifest_completeness": True,
            "quality_gates_declared": True,
            "quality_gates_passed": True,
        },
        "license_block_reasons": [],
        "license_policy_status": "READY",
        "lifecycle_status": "ready",
        "operator_explanation": "fixture",
        "provider_id": "alpha_vantage_candidate",
        "source_id": "alpha_vantage_candidate_manifest",
        "source_quality_ready": True,
        "transition_targets": {
            "active_read_only": {"allowed": True, "blocking_reasons": []},
            "quality_gated": {"allowed": True, "blocking_reasons": []},
        },
    }
    row.update(overrides)
    return row


def _factor_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "factor_id": "factor_alpha",
        "field_coverage_status": "COVERED",
        "provider_coverage_count": 1,
        "coverage_block_reasons": [],
        "provider_rows": [
            {
                "provider_id": "alpha_vantage_candidate",
                "provider_name": "Alpha Vantage",
                "manifest_status": "VALID",
                "approval_status": "APPROVED_READ_ONLY",
                "freshness_status": "DECLARED",
            }
        ],
    }
    row.update(overrides)
    return row


def _campaign_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "campaign_id": "col-1",
        "hypothesis_id": "hyp-1",
        "state": "completed",
        "outcome": "completed_no_survivor",
        "lineage_root_campaign_id": "col-1",
        "meaningful_classification": "duplicate_low_value_run",
    }
    row.update(overrides)
    return row


def _write_required_fixture_set(
    tmp_path: Path,
    *,
    catalog_hypothesis_id: str = "hyp-1",
    campaign_hypothesis_id: str = "hyp-1",
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_source_lifecycle_quality_gate" / "latest.json",
        {"report_kind": "qre_source_lifecycle_quality_gate", "rows": [_source_lifecycle_row()]},
    )
    _write_json(
        tmp_path / "logs" / "qre_historical_accounting_foundation" / "latest.json",
        {
            "report_kind": "qre_historical_accounting_foundation",
            "rows": [
                {
                    "provider_id": "alpha_vantage_candidate",
                    "source_id": "alpha_vantage_candidate_manifest",
                    "snapshot_contract_status": "READY",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_factor_coverage_matrix" / "latest.json",
        {"report_kind": "qre_factor_coverage_matrix", "factor_rows": [_factor_row()], "rows": [_factor_row()]},
    )
    _write_json(
        tmp_path / "logs" / "qre_grid_candidate_campaign_lineage_bridge" / "latest.json",
        {
            "report_kind": "qre_grid_candidate_campaign_lineage_bridge",
            "rows": [
                {
                    "asset": "AAPL",
                    "basket_id": "seed::AAPL",
                    "campaign_lineage_status": "visible",
                    "candidate_lineage_status": "visible",
                    "exact_next_action": "keep_fail_closed",
                    "join_key_status": "grid_row_match_found",
                    "lineage_bridge_status": "lineage_visible",
                    "matched_grid_rows_count": 1,
                    "operator_explanation": "fixture",
                    "preset": "trend_pullback",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_source_usefulness_ledger" / "latest.json",
        {
            "report_kind": "qre_source_usefulness_ledger",
            "rows": [
                {
                    "source": "alpha_vantage_candidate",
                    "usefulness_state": "useful",
                    "ready_ratio": 1.0,
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "report_kind": "qre_data_source_quality_readiness",
            "rows": [
                {
                    "source": "alpha_vantage_candidate",
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "quality_status": "ready",
                    "manifest_status": "ready",
                    "identity_confidence": "high",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "research" / "strategy_hypothesis_catalog_latest.v1.json",
        {
            "report_kind": "strategy_hypothesis_catalog",
            "hypotheses": [
                {
                    "hypothesis_id": catalog_hypothesis_id,
                    "status": "active_discovery",
                    "strategy_family": "trend_pullback",
                    "feature_dependencies": ["ema_fast", "ema_slow"],
                    "baseline_reference": "ema_trend_baseline",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "report_kind": "campaign_registry",
            "campaigns": {
                "col-1": _campaign_row(hypothesis_id=campaign_hypothesis_id),
            },
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_digest_latest.v1.json",
        {
            "report_kind": "campaign_digest",
            "compute_by_lineage_root": {
                "col-1": {"actual_compute_seconds": 10, "children_count": 1, "meaningful_classifications": ["duplicate_low_value_run"]}
            },
        },
    )


def test_lineage_graph_builds_complete_read_only_graph(tmp_path: Path) -> None:
    _write_required_fixture_set(tmp_path)
    report = lineage_graph.build_qre_lineage_graph_v1(repo_root=tmp_path)
    summary = report["summary"]
    checks = report["checks"]
    assert summary["graph_status"] == "ready"
    assert summary["source_count"] == 1
    assert summary["normalized_data_count"] == 1
    assert summary["factor_count"] == 1
    assert summary["hypothesis_count"] == 1
    assert summary["campaign_count"] == 1
    assert summary["evidence_count"] >= 8
    assert checks["missing_reports"] == []
    assert checks["orphan_nodes"] == []
    assert checks["contradictions"] == []
    node_types = {str(node["node_type"]) for node in report["nodes"]}
    assert {"source", "normalized_data", "factor", "hypothesis", "campaign", "evidence"} <= node_types


def test_lineage_graph_flags_missing_hypothesis_as_contradiction(tmp_path: Path) -> None:
    _write_required_fixture_set(tmp_path, catalog_hypothesis_id="hyp-1", campaign_hypothesis_id="missing_hypothesis")
    report = lineage_graph.build_qre_lineage_graph_v1(repo_root=tmp_path)
    checks = report["checks"]
    assert report["summary"]["graph_status"] == "blocked"
    assert any(row["kind"] == "missing_hypothesis_reference" for row in checks["contradictions"])
    assert any(row["lineage_layer"] == "hypothesis" for row in checks["orphan_nodes"])


def test_lineage_graph_blocks_when_required_report_missing(tmp_path: Path) -> None:
    _write_required_fixture_set(tmp_path)
    missing = tmp_path / "research" / "campaign_digest_latest.v1.json"
    missing.unlink()
    report = lineage_graph.build_qre_lineage_graph_v1(repo_root=tmp_path)
    assert report["summary"]["graph_status"] == "blocked"
    assert "research/campaign_digest_latest.v1.json" in report["checks"]["missing_reports"]


def test_lineage_graph_writes_outputs(tmp_path: Path) -> None:
    _write_required_fixture_set(tmp_path)
    report = lineage_graph.build_qre_lineage_graph_v1(repo_root=tmp_path)
    paths = lineage_graph.write_outputs(report, repo_root=tmp_path)
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_lineage_graph_v1/latest.json"
    assert "# QRE Lineage Graph v1" in summary
