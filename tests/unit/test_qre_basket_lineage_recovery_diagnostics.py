from __future__ import annotations

import json
from pathlib import Path

from research import qre_basket_lineage_recovery_diagnostics as lineage_diag


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_lineage_diagnostics_distinguish_proven_lineage_from_gaps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        lineage_diag.density,
        "build_basket_evidence_density_materialization",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "behavior_family": "trend_pullback",
                    "region": "US",
                    "asset_class": "equity",
                    "timeframes": ["4h"],
                    "candidate_lineage_rows": 1,
                    "campaign_lineage_rows": 1,
                    "candidate_lineage_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json#AAPL|preset-a"],
                    "campaign_lineage_refs": ["logs/qre_grid_candidate_campaign_lineage_bridge/latest.json#AAPL|preset-a"],
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "preset_id": "preset-b",
                    "hypothesis_id": "hyp-b",
                    "behavior_family": "trend_pullback",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "timeframes": ["1d"],
                    "candidate_lineage_rows": 0,
                    "campaign_lineage_rows": 0,
                    "candidate_lineage_refs": [],
                    "campaign_lineage_refs": [],
                },
            ]
        },
    )
    monkeypatch.setattr(
        lineage_diag.lineage_bridge,
        "build_grid_candidate_campaign_lineage_bridge",
        lambda **_: {
            "rows": [
                {"asset": "AAPL", "preset": "preset-a", "lineage_bridge_status": "lineage_visible", "exact_next_action": "keep_fail_closed"},
                {"asset": "ASMI", "preset": "preset-b", "lineage_bridge_status": "blocked_no_grid_match", "exact_next_action": "restore_or_run_grid_artifacts"},
            ]
        },
    )

    report = lineage_diag.build_basket_lineage_recovery_diagnostics(repo_root=tmp_path, max_candidates=2)

    assert report["summary"]["basket_count"] == 2
    assert report["summary"]["candidate_lineage_proven_count"] == 1
    assert report["summary"]["campaign_lineage_proven_count"] == 1
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["AAPL"]["candidate_lineage_proof_status"] == "lineage_visible"
    assert rows["AAPL"]["campaign_lineage_proof_status"] == "proven"
    assert rows["ASMI"]["candidate_lineage_proof_status"] == "artifact_missing"
    assert rows["ASMI"]["exact_next_action"] == "restore_or_run_grid_artifacts"


def test_lineage_diagnostics_write_outputs_stays_allowlisted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        lineage_diag.density,
        "build_basket_evidence_density_materialization",
        lambda **_: {"rows": []},
    )
    monkeypatch.setattr(
        lineage_diag.lineage_bridge,
        "build_grid_candidate_campaign_lineage_bridge",
        lambda **_: {"rows": []},
    )

    report = lineage_diag.build_basket_lineage_recovery_diagnostics(repo_root=tmp_path, max_candidates=1)
    paths = lineage_diag.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_basket_lineage_recovery_diagnostics/latest.json"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
