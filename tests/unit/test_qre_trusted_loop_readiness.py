from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_closed_loop_operator_report as operator_report
from reporting import qre_hypothesis_candidates as hyp
from reporting import qre_hypothesis_evidence_update as evidence
from reporting import qre_hypothesis_validation_plan as plan
from reporting import qre_hypothesis_validation_results as results
from reporting import qre_market_observation_snapshot as market
from reporting import qre_research_run_manifest as manifest
from reporting import qre_trusted_loop_readiness as readiness
from reporting import qre_validation_research_action_candidates as action


FROZEN = "2026-06-01T12:00:00Z"


def _write_payload(path: Path, report_kind: str, field: str, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": report_kind,
                "generated_at_utc": FROZEN,
                field: rows,
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _artifact_set(tmp_path: Path, *, with_results: bool = True) -> dict[str, Path]:
    paths = {
        "observations": _write_payload(
            tmp_path / "observations.json",
            "qre_market_observation_snapshot",
            "observations",
            [{"observation_id": "qre-obs-fixture-001", "safe_to_execute": False}],
        ),
        "hypotheses": _write_payload(
            tmp_path / "hypotheses.json",
            "qre_hypothesis_candidates",
            "hypotheses",
            [{"hypothesis_id": "qre-hyp-fixture-001", "safe_to_execute": False}],
        ),
        "plans": _write_payload(
            tmp_path / "plans.json",
            "qre_hypothesis_validation_plan",
            "validation_plans",
            [
                {
                    "validation_plan_id": "qre-plan-fixture-001",
                    "hypothesis_id": "qre-hyp-fixture-001",
                    "safe_to_execute": False,
                }
            ],
        ),
        "actions": _write_payload(
            tmp_path / "actions.json",
            "qre_validation_research_action_candidates",
            "action_candidates",
            [
                {
                    "action_id": "qre-action-fixture-001",
                    "target_validation_plan_id": "qre-plan-fixture-001",
                    "safe_to_execute": False,
                }
            ],
        ),
        "run_manifests": _write_payload(
            tmp_path / "run_manifests.json",
            "qre_research_run_manifest",
            "run_manifests",
            [{"run_manifest_id": "qre-run-fixture-001", "safe_to_execute": False}],
        ),
        "results": _write_payload(
            tmp_path / "results.json",
            "qre_hypothesis_validation_results",
            "validation_results",
            [
                {
                    "result_id": "qre-result-fixture-001",
                    "hypothesis_id": "qre-hyp-fixture-001",
                    "source_artifact": "fixture/results.json",
                    "source_report_kind": "fixture",
                    "source_row_id": "result-001",
                    "source_ref": "fixture/results.json#result-001",
                    "safe_to_execute": False,
                }
            ]
            if with_results
            else [],
        ),
        "updates": _write_payload(
            tmp_path / "updates.json",
            "qre_hypothesis_evidence_update",
            "evidence_updates",
            [
                {
                    "evidence_update_id": "qre-evidence-fixture-001",
                    "hypothesis_id": "qre-hyp-fixture-001",
                    "evidence_decision": "supported",
                    "contradicting_evidence_refs": [],
                    "source_artifact": "fixture/results.json",
                    "source_report_kind": "fixture",
                    "source_row_id": "result-001",
                    "source_ref": "fixture/results.json#result-001",
                    "safe_to_execute": False,
                }
            ]
            if with_results
            else [],
        ),
        "operator_report": tmp_path / "operator_report.json",
    }
    paths["operator_report"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "qre_closed_loop_operator_report",
                "operator_report": {
                    "operator_decisions_required": [],
                    "safe_to_execute": False,
                },
                "safe_to_execute": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return paths


def _collect(paths: dict[str, Path], **overrides) -> dict:
    args = {
        "observations_path": paths["observations"],
        "hypotheses_path": paths["hypotheses"],
        "validation_plans_path": paths["plans"],
        "action_candidates_path": paths["actions"],
        "run_manifests_path": paths["run_manifests"],
        "validation_results_path": paths["results"],
        "evidence_updates_path": paths["updates"],
        "operator_report_path": paths["operator_report"],
        "generated_at_utc": FROZEN,
    }
    args.update(overrides)
    return readiness.collect_snapshot(**args)


def _assert_safety_flags_false(snapshot: dict) -> None:
    for key in (
        "safe_to_execute",
        "writes_development_work_queue",
        "writes_seed_jsonl",
        "writes_generated_seed_jsonl",
        "writes_research_action_queue",
        "mutates_campaign_queue",
        "mutates_strategy_or_preset",
        "mutates_paper_shadow_live_runtime",
        "launches_codex",
        "eligible_for_direct_execution",
    ):
        assert snapshot[key] is False


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    paths = {
        key: missing
        for key in (
            "observations",
            "hypotheses",
            "plans",
            "actions",
            "run_manifests",
            "results",
            "updates",
            "operator_report",
        )
    }

    snap = _collect(paths)

    assert snap["readiness_state"] == "scaffold"
    assert snap["blockers"]
    assert snap["operator_report_available"] is False
    _assert_safety_flags_false(snap)


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["results"].write_text(
        json.dumps({"report_kind": "wrong", "validation_results": []}),
        encoding="utf-8",
    )

    snap = _collect(paths)

    assert snap["readiness_state"] == "scaffold"
    assert any("validation_results" in item for item in snap["blockers"])
    _assert_safety_flags_false(snap)


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)

    snap_a = _collect(paths)
    snap_b = _collect(paths)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    assert snap_a["readiness_state"] == "operator_trusted_candidate"
    assert snap_a["evidence_density"]["validation_results"] == 1
    assert snap_a["contradiction_visibility"]["status"] == "visible"
    assert snap_a["source_lineage"]["status"] == "complete"
    assert snap_a["operator_report_available"] is True


def test_working_capability_when_planning_exists_without_results(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path, with_results=False)

    snap = _collect(paths)

    assert snap["readiness_state"] == "working_capability"
    assert "validation_results_or_evidence_updates_absent" in snap["blockers"]


def test_operator_trusted_requires_repeatability_and_approval(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["results"].write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_validation_results",
                "validation_results": [
                    {
                        "result_id": "qre-result-fixture-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "source_artifact": "fixture/results.json",
                        "source_report_kind": "fixture",
                        "source_row_id": "result-001",
                        "source_ref": "fixture/results.json#result-001",
                        "repeatability_evidence_refs": ["fixture#repeatability"],
                        "safe_to_execute": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    paths["operator_report"].write_text(
        json.dumps(
            {
                "report_kind": "qre_closed_loop_operator_report",
                "operator_report": {
                    "operator_approved_for_trusted_loop": True,
                    "safe_to_execute": False,
                },
                "safe_to_execute": False,
            }
        ),
        encoding="utf-8",
    )
    paths["updates"].write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_evidence_update",
                "evidence_updates": [
                    {
                        "evidence_update_id": "qre-evidence-fixture-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "evidence_decision": "supported",
                        "contradicting_evidence_refs": [],
                        "source_artifact": "fixture/results.json",
                        "source_report_kind": "fixture",
                        "source_row_id": "result-001",
                        "source_ref": "fixture/results.json#result-001",
                        "safe_to_execute": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snap = _collect(paths)

    assert snap["readiness_state"] == "operator_trusted"
    assert snap["repeatability_status"] == "operator_approved_repeatability_evidence_present"


def test_evidence_without_source_lineage_is_not_trusted(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["results"].write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_validation_results",
                "validation_results": [
                    {
                        "result_id": "qre-result-fixture-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "safe_to_execute": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    paths["updates"].write_text(
        json.dumps(
            {
                "report_kind": "qre_hypothesis_evidence_update",
                "evidence_updates": [
                    {
                        "evidence_update_id": "qre-evidence-fixture-001",
                        "hypothesis_id": "qre-hyp-fixture-001",
                        "evidence_decision": "supported",
                        "contradicting_evidence_refs": [],
                        "safe_to_execute": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    snap = _collect(paths)

    assert snap["readiness_state"] == "working_capability"
    assert "source_lineage_incomplete" in snap["blockers"]


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        readiness._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = _artifact_set(tmp_path)
    artifact_dir = tmp_path / "logs" / "qre_trusted_loop_readiness"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(readiness, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(readiness, "ARTIFACT_LATEST", latest)

    rc = readiness.main(
        [
            "--no-write",
            "--observations-source",
            str(paths["observations"]),
            "--hypotheses-source",
            str(paths["hypotheses"]),
            "--plans-source",
            str(paths["plans"]),
            "--actions-source",
            str(paths["actions"]),
            "--run-manifests-source",
            str(paths["run_manifests"]),
            "--results-source",
            str(paths["results"]),
            "--evidence-updates-source",
            str(paths["updates"]),
            "--operator-report-source",
            str(paths["operator_report"]),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["readiness_state"] == "operator_trusted_candidate"


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(readiness.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token


def test_source_does_not_write_active_or_mutating_paths() -> None:
    src = Path(readiness.__file__).read_text(encoding="utf-8")
    forbidden = (
        "seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "agent/backtesting/strategies.py",
        "registry.py",
        "paper/",
        "shadow/",
        "live/",
    )
    for token in forbidden:
        assert token not in src, token


def test_integration_synthetic_closed_loop_to_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logs_dir = tmp_path / "logs"
    market_dir = logs_dir / "qre_market_observations"
    hyp_dir = logs_dir / "qre_hypothesis_candidates"
    plan_dir = logs_dir / "qre_hypothesis_validation_plans"
    action_dir = logs_dir / "qre_validation_research_action_candidates"
    manifest_dir = logs_dir / "qre_research_run_manifest"
    result_dir = logs_dir / "qre_hypothesis_validation_results"
    evidence_dir = logs_dir / "qre_hypothesis_evidence_updates"
    report_dir = logs_dir / "qre_closed_loop_operator_report"
    readiness_dir = logs_dir / "qre_trusted_loop_readiness"
    monkeypatch.setattr(market, "ARTIFACT_DIR", market_dir)
    monkeypatch.setattr(market, "ARTIFACT_LATEST", market_dir / "latest.json")
    monkeypatch.setattr(hyp, "ARTIFACT_DIR", hyp_dir)
    monkeypatch.setattr(hyp, "ARTIFACT_LATEST", hyp_dir / "latest.json")
    monkeypatch.setattr(plan, "ARTIFACT_DIR", plan_dir)
    monkeypatch.setattr(plan, "ARTIFACT_LATEST", plan_dir / "latest.json")
    monkeypatch.setattr(action, "ARTIFACT_DIR", action_dir)
    monkeypatch.setattr(action, "ARTIFACT_LATEST", action_dir / "latest.json")
    monkeypatch.setattr(manifest, "ARTIFACT_DIR", manifest_dir)
    monkeypatch.setattr(manifest, "ARTIFACT_LATEST", manifest_dir / "latest.json")
    monkeypatch.setattr(results, "ARTIFACT_DIR", result_dir)
    monkeypatch.setattr(results, "ARTIFACT_LATEST", result_dir / "latest.json")
    monkeypatch.setattr(evidence, "ARTIFACT_DIR", evidence_dir)
    monkeypatch.setattr(evidence, "ARTIFACT_LATEST", evidence_dir / "latest.json")
    monkeypatch.setattr(operator_report, "ARTIFACT_DIR", report_dir)
    monkeypatch.setattr(operator_report, "ARTIFACT_LATEST", report_dir / "latest.json")
    monkeypatch.setattr(readiness, "ARTIFACT_DIR", readiness_dir)
    monkeypatch.setattr(readiness, "ARTIFACT_LATEST", readiness_dir / "latest.json")

    market_source = tmp_path / "synthetic_market_source.json"
    market_source.write_text(
        json.dumps(
            {
                "observations": [
                    {
                        "observation_type": "low_trade_count",
                        "asset_scope": ["BTC-USD"],
                        "timeframe_scope": ["4h"],
                        "regime_tags": ["trend"],
                        "metric_refs": ["total_trades:19"],
                        "summary": "The fold has too few trades for durable validation.",
                        "confidence": 0.8,
                        "supporting_evidence_refs": ["fixture#low-count"],
                        "contradicting_evidence_refs": [],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    market_snap = market.collect_snapshot(
        source_path=market_source,
        generated_at_utc=FROZEN,
    )
    market.write_outputs(market_snap)
    hyp_snap = hyp.collect_snapshot(
        input_artifact_path=market.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    hyp.write_outputs(hyp_snap)
    plan_snap = plan.collect_snapshot(
        input_artifact_path=hyp.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    plan.write_outputs(plan_snap)
    action_snap = action.collect_snapshot(
        input_artifact_path=plan.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    action.write_outputs(action_snap)
    manifest_snap = manifest.collect_snapshot(
        input_artifact_path=action.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    manifest.write_outputs(manifest_snap)

    hypothesis_id = hyp_snap["hypotheses"][0]["hypothesis_id"]
    validation_plan_id = plan_snap["validation_plans"][0]["validation_plan_id"]
    run_manifest_id = manifest_snap["run_manifests"][0]["run_manifest_id"]
    result_source = tmp_path / "synthetic_validation_results.json"
    result_source.write_text(
        json.dumps(
            {
                "validation_results": [
                    {
                        "hypothesis_id": hypothesis_id,
                        "validation_plan_id": validation_plan_id,
                        "run_manifest_id": run_manifest_id,
                        "status": "passed",
                        "metric_results": {"trade_count": 120},
                        "falsification_hits": [],
                        "supporting_evidence_refs": ["fixture#validation-pass"],
                        "contradicting_evidence_refs": [],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result_snap = results.collect_snapshot(
        input_artifact_path=result_source,
        generated_at_utc=FROZEN,
    )
    results.write_outputs(result_snap)
    evidence_snap = evidence.collect_snapshot(
        hypothesis_input_artifact_path=hyp.ARTIFACT_LATEST,
        result_input_artifact_path=results.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    evidence.write_outputs(evidence_snap)
    report_snap = operator_report.collect_snapshot(
        observations_path=market.ARTIFACT_LATEST,
        hypotheses_path=hyp.ARTIFACT_LATEST,
        validation_plans_path=plan.ARTIFACT_LATEST,
        action_candidates_path=action.ARTIFACT_LATEST,
        run_manifests_path=manifest.ARTIFACT_LATEST,
        validation_results_path=results.ARTIFACT_LATEST,
        evidence_updates_path=evidence.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    operator_report.write_outputs(report_snap)
    readiness_snap = readiness.collect_snapshot(
        observations_path=market.ARTIFACT_LATEST,
        hypotheses_path=hyp.ARTIFACT_LATEST,
        validation_plans_path=plan.ARTIFACT_LATEST,
        action_candidates_path=action.ARTIFACT_LATEST,
        run_manifests_path=manifest.ARTIFACT_LATEST,
        validation_results_path=results.ARTIFACT_LATEST,
        evidence_updates_path=evidence.ARTIFACT_LATEST,
        operator_report_path=operator_report.ARTIFACT_LATEST,
        generated_at_utc=FROZEN,
    )
    readiness.write_outputs(readiness_snap)

    for snap in [manifest_snap, result_snap, evidence_snap, report_snap, readiness_snap]:
        _assert_safety_flags_false(snap)
    assert manifest_snap["run_manifests"][0]["safe_to_execute"] is False
    assert result_snap["validation_results"][0]["safe_to_execute"] is False
    assert evidence_snap["evidence_updates"][0]["safe_to_execute"] is False
    assert report_snap["operator_report"]["safe_to_execute"] is False
    assert readiness_snap["readiness_state"] == "working_capability"
    assert readiness_snap["readiness_state"] != "operator_trusted"

    allowed_dirs = {
        "qre_market_observations",
        "qre_hypothesis_candidates",
        "qre_hypothesis_validation_plans",
        "qre_validation_research_action_candidates",
        "qre_research_run_manifest",
        "qre_hypothesis_validation_results",
        "qre_hypothesis_evidence_updates",
        "qre_closed_loop_operator_report",
        "qre_trusted_loop_readiness",
    }
    written = [path for path in logs_dir.rglob("*") if path.is_file()]
    assert {path.parent.name for path in written} <= allowed_dirs
    assert {path.name for path in written} == {"latest.json"}
