from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import bounded_strategy_synthesis as bss
from packages.qre_research import generated_hypothesis_paths as ghp
from packages.qre_research import generated_strategy_paths as gsp
from packages.qre_research import hypothesis_lifecycle as qhl


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_generated_hypothesis_trusted_loop_flows_into_fail_closed_synthesis_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ghp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gsp, "REPO_ROOT", tmp_path)

    registry_path = (
        tmp_path
        / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json"
    )
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_kind": "qre_generated_thesis_registry",
                "rows": [
                    {
                        "thesis_id": "qht_fixture",
                        "source_hypothesis_id": "atr_adaptive_trend_v0",
                        "lifecycle_state": "HYPOTHESIS_ADMITTED_AUTOMATED",
                        "primitive_compatibility": "COMPILABLE_WITH_CURRENT_PRIMITIVES",
                        "mechanism_class": "trend_persistence",
                        "behavior_family": "trend",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    candidate_index = {
        "qht_fixture": {
            "thesis_id": "qht_fixture",
            "source_hypothesis_id": "atr_adaptive_trend_v0",
            "behavior_id": "trend",
            "timeframe": "4h",
            "required_data": ["ohlcv"],
            "falsification_criteria": ["null_model_not_beaten"],
            "entry_relevant_observations": ["trend_anchor_delta_positive"],
            "strongest_supporting_evidence": ["reason_record_fixture"],
            "strongest_contradicting_evidence": [],
            "testability_state": "READY",
            "novelty_outcome": "NOVEL_WITH_OVERLAP",
            "known_risks": ["empirical_evidence_incomplete"],
        }
    }
    monkeypatch.setattr(qhl, "_candidate_index", lambda repo_root: candidate_index)
    monkeypatch.setattr(
        qhl,
        "_candidate_index_by_source",
        lambda repo_root: {
            "atr_adaptive_trend_v0": candidate_index["qht_fixture"],
        },
    )
    monkeypatch.setattr(bss, "_candidate_index", lambda repo_root: candidate_index)
    monkeypatch.setattr(
        qhl,
        "_identity_index",
        lambda repo_root: {
            "atr_adaptive_trend_v0": {
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "resolution_state": "RESOLVED",
            }
        },
    )
    monkeypatch.setattr(qhl, "_source_quality_index", lambda repo_root: {})

    _write_json(
        tmp_path / "generated_research/registry/generated_strategy_registry.v1.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_generated_strategy_registry",
            "rows": [
                {
                    "generated_strategy_id": "qgs_fixture",
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                    "strategy_spec_id": "qss_fixture",
                    "state": "STRATEGY_SPEC_MATERIALIZED_FIXTURE",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "generated_research/specs/qss_fixture.json",
        {
            "schema_version": "1.0",
            "strategy_spec_id": "qss_fixture",
            "source_hypothesis_id": "atr_adaptive_trend_v0",
            "required_feature_primitives": [],
            "expected_behavior": "trend_anchor_delta_positive",
            "expected_failure_modes": ["null_model_not_beaten"],
            "fixture_only": True,
        },
    )
    _write_json(
        tmp_path / "generated_research/readiness/data_bindings/autonomous_strategy_data_bindings.v1.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_strategy_data_binding_readiness",
            "rows": [
                {
                    "generated_strategy_id": "qgs_fixture",
                    "outcome": "DATA_BINDING_READY",
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                    "fixture_only": True,
                }
            ],
        },
    )
    _write_json(
        tmp_path / "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_universe_authority_readiness",
            "rows": [
                {
                    "generated_strategy_id": "qgs_fixture",
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                    "decision": "IDENTITY_READY_FIXTURE_ONLY",
                    "fixture_only": True,
                }
            ],
        },
    )
    _write_json(
        tmp_path / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_portfolio_readiness",
            "rows": [
                {
                    "generated_strategy_id": "qgs_fixture",
                    "source_hypothesis_id": "atr_adaptive_trend_v0",
                    "status": "READY_FOR_PREREGISTRATION",
                    "timeframe": "4h",
                    "train_window": {"start": "2024-01-01", "end": "2024-06-30"},
                    "validation_window": {"start": "2024-07-01", "end": "2024-09-30"},
                    "oos_window": {"start": "2024-10-01", "end": "2024-12-31"},
                    "blockers": [],
                    "next_action": "evaluate_exact_blocker_or_empirical_campaign_gap",
                    "fixture_only": True,
                }
            ],
        },
    )

    trusted_loop = qhl.run_trusted_hypothesis_loop(
        repo_root=tmp_path,
        write_outputs=True,
    )
    readiness = bss.materialize_synthesis_readiness(
        repo_root=tmp_path,
        write_outputs=True,
    )
    synthesis = bss.run_bounded_strategy_synthesis(
        repo_root=tmp_path,
        write_outputs=True,
    )

    assert trusted_loop["selected_hypotheses"] == 1
    assert trusted_loop["feasibility_ready_count"] == 1
    assert trusted_loop["routing_ready_count"] == 1
    assert trusted_loop["sampling_ready_count"] == 1
    assert trusted_loop["campaigns_admitted"] == 0
    assert readiness["readiness_status"] == "INELIGIBLE_EVIDENCE"
    assert "oos_evidence" in readiness["missing_evidence"]
    assert synthesis["status"] == "BLOCKED_BY_READINESS"
    assert synthesis["research_only_candidate_created"] is False


def test_lifecycle_fixture_reports_blockers_when_canonical_prerequisites_are_absent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(ghp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gsp, "REPO_ROOT", tmp_path)

    _write_json(
        tmp_path / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_generated_thesis_registry",
            "rows": [
                {
                    "thesis_id": "qht_blocked_fixture",
                    "source_hypothesis_id": "blocked_source_v0",
                    "lifecycle_state": "HYPOTHESIS_ADMITTED_AUTOMATED",
                    "primitive_compatibility": "COMPILABLE_WITH_CURRENT_PRIMITIVES",
                    "mechanism_class": "trend_persistence",
                    "behavior_family": "trend",
                }
            ],
        },
    )
    monkeypatch.setattr(qhl, "_candidate_index_by_source", lambda repo_root: {})
    monkeypatch.setattr(qhl, "_identity_index", lambda repo_root: {})
    monkeypatch.setattr(qhl, "_source_quality_index", lambda repo_root: {})

    snapshot = qhl.build_feasibility_snapshot(repo_root=tmp_path)

    row = snapshot["rows"][0]
    assert row["status"] == "blocked"
    assert row["missing_prerequisites"] == [
        "generated_strategy_missing",
        "identity_unresolved",
        "data_binding_not_ready",
        "missing_falsification_criteria",
        "missing_expected_observables",
    ]
