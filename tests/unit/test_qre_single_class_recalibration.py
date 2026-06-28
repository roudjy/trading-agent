from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_single_class_recalibration as recalibration


FROZEN = "2026-06-28T13:00:00Z"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _diagnosis_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_funnel_diagnosis",
        "diagnosis_identity": "qcz_fixture",
        "funnel_counts": {
            "eligibility_ready_count": 0,
            "oos_accepted_count": 0,
            "null_control_complete_count": 0,
        },
        "criterion_rows": [
            {
                "criterion_id": "evidence_completeness",
                "recommendation": "keep",
                "affected_cell_count": 7,
                "affected_cell_ids": ["cell-1"],
            },
            {
                "criterion_id": "identity_ambiguity",
                "recommendation": "stratify",
                "affected_cell_count": 2,
                "affected_cell_ids": ["cell-2", "cell-3"],
            },
        ],
        "summary": {
            "primary_bottleneck": "evidence_completeness",
            "secondary_bottlenecks": ["null_controls", "identity_ambiguity"],
        },
    }


def _execution_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_execution",
        "campaign_execution_identity": "qcy_fixture",
        "replay_identity": "qcr_fixture",
        "summary": {
            "executable_cell_count": 0,
        },
    }


def _manifest_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_preregistered_campaign_manifest",
        "manifest_identity": "qcm_fixture",
        "replay_identity": "qcr_fixture",
    }


def test_collect_snapshot_fails_closed_to_no_change_when_change_is_unjustified(tmp_path: Path) -> None:
    diagnosis_path = _write_json(tmp_path / "diagnosis.json", _diagnosis_payload())
    execution_path = _write_json(tmp_path / "execution.json", _execution_payload())
    manifest_path = _write_json(tmp_path / "manifest.json", _manifest_payload())

    snapshot = recalibration.collect_snapshot(
        diagnosis_path=diagnosis_path,
        execution_path=execution_path,
        manifest_path=manifest_path,
        generated_at_utc=FROZEN,
    )

    assert snapshot["decision"] == "INSUFFICIENT_EVIDENCE"
    assert snapshot["selected_criterion_class"] == ""
    assert snapshot["next_action"] == "run_no_change_control_replay"
    assert snapshot["summary"]["final_recommendation"] == "single_class_recalibration_not_justified"
    assert snapshot["summary"]["executable_cell_count"] == 0
    assert snapshot["summary"]["threshold_distance_visible"] is False
    blockers = {
        row["criterion_id"]: row["blocker_reasons"]
        for row in snapshot["candidate_rows"]
    }
    assert "diagnosis_recommendation_not_change_ready:stratify" in blockers["identity_ambiguity"]
    assert "zero_executable_cells" in blockers["identity_ambiguity"]
    assert "threshold_distance_evidence_absent" in blockers["identity_ambiguity"]


def test_collect_snapshot_is_deterministic(tmp_path: Path) -> None:
    diagnosis_path = _write_json(tmp_path / "diagnosis.json", _diagnosis_payload())
    execution_path = _write_json(tmp_path / "execution.json", _execution_payload())
    manifest_path = _write_json(tmp_path / "manifest.json", _manifest_payload())

    first = recalibration.collect_snapshot(
        diagnosis_path=diagnosis_path,
        execution_path=execution_path,
        manifest_path=manifest_path,
        generated_at_utc=FROZEN,
    )
    second = recalibration.collect_snapshot(
        diagnosis_path=diagnosis_path,
        execution_path=execution_path,
        manifest_path=manifest_path,
        generated_at_utc=FROZEN,
    )

    assert first == second
    assert first["recalibration_identity"].startswith("qraa_")


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        recalibration._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(recalibration.__file__).read_text(encoding="utf-8")
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
