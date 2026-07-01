from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import bounded_strategy_synthesis as bss
from packages.qre_research import generated_strategy_paths as gsp


def test_materialize_synthesis_readiness_writes_fail_closed_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gsp, "REPO_ROOT", tmp_path)

    def _artifacts(*, root: Path = Path(".")):
        assert root == tmp_path
        return (
            {
                "feasibility": {"rows": []},
                "routing": {"rows": []},
                "sampling": {"rows": []},
                "reason_records": {"rows": []},
                "evidence_updates": {"rows": []},
                "failure_actions": {"rows": []},
                "research_memory": {"rows": []},
                "trusted_loop_summary": {
                    "empirical_research_evidence_materialized": False
                },
            },
            {
                name: {"path": path.as_posix(), "status": "missing"}
                for name, path in bss.sg.GENERATED_HYPOTHESIS_ARTIFACT_PATHS.items()
            },
        )

    monkeypatch.setattr(bss.sg, "load_generated_hypothesis_artifacts", _artifacts)

    payload = bss.materialize_synthesis_readiness(
        repo_root=tmp_path,
        write_outputs=True,
    )

    path = tmp_path / bss.readiness_artifact_path()
    assert path.is_file()
    written = json.loads(path.read_text(encoding="utf-8"))
    assert payload == written
    assert written["readiness_status"] == "INELIGIBLE_EVIDENCE"


def test_bounded_synthesis_refuses_ineligible_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gsp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        bss,
        "materialize_synthesis_readiness",
        lambda repo_root, write_outputs: {
            "readiness_status": "INELIGIBLE_EVIDENCE",
            "hypothesis_id": "qht_blocked",
            "blocking_reasons": ["empirical_research_evidence_incomplete"],
            "recommended_next_actions": ["materialize_oos_and_cost_evidence"],
        },
    )

    result = bss.run_bounded_strategy_synthesis(
        repo_root=tmp_path,
        write_outputs=True,
    )

    assert result["status"] == "BLOCKED_BY_READINESS"
    assert result["blueprint_created"] is False
    assert result["research_only_candidate_created"] is False


def test_bounded_synthesis_materializes_disabled_research_only_candidate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gsp, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        bss,
        "materialize_synthesis_readiness",
        lambda repo_root, write_outputs: {
            "readiness_status": "ELIGIBLE",
            "hypothesis_id": "qht_ready",
            "criteria_passed": ["hypothesis_exists", "routing_ready", "sampling_ready"],
            "criteria_failed": [],
            "missing_evidence": [],
        },
    )
    monkeypatch.setattr(
        bss,
        "_generated_hypothesis_rows",
        lambda repo_root: {
            "qht_ready": {
                "thesis_id": "qht_ready",
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "behavior_family": "trend",
                "mechanism_class": "trend_persistence",
            }
        },
    )
    monkeypatch.setattr(
        bss,
        "_candidate_index",
        lambda repo_root: {
            "qht_ready": {
                "behavior_id": "trend",
                "timeframe": "4h",
                "required_data": ["ohlcv"],
                "falsification_criteria": ["null_model_not_beaten"],
                "entry_relevant_observations": ["trend_anchor_delta_positive"],
                "known_risks": ["empirical_evidence_incomplete"],
            }
        },
    )

    result = bss.run_bounded_strategy_synthesis(
        repo_root=tmp_path,
        write_outputs=True,
    )

    assert result["status"] == "SYNTHESIS_READY_FOR_RESEARCH_VALIDATION"
    assert result["blueprint_created"] is True
    assert result["research_only_candidate_created"] is True
    assert result["promotion_proposal_created"] is True

    blueprint_path = tmp_path / Path(result["artifact_paths"]["blueprint"])
    candidate_path = tmp_path / Path(result["artifact_paths"]["candidate"])
    proposal_path = tmp_path / Path(result["artifact_paths"]["proposal"])
    assert blueprint_path.is_file()
    assert candidate_path.is_file()
    assert proposal_path.is_file()

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    assert candidate["enabled"] is False
    assert candidate["bundle_active"] is False
    assert candidate["active_discovery"] is False
    assert candidate["paper_ready"] is False
    assert candidate["shadow_ready"] is False
    assert candidate["live_eligible"] is False
    assert len(candidate["parameter_definitions"]) <= bss.MAX_TUNABLE_PARAMETERS
