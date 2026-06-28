from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_same_input_replay as replay


FROZEN = "2026-06-28T14:00:00Z"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _recalibration_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_single_class_recalibration",
        "recalibration_identity": "qraa_fixture",
        "decision": "INSUFFICIENT_EVIDENCE",
        "source_execution_identity": "qcy_fixture",
        "source_manifest_identity": "qcm_fixture",
        "source_replay_identity": "qcr_fixture",
    }


def _diagnosis_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_funnel_diagnosis",
        "funnel_counts": {
            "raw_scope_count": 9,
            "eligibility_ready_count": 0,
            "validation_completed_count": 0,
            "oos_accepted_count": 0,
            "null_control_complete_count": 0,
        },
    }


def _execution_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_execution",
        "campaign_execution_identity": "qcy_fixture",
        "summary": {
            "accounted_cell_count": 9,
            "executable_cell_count": 0,
        },
    }


def _manifest_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_preregistered_campaign_manifest",
        "manifest_identity": "qcm_fixture",
        "replay_identity": "qcr_fixture",
    }


def _operator_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_operator_decision_report",
        "summary": {
            "decision_counts": {
                "SUPPORTED_FOR_REVIEW": 0,
                "REJECTED": 1,
                "INSUFFICIENT_EVIDENCE": 0,
                "BLOCKED": 6,
            }
        },
    }


def test_collect_snapshot_confirms_no_change_control_replay(tmp_path: Path) -> None:
    snapshot = replay.collect_snapshot(
        recalibration_path=_write_json(tmp_path / "recalibration.json", _recalibration_payload()),
        diagnosis_path=_write_json(tmp_path / "diagnosis.json", _diagnosis_payload()),
        execution_path=_write_json(tmp_path / "execution.json", _execution_payload()),
        manifest_path=_write_json(tmp_path / "manifest.json", _manifest_payload()),
        operator_path=_write_json(tmp_path / "operator.json", _operator_payload()),
        generated_at_utc=FROZEN,
    )

    assert snapshot["decision"] == "INSUFFICIENT_EVIDENCE"
    assert snapshot["replay_mode"] == "no_change_control_confirmation"
    assert snapshot["funnel_comparison"]["raw_scope_count_before"] == 9
    assert snapshot["funnel_comparison"]["raw_scope_count_after"] == 9
    assert snapshot["regression_checks"]["manifest_identity_unchanged"] is True
    assert snapshot["regression_checks"]["replay_identity_unchanged"] is True
    assert snapshot["summary"]["final_recommendation"] == "same_input_replay_no_change_confirmed"
    assert "no_approved_single_class_change_visible" in snapshot["summary"]["blocker_reasons"]


def test_collect_snapshot_is_deterministic(tmp_path: Path) -> None:
    kwargs = {
        "recalibration_path": _write_json(tmp_path / "recalibration.json", _recalibration_payload()),
        "diagnosis_path": _write_json(tmp_path / "diagnosis.json", _diagnosis_payload()),
        "execution_path": _write_json(tmp_path / "execution.json", _execution_payload()),
        "manifest_path": _write_json(tmp_path / "manifest.json", _manifest_payload()),
        "operator_path": _write_json(tmp_path / "operator.json", _operator_payload()),
        "generated_at_utc": FROZEN,
    }
    first = replay.collect_snapshot(**kwargs)
    second = replay.collect_snapshot(**kwargs)

    assert first == second
    assert first["replay_assessment_identity"].startswith("qrab_")


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        replay._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(replay.__file__).read_text(encoding="utf-8")
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
