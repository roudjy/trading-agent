from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_closed_loop_operator_report as report


FROZEN = "2026-06-01T12:00:00Z"


def _write_payload(path: Path, report_kind: str, field: str, rows: list[dict]) -> Path:
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


def _artifact_set(tmp_path: Path) -> dict[str, Path]:
    paths = {
        "observations": _write_payload(
            tmp_path / "observations.json",
            "qre_market_observation_snapshot",
            "observations",
            [
                {
                    "observation_id": "qre-obs-fixture-001",
                    "safe_to_execute": False,
                }
            ],
        ),
        "hypotheses": _write_payload(
            tmp_path / "hypotheses.json",
            "qre_hypothesis_candidates",
            "hypotheses",
            [
                {
                    "hypothesis_id": "qre-hyp-fixture-001",
                    "status": "proposed",
                    "safe_to_execute": False,
                }
            ],
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
            [
                {
                    "run_manifest_id": "qre-run-fixture-001",
                    "source_action_id": "qre-action-fixture-001",
                    "status": "operator_review_required",
                    "safe_to_execute": False,
                }
            ],
        ),
        "results": _write_payload(
            tmp_path / "results.json",
            "qre_hypothesis_validation_results",
            "validation_results",
            [
                {
                    "result_id": "qre-result-fixture-001",
                    "hypothesis_id": "qre-hyp-fixture-001",
                    "safe_to_execute": False,
                }
            ],
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
                    "safe_to_execute": False,
                }
            ],
        ),
    }
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
        "generated_at_utc": FROZEN,
    }
    args.update(overrides)
    return report.collect_snapshot(**args)


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
        )
    }

    snap = _collect(paths)

    assert snap["operator_report"]["safe_to_execute"] is False
    assert snap["operator_report"]["active_hypotheses"] == []
    assert snap["validation_warnings"]
    _assert_safety_flags_false(snap)


def test_malformed_input_fails_closed(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["hypotheses"].write_text(
        json.dumps({"report_kind": "wrong", "hypotheses": []}),
        encoding="utf-8",
    )

    snap = _collect(paths)

    assert "hypotheses:missing_or_unparseable" in snap["validation_warnings"]
    assert snap["operator_report"]["final_recommendation"] == "operator_review_required"
    _assert_safety_flags_false(snap)


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)

    snap_a = _collect(paths)
    snap_b = _collect(paths)

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)
    op = snap_a["operator_report"]
    assert op["active_hypotheses"][0]["hypothesis_id"] == "qre-hyp-fixture-001"
    assert op["pending_run_manifests"][0]["run_manifest_id"] == "qre-run-fixture-001"
    assert op["validation_results"][0]["result_id"] == "qre-result-fixture-001"
    assert op["evidence_updates"][0]["evidence_decision"] == "supported"
    assert "approve_or_reject_pending_run_manifests" in op["operator_decisions_required"]
    assert op["top_supported_hypotheses"][0]["hypothesis_id"] == "qre-hyp-fixture-001"
    assert op["top_falsified_hypotheses"] == []
    assert op["needs_more_data_hypotheses"] == []
    assert op["contradiction_hypotheses"] == []
    assert op["missing_validation_results"] == []
    assert op["why_auto_execution_is_forbidden"]
    assert op["next_manual_actions"] == ["review_evidence_lineage_before_any_follow_up"]


def test_operator_report_buckets_all_evidence_decisions(tmp_path: Path) -> None:
    paths = _artifact_set(tmp_path)
    paths["hypotheses"] = _write_payload(
        tmp_path / "hypotheses_multi.json",
        "qre_hypothesis_candidates",
        "hypotheses",
        [
            {"hypothesis_id": "hyp-supported", "title": "Supported"},
            {"hypothesis_id": "hyp-falsified", "title": "Falsified"},
            {"hypothesis_id": "hyp-more", "title": "Needs more"},
            {"hypothesis_id": "hyp-contradiction", "title": "Contradiction"},
            {"hypothesis_id": "hyp-missing", "title": "Missing"},
        ],
    )
    paths["plans"] = _write_payload(
        tmp_path / "plans_multi.json",
        "qre_hypothesis_validation_plan",
        "validation_plans",
        [
            {"validation_plan_id": f"plan-{idx}", "hypothesis_id": hypothesis_id}
            for idx, hypothesis_id in enumerate(
                [
                    "hyp-supported",
                    "hyp-falsified",
                    "hyp-more",
                    "hyp-contradiction",
                    "hyp-missing",
                ]
            )
        ],
    )
    paths["results"] = _write_payload(
        tmp_path / "results_multi.json",
        "qre_hypothesis_validation_results",
        "validation_results",
        [
            {"result_id": "result-supported", "hypothesis_id": "hyp-supported"},
            {"result_id": "result-falsified", "hypothesis_id": "hyp-falsified"},
            {"result_id": "result-more", "hypothesis_id": "hyp-more"},
            {"result_id": "result-contradiction", "hypothesis_id": "hyp-contradiction"},
        ],
    )
    paths["updates"] = _write_payload(
        tmp_path / "updates_multi.json",
        "qre_hypothesis_evidence_update",
        "evidence_updates",
        [
            {
                "evidence_update_id": "update-supported",
                "hypothesis_id": "hyp-supported",
                "evidence_decision": "supported",
                "supporting_evidence_refs": ["source#supported"],
                "contradicting_evidence_refs": [],
            },
            {
                "evidence_update_id": "update-falsified",
                "hypothesis_id": "hyp-falsified",
                "evidence_decision": "falsified",
                "supporting_evidence_refs": [],
                "contradicting_evidence_refs": ["source#falsified"],
            },
            {
                "evidence_update_id": "update-more",
                "hypothesis_id": "hyp-more",
                "evidence_decision": "needs_more_data",
                "supporting_evidence_refs": [],
                "contradicting_evidence_refs": [],
            },
            {
                "evidence_update_id": "update-contradiction",
                "hypothesis_id": "hyp-contradiction",
                "evidence_decision": "contradiction_detected",
                "supporting_evidence_refs": ["source#support"],
                "contradicting_evidence_refs": ["source#contradiction"],
            },
        ],
    )

    snap = _collect(paths)
    op = snap["operator_report"]

    assert [row["hypothesis_id"] for row in op["top_supported_hypotheses"]] == ["hyp-supported"]
    assert [row["hypothesis_id"] for row in op["top_falsified_hypotheses"]] == ["hyp-falsified"]
    assert [row["hypothesis_id"] for row in op["needs_more_data_hypotheses"]] == ["hyp-more"]
    assert [row["hypothesis_id"] for row in op["contradiction_hypotheses"]] == ["hyp-contradiction"]
    assert [row["hypothesis_id"] for row in op["missing_validation_results"]] == ["hyp-missing"]
    assert "provide_or_accept_missing_validation_results" in op["operator_decisions_required"]


def test_atomic_write_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        report._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    paths = _artifact_set(tmp_path)
    artifact_dir = tmp_path / "logs" / "qre_closed_loop_operator_report"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(report, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(report, "ARTIFACT_LATEST", latest)

    rc = report.main(
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
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["operator_report"]["safe_to_execute"] is False


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(report.__file__).read_text(encoding="utf-8")
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
    src = Path(report.__file__).read_text(encoding="utf-8")
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
