from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import execution_authority as ea
from reporting import qre_development_intake_promotion as qdip
from reporting import qre_development_queue_admission_policy as qap


def _promotion_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "candidate_id": "qre-proposal-001",
        "title": "QRE research action: inspect signal quality",
        "source_kind": "qre_research_action_consumer_gate",
        "candidate_kind": "qre_research_action",
        "category": "research_diagnostic",
        "risk_level": ea.RISK_LOW,
        "target_path": "reporting/qre_development_queue_admission_policy.py",
        "upstream_proposal_status": "eligible",
        "upstream_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "reclassified_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "classification_drift": False,
        "human_needed": False,
        "human_needed_reason": "",
        "promotion_target": qdip.PROMOTION_TARGET_DEVELOPMENT_WORK_QUEUE,
        "decision_state": qdip.DECISION_ELIGIBLE,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "suggested_branch_name": "fix/qre-action-signal-quality",
        "required_tests": [
            "python -m pytest tests/unit/test_qre_development_queue_admission_policy.py -q"
        ],
        "affected_files": ["reporting/qre_development_queue_admission_policy.py"],
        "forbidden_actions": [],
        "validation_warnings": [],
    }
    base.update(overrides)
    return base


def _write_promotion_artifact(
    tmp_path: Path,
    rows: list[Any],
    **overrides: Any,
) -> Path:
    path = tmp_path / "logs" / "qre_development_intake_promotion" / "latest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "report_kind": qdip.REPORT_KIND,
        "generated_at_utc": "2026-06-01T12:00:00Z",
        "safe_to_execute": False,
        "rows": rows,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _snapshot(tmp_path: Path, rows: list[Any]) -> dict[str, Any]:
    return qap.collect_snapshot(
        input_artifact_path=_write_promotion_artifact(tmp_path, rows),
        generated_at_utc="2026-06-01T12:00:00Z",
    )


def test_closed_vocabularies_are_pinned() -> None:
    assert qap.ADMISSION_DECISIONS == (
        "admissible",
        "needs_human",
        "blocked",
        "duplicate_of_existing",
        "not_eligible_upstream",
    )
    assert qap.ADMISSION_REASONS == (
        "auto_allowed_low_risk_eligible_qre_promotion",
        "needs_human_authority_decision",
        "needs_human_unknown_or_invalid_risk",
        "needs_human_classification_drift",
        "needs_human_protected_target_path",
        "blocked_authority_permanently_denied",
        "blocked_classification_drift_to_denied",
        "upstream_decision_state_not_eligible",
        "upstream_safe_to_execute_true",
        "upstream_eligible_for_direct_execution_true",
        "duplicate_candidate_id",
        "malformed_upstream_record",
    )


def test_exact_row_schema_is_pinned_and_ordered(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_promotion_row()])

    assert qap.ADMISSION_SCHEMA_KEYS == (
        "candidate_id",
        "title",
        "source_kind",
        "candidate_kind",
        "category",
        "risk_level",
        "target_path",
        "upstream_proposal_status",
        "upstream_decision_state",
        "upstream_execution_authority_decision",
        "reclassified_execution_authority_decision",
        "classification_drift",
        "human_needed",
        "human_needed_reason",
        "admission_decision",
        "admission_reason",
        "would_target_lane",
        "safe_to_execute",
        "eligible_for_direct_execution",
        "policy_version",
        "evaluated_at",
    )
    assert tuple(snap["rows"][0].keys()) == qap.ADMISSION_SCHEMA_KEYS


def test_missing_input_artifact_fails_closed_with_zero_rows(tmp_path: Path) -> None:
    snap = qap.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert snap["input_artifact_available"] is False
    assert snap["rows"] == []
    assert snap["counts"]["total"] == 0
    assert snap["safe_to_execute"] is False
    assert "qre_promotion_artifact_absent" in snap["validation_warnings"]


def test_malformed_payload_fails_closed(tmp_path: Path) -> None:
    path = _write_promotion_artifact(tmp_path, [], report_kind="wrong_kind")

    snap = qap.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert snap["input_artifact_available"] is True
    assert snap["rows"] == []
    assert snap["counts"]["total"] == 0
    assert "qre_promotion_artifact_unparseable" in snap["validation_warnings"]


def test_pending_proposed_derived_row_is_not_eligible_upstream(
    tmp_path: Path,
) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                upstream_proposal_status="proposed",
                decision_state=qdip.DECISION_PENDING,
                promotion_target=qdip.PROMOTION_TARGET_NONE,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "not_eligible_upstream"
    assert row["admission_reason"] == "upstream_decision_state_not_eligible"
    assert row["would_target_lane"] == "none"


