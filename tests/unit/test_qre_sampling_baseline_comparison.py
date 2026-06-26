from __future__ import annotations

import ast
import json
from pathlib import Path

from reporting import qre_sampling_baseline_comparison as comparison


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_sampling_readiness_from_basket" / "latest.json",
        {
            "rows": [
                {
                    "candidate_id": "cand_b",
                    "behavior_family": "post_shock_stabilization",
                    "sampling_readiness_state": "ready",
                    "sampling_readiness_score_pct": 92,
                    "routing_readiness_score_pct": 81,
                    "timeframes": ["1d", "1w"],
                    "evidence_presence": {"oos_evidence_known": True},
                    "validation_evidence_status_counts": {"sufficient_oos_evidence": 1},
                },
                {
                    "candidate_id": "cand_a",
                    "behavior_family": "index_regime_filter",
                    "sampling_readiness_state": "blocked",
                    "sampling_readiness_score_pct": 40,
                    "routing_readiness_score_pct": 78,
                    "timeframes": ["1d"],
                    "evidence_presence": {"oos_evidence_known": False},
                    "validation_evidence_status_counts": {"insufficient_oos_trades": 1},
                },
                {
                    "candidate_id": "cand_c",
                    "behavior_family": "relative_strength",
                    "sampling_readiness_state": "ready",
                    "sampling_readiness_score_pct": 80,
                    "routing_readiness_score_pct": 65,
                    "timeframes": ["1d", "4h", "1w"],
                    "evidence_presence": {"oos_evidence_known": True},
                    "validation_evidence_status_counts": {"sufficient_oos_evidence": 1},
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_routing_sampling_readiness" / "latest.json",
        {
            "candidate_examples_top": [
                {
                    "candidate_id": "cand_b",
                    "routing_score_pct": 81,
                    "shared_ready": True,
                    "sampling_reason_record_present": True,
                },
                {
                    "candidate_id": "cand_a",
                    "routing_score_pct": 78,
                    "shared_ready": False,
                    "sampling_reason_record_present": True,
                },
                {
                    "candidate_id": "cand_c",
                    "routing_score_pct": 65,
                    "shared_ready": True,
                    "sampling_reason_record_present": False,
                },
            ]
        },
    )


def test_build_is_deterministic_and_current_sampling_beats_routing_order(tmp_path: Path) -> None:
    _seed(tmp_path)
    left = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)
    right = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_sampling_baseline_comparison"
    assert left["summary"]["best_baseline_id"] == "current_sampling_score"
    assert left["summary"]["current_minus_routing_order"] >= 0


def test_baseline_vocab_and_source_status_are_closed(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)

    assert report["source_status"]["sampling_readiness_from_basket"]["status"] == "ready"
    assert report["source_status"]["routing_sampling_readiness"]["status"] == "ready"
    assert [row["baseline_id"] for row in report["baselines"]] == sorted(
        [row["baseline_id"] for row in report["baselines"]],
        key=lambda baseline_id: -next(
            row["decision_usefulness_score"]
            for row in report["baselines"]
            if row["baseline_id"] == baseline_id
        ),
    )


def test_missing_joined_surface_fails_closed(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "logs" / "qre_routing_sampling_readiness" / "latest.json").unlink()

    report = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)

    assert report["source_status"]["routing_sampling_readiness"]["status"] == "missing"
    assert all(row["shared_ready"] is False for row in report["candidate_rows"])


def test_candidate_rows_keep_provenance_and_useful_proxies(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)

    row = report["candidate_rows"][0]
    assert row["sampling_state"] in comparison.STATE_VALUES
    assert row["provenance_refs"]
    assert 0.0 <= row["decision_usefulness_proxy"] <= 1.0
    assert 0.0 <= row["signal_density_proxy"] <= 1.0
    assert 0.0 <= row["compute_efficiency_proxy"] <= 1.0


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_sampling_baseline_comparison(repo_root=tmp_path)

    paths = comparison.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_sampling_baseline_comparison/latest.json",
        "doc": "docs/governance/qre_sampling_baseline_comparison.md",
    }
    assert "QRE Sampling Baseline Comparison" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert comparison.read_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_sampling_baseline_comparison/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(comparison.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "research/research_latest.json" not in source
    assert "research/strategy_matrix.csv" not in source
    assert "\"can_launch_campaign\": False" in source
