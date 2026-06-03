from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_operator_closed_loop_report as report

FROZEN = "2026-06-01T12:00:00Z"


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fixtures(
    tmp_path: Path,
    *,
    identity_blocked: bool = False,
    audit_status: str = "promotion_ready_for_operator_review",
) -> dict[str, Path]:
    ready = 0 if identity_blocked else 1
    return {
        "observations": _write(
            tmp_path / "observations.json",
            {
                "report_kind": "qre_market_observation_snapshot",
                "observations": [{"observation_id": "qre-obs-1"}],
                "counts": {"total": 1},
                "safe_to_execute": False,
            },
        ),
        "readiness": _write(
            tmp_path / "readiness.json",
            {
                "report_kind": "qre_market_observation_hypothesis_readiness",
                "counts": {"hypothesis_ready": ready, "not_ready": 1 - ready},
                "by_readiness_class": {
                    "execution_identity_missing": 1 if identity_blocked else 0,
                    "hypothesis_ready": ready,
                },
                "safe_to_execute": False,
            },
        ),
        "request": _write(
            tmp_path / "request.json",
            {
                "report_kind": "qre_executable_validation_request",
                "counts": {"ready": ready, "blocked": 1 - ready},
                "validation_requests": [],
                "safe_to_execute": False,
            },
        ),
        "dry": _write(
            tmp_path / "dry.json",
            {
                "report_kind": "qre_validation_request_dry_run",
                "counts": {"ready": ready, "blocked": 1 - ready},
                "dry_run_results": [],
                "executed_anything": False,
                "safe_to_execute": False,
            },
        ),
        "controlled": _write(
            tmp_path / "controlled.json",
            {
                "report_kind": "qre_controlled_artifact_regeneration",
                "mode": "dry_run",
                "backups_created": [],
                "executed_research_regeneration": False,
                "executed_reporting_materialization": False,
                "final_recommendation": "dry_run_only_controlled_regeneration_not_executed",
                "safe_to_execute": False,
            },
        ),
        "results": _write(
            tmp_path / "results.json",
            {
                "report_kind": "qre_hypothesis_validation_results",
                "validation_results": [{"hypothesis_id": "qre-hyp-1", "status": "passed"}],
                "counts": {"total": 1},
                "safe_to_execute": False,
            },
        ),
        "evidence": _write(
            tmp_path / "evidence.json",
            {
                "report_kind": "qre_evidence_quality_gate",
                "evidence_quality_rows": [
                    {"hypothesis_id": "qre-hyp-1", "quality_class": "usable"}
                ],
                "counts": {"total": 1},
                "safe_to_execute": False,
            },
        ),
        "promotion": _write(
            tmp_path / "promotion.json",
            {
                "report_kind": "qre_validated_hypothesis_promotion_intent",
                "promotion_intents": [
                    {"hypothesis_id": "qre-hyp-1", "intent_status": "operator_review_required"}
                ],
                "counts": {"total": 1},
                "safe_to_execute": False,
            },
        ),
        "audit": _write(
            tmp_path / "audit.json",
            {
                "report_kind": "qre_post_run_evidence_promotion_audit",
                "final_recommendation": audit_status,
                "next_action": "operator_review_promotion_intents",
                "blockers": [],
                "safe_to_execute": False,
            },
        ),
    }


def _collect(paths: dict[str, Path]) -> dict:
    return report.collect_snapshot(
        market_observations_path=paths["observations"],
        readiness_path=paths["readiness"],
        validation_request_path=paths["request"],
        dry_run_path=paths["dry"],
        controlled_regeneration_path=paths["controlled"],
        validation_results_path=paths["results"],
        evidence_quality_path=paths["evidence"],
        promotion_intent_path=paths["promotion"],
        audit_path=paths["audit"],
        generated_at_utc=FROZEN,
    )


def test_identity_missing_blocks_operator_report_loop_status(tmp_path: Path) -> None:
    snap = _collect(
        _fixtures(tmp_path, identity_blocked=True, audit_status="identity_route_still_blocked")
    )

    assert snap["loop_status"] == "loop_blocked_identity_missing"
    assert snap["final_recommendation"] == "loop_blocked_identity_missing"
    assert snap["next_operator_action"] == "repair_explicit_executable_identity_before_regeneration"
    assert snap["safe_to_execute"] is False
    assert snap["read_only"] is True


def test_loop_closed_ready_for_operator_review_when_audit_promotable(tmp_path: Path) -> None:
    snap = _collect(_fixtures(tmp_path))

    assert snap["loop_status"] == "loop_closed_ready_for_operator_review"
    assert snap["operator_summary"]["validation_results"]["count"] == 1
    assert snap["operator_summary"]["promotion_intent"]["rows"] == 1
    assert snap["safety_summary"]["live_paper_shadow_broker_risk_execution_touched"] is False
    assert "operator_review_promotion_intents" in snap["recommended_actions"]


def test_missing_controlled_regeneration_report_requires_regeneration(tmp_path: Path) -> None:
    paths = _fixtures(tmp_path)
    paths["controlled"] = tmp_path / "missing-controlled.json"

    snap = _collect(paths)

    assert snap["loop_status"] == "loop_requires_controlled_regeneration"
    assert "controlled_regeneration:missing_or_unparseable" in snap["validation_warnings"]


def test_write_outputs_writes_json_and_markdown_inside_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_operator_closed_loop_report"
    latest = artifact_dir / "latest.json"
    latest_md = artifact_dir / "latest.md"
    monkeypatch.setattr(report, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(report, "ARTIFACT_LATEST", latest)
    monkeypatch.setattr(report, "MARKDOWN_LATEST", latest_md)
    snap = _collect(_fixtures(tmp_path))

    assert report.write_outputs(snap) == latest
    assert latest.exists()
    assert latest_md.exists()
    assert "QRE Closed-Loop Operator Report" in latest_md.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        report.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_cli_no_write_does_not_write_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_operator_closed_loop_report"
    monkeypatch.setattr(report, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(report, "ARTIFACT_LATEST", artifact_dir / "latest.json")
    monkeypatch.setattr(report, "MARKDOWN_LATEST", artifact_dir / "latest.md")
    paths = _fixtures(tmp_path)

    rc = report.main(
        [
            "--no-write",
            "--market-observations-source",
            str(paths["observations"]),
            "--readiness-source",
            str(paths["readiness"]),
            "--validation-request-source",
            str(paths["request"]),
            "--dry-run-source",
            str(paths["dry"]),
            "--controlled-regeneration-source",
            str(paths["controlled"]),
            "--results-source",
            str(paths["results"]),
            "--evidence-quality-source",
            str(paths["evidence"]),
            "--promotion-intent-source",
            str(paths["promotion"]),
            "--audit-source",
            str(paths["audit"]),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert (artifact_dir / "latest.json").exists() is False
    assert (artifact_dir / "latest.md").exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == report.REPORT_KIND


def test_source_has_no_runtime_launch_or_mutating_queue_calls() -> None:
    src = Path(report.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "os.system",
        "os.popen",
        "shell=True",
        "research.run_research",
        "seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "research/research_action_queue_latest.v1.json",
        "SequenceMatcher",
        "difflib",
        "fuzzy",
    )
    for token in forbidden:
        assert token not in src, token