def test_human_needed_upstream_row_becomes_needs_human(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                decision_state=qdip.DECISION_HUMAN_NEEDED,
                human_needed=True,
                upstream_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
                reclassified_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "needs_human"
    assert row["admission_reason"] == "needs_human_authority_decision"


def test_blocked_upstream_row_becomes_not_eligible_upstream(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_promotion_row(decision_state=qdip.DECISION_BLOCKED)])

    row = snap["rows"][0]
    assert row["admission_decision"] == "not_eligible_upstream"
    assert row["admission_reason"] == "upstream_decision_state_not_eligible"


def test_explicit_eligible_low_auto_allowed_row_is_admissible(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_promotion_row()])

    row = snap["rows"][0]
    assert row["admission_decision"] == "admissible"
    assert row["admission_reason"] == "auto_allowed_low_risk_eligible_qre_promotion"
    assert row["would_target_lane"] == "development_work_queue"
    assert snap["counts"]["admissible"] == 1


def test_safe_to_execute_true_blocks(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_promotion_row(safe_to_execute=True)])

    row = snap["rows"][0]
    assert row["admission_decision"] == "blocked"
    assert row["admission_reason"] == "upstream_safe_to_execute_true"


def test_eligible_for_direct_execution_true_blocks(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [_promotion_row(eligible_for_direct_execution=True)],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "blocked"
    assert row["admission_reason"] == "upstream_eligible_for_direct_execution_true"


def test_permanently_denied_blocks(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                upstream_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
                reclassified_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "blocked"
    assert row["admission_reason"] == "blocked_authority_permanently_denied"


def test_classification_drift_to_denied_blocks(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                upstream_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
                reclassified_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
                classification_drift=True,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "blocked"
    assert row["admission_reason"] == "blocked_classification_drift_to_denied"


def test_classification_drift_non_denied_needs_human(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                upstream_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
                reclassified_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
                classification_drift=True,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "needs_human"
    assert row["admission_reason"] == "needs_human_classification_drift"


def test_unknown_or_invalid_risk_needs_human(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(
                risk_level="EXTREME",
                upstream_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
                reclassified_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["admission_decision"] == "needs_human"
    assert row["admission_reason"] == "needs_human_unknown_or_invalid_risk"


def test_duplicate_candidate_id_later_duplicate_only(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _promotion_row(candidate_id="dup"),
            _promotion_row(candidate_id="dup", title="Duplicate copy"),
        ],
    )

    first, second = snap["rows"]
    assert first["admission_decision"] == "admissible"
    assert second["admission_decision"] == "duplicate_of_existing"
    assert second["admission_reason"] == "duplicate_candidate_id"


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    path = _write_promotion_artifact(
        tmp_path,
        [_promotion_row(), _promotion_row(candidate_id="qre-proposal-002")],
    )

    snap_a = qap.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )
    snap_b = qap.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)


def test_atomic_write_refuses_non_output_dir_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        qap._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_write_outputs_writes_only_latest(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "logs" / "qre_development_queue_admission_policy"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(qap, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(qap, "ARTIFACT_LATEST", latest)

    out = qap.write_outputs({"schema_version": 1, "rows": []})

    assert out == latest
    assert json.loads(latest.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "rows": [],
    }
    assert sorted(path.name for path in artifact_dir.iterdir()) == ["latest.json"]


def _module_source() -> str:
    return Path(qap.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_source_has_no_subprocess_network_or_launch_calls() -> None:
    src = _module_source()
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import urllib",
        "from urllib",
        "import requests",
        "import httpx",
        "import aiohttp",
        "os.system",
        "os.popen",
        "shell=True",
        "gh pr",
        "git ",
        "codex",
    )
    for token in forbidden:
        assert token not in src, token


def test_module_imports_only_allowed_dependencies() -> None:
    allowed = {
        "__future__",
        "argparse",
        "ast",
        "collections",
        "datetime",
        "json",
        "os",
        "pathlib",
        "sys",
        "tempfile",
        "typing",
        "reporting",
        "reporting.agent_audit_summary",
    }
    assert _imported_module_names() - allowed == set()


def test_source_does_not_write_queue_seed_or_active_queue_paths() -> None:
    src = _module_source()
    forbidden = (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
    )
    for token in forbidden:
        assert token not in src, token


def test_module_imports_cleanly() -> None:
    importlib.reload(qap)
    assert callable(qap.collect_snapshot)
