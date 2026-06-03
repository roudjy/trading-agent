from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_post_run_evidence_promotion_audit as audit

FROZEN = "2026-06-01T12:00:00Z"


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _results(path: Path, rows: list[dict]) -> Path:
    return _write(
        path,
        {
            "report_kind": "qre_hypothesis_validation_results",
            "validation_results": rows,
            "safe_to_execute": False,
        },
    )


def _evidence(path: Path, rows: list[dict]) -> Path:
    return _write(
        path,
        {
            "report_kind": "qre_evidence_quality_gate",
            "evidence_quality_rows": rows,
            "safe_to_execute": False,
        },
    )


def _promotion(path: Path, rows: list[dict]) -> Path:
    return _write(
        path,
        {
            "report_kind": "qre_validated_hypothesis_promotion_intent",
            "promotion_intents": rows,
            "safe_to_execute": False,
        },
    )


def _request(path: Path, ready: int = 0, identity_blocked: int = 0) -> Path:
    return _write(
        path,
        {
            "report_kind": "qre_executable_validation_request",
            "counts": {
                "ready": ready,
                "by_request_status": {
                    "request_ready_for_operator_review": ready,
                    "request_blocked_identity_missing": identity_blocked,
                },
            },
            "validation_requests": [],
            "safe_to_execute": False,
        },
    )


def _dry(path: Path, ready: int = 0) -> Path:
    return _write(
        path,
        {
            "report_kind": "qre_validation_request_dry_run",
            "counts": {"ready": ready, "by_dry_run_status": {"dry_run_ready": ready}},
            "dry_run_results": [],
            "safe_to_execute": False,
        },
    )


def test_identity_blocked_route_is_classified_before_validation_result_absence(
    tmp_path: Path,
) -> None:
    snap = audit.collect_snapshot(
        validation_results_path=_results(tmp_path / "results.json", []),
        evidence_quality_path=_evidence(tmp_path / "evidence.json", []),
        promotion_intent_path=_promotion(tmp_path / "promotion.json", []),
        validation_request_path=_request(tmp_path / "request.json", identity_blocked=32),
        dry_run_path=_dry(tmp_path / "dry.json"),
        generated_at_utc=FROZEN,
    )

    assert snap["final_recommendation"] == "identity_route_still_blocked"
    assert "identity_route_still_blocked" in snap["blockers"]
    assert snap["audit_summary"]["validation_results_count"] == 0
    assert snap["next_action"] == "repair_explicit_executable_identity_before_regeneration"


def test_no_validation_results_classification_when_route_not_identity_blocked(
    tmp_path: Path,
) -> None:
    snap = audit.collect_snapshot(
        validation_results_path=_results(tmp_path / "results.json", []),
        evidence_quality_path=_evidence(tmp_path / "evidence.json", []),
        promotion_intent_path=_promotion(tmp_path / "promotion.json", []),
        validation_request_path=_request(tmp_path / "request.json", ready=1),
        dry_run_path=_dry(tmp_path / "dry.json", ready=1),
        generated_at_utc=FROZEN,
    )

    assert snap["final_recommendation"] == "no_validation_results"
    assert snap["safe_to_execute"] is False
    assert snap["read_only"] is True


def test_promotion_ready_for_operator_review(tmp_path: Path) -> None:
    hypothesis_id = "qre-hyp-ready"
    snap = audit.collect_snapshot(
        validation_results_path=_results(
            tmp_path / "results.json",
            [{"hypothesis_id": hypothesis_id, "status": "passed"}],
        ),
        evidence_quality_path=_evidence(
            tmp_path / "evidence.json",
            [{"hypothesis_id": hypothesis_id, "quality_class": "usable"}],
        ),
        promotion_intent_path=_promotion(
            tmp_path / "promotion.json",
            [{"hypothesis_id": hypothesis_id, "intent_status": "operator_review_required"}],
        ),
        validation_request_path=_request(tmp_path / "request.json", ready=1),
        dry_run_path=_dry(tmp_path / "dry.json", ready=1),
        generated_at_utc=FROZEN,
    )

    assert snap["final_recommendation"] == "promotion_ready_for_operator_review"
    assert snap["audit_summary"]["validation_status_counts"]["passed"] == 1
    assert snap["audit_summary"]["quality_class_counts"]["usable"] == 1
    assert snap["audit_summary"]["promotion_readiness_counts"]["operator_review_required"] == 1
    assert snap["next_action"] == "operator_review_promotion_intents"


def test_backup_comparison_is_included_when_available(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    (backup_dir / "research__run_candidates_latest.v1.json").write_text("{}", encoding="utf-8")

    snap = audit.collect_snapshot(
        validation_results_path=_results(tmp_path / "results.json", []),
        evidence_quality_path=_evidence(tmp_path / "evidence.json", []),
        promotion_intent_path=_promotion(tmp_path / "promotion.json", []),
        validation_request_path=_request(tmp_path / "request.json", ready=1),
        dry_run_path=_dry(tmp_path / "dry.json", ready=1),
        backup_dir=backup_dir,
        generated_at_utc=FROZEN,
    )

    comparison = snap["audit_summary"]["before_after_comparison"]
    assert comparison["available"] is True
    assert comparison["snapshot_file_count"] == 1


def test_write_outputs_only_allows_audit_artifact_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_post_run_evidence_promotion_audit"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(audit, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(audit, "ARTIFACT_LATEST", latest)
    snap = audit.collect_snapshot(
        validation_results_path=_results(tmp_path / "results.json", []),
        evidence_quality_path=_evidence(tmp_path / "evidence.json", []),
        promotion_intent_path=_promotion(tmp_path / "promotion.json", []),
        validation_request_path=_request(tmp_path / "request.json", ready=1),
        dry_run_path=_dry(tmp_path / "dry.json", ready=1),
        generated_at_utc=FROZEN,
    )

    assert audit.write_outputs(snap) == latest
    with pytest.raises(ValueError):
        audit.write_outputs(snap, output_path=tmp_path / "outside.json")


def test_cli_no_write_does_not_write_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    artifact_dir = tmp_path / "logs" / "qre_post_run_evidence_promotion_audit"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(audit, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(audit, "ARTIFACT_LATEST", latest)

    rc = audit.main(
        [
            "--no-write",
            "--results-source",
            str(_results(tmp_path / "results.json", [])),
            "--evidence-quality-source",
            str(_evidence(tmp_path / "evidence.json", [])),
            "--promotion-intent-source",
            str(_promotion(tmp_path / "promotion.json", [])),
            "--validation-request-source",
            str(_request(tmp_path / "request.json", ready=1)),
            "--dry-run-source",
            str(_dry(tmp_path / "dry.json", ready=1)),
            "--frozen-utc",
            FROZEN,
            "--indent",
            "0",
        ]
    )

    assert rc == 0
    assert latest.exists() is False
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == audit.REPORT_KIND


def test_source_has_no_runtime_launch_or_mutating_queue_calls() -> None:
    src = Path(audit.__file__).read_text(encoding="utf-8")
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
