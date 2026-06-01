from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import execution_authority as ea
from reporting import qre_development_intake_promotion as promo


def _proposal(**overrides: Any) -> dict[str, Any]:
    base = {
        "proposal_id": "qre-proposal-001",
        "source_type": "qre_research_action_consumer_gate",
        "proposal_type": "qre_research_action",
        "title": "QRE research action: inspect signal quality",
        "status": "proposed",
        "risk_class": "LOW",
        "execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "affected_files": ["reporting/qre_development_intake_promotion.py"],
        "required_tests": [
            "python -m pytest tests/unit/test_qre_development_intake_promotion.py -q"
        ],
        "suggested_branch_name": "fix/qre-action-signal-quality",
        "forbidden_actions": [
            "launch_codex",
            "mutate_campaign_queue",
            "mutate_strategy_or_preset",
            "enable_paper_runtime",
            "enable_shadow_runtime",
            "enable_live_runtime",
            "place_order",
            "allocate_capital",
        ],
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
    }
    base.update(overrides)
    return base


def _write_intake(tmp_path: Path, proposals: list[Any], **overrides: Any) -> Path:
    path = tmp_path / "logs" / "qre_research_action_proposal_intake" / "latest.json"
    path.parent.mkdir(parents=True)
    payload = {
        "schema_version": 1,
        "report_kind": "qre_research_action_proposal_intake",
        "generated_at_utc": "2026-06-01T12:00:00Z",
        "safe_to_execute": False,
        "proposals": proposals,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _snapshot(tmp_path: Path, proposals: list[Any]) -> dict[str, Any]:
    return promo.collect_snapshot(
        input_artifact_path=_write_intake(tmp_path, proposals),
        generated_at_utc="2026-06-01T12:00:00Z",
    )


def test_proposed_qre_proposal_becomes_pending_not_eligible(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_proposal(status="proposed")])

    row = snap["rows"][0]
    assert row["decision_state"] == "pending"
    assert row["promotion_target"] == "none"
    assert row["safe_to_execute"] is False
    assert row["eligible_for_direct_execution"] is False
    assert snap["counts"]["by_decision_state"]["eligible"] == 0


def test_needs_human_remains_human_needed(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_proposal(status="needs_human")])

    row = snap["rows"][0]
    assert row["decision_state"] == "human_needed"
    assert row["human_needed"] is True
    assert row["promotion_target"] == "none"


def test_blocked_remains_blocked(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_proposal(status="blocked")])

    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert row["promotion_target"] == "none"


def test_explicit_eligible_low_auto_allowed_can_become_promotion_intent(
    tmp_path: Path,
) -> None:
    snap = _snapshot(tmp_path, [_proposal(status="eligible")])

    row = snap["rows"][0]
    assert row["decision_state"] == "eligible"
    assert row["promotion_target"] == "development_work_queue"
    assert row["reclassified_execution_authority_decision"] == ea.DECISION_AUTO_ALLOWED
    assert row["safe_to_execute"] is False
    assert row["eligible_for_direct_execution"] is False


def test_safe_to_execute_true_blocks(tmp_path: Path) -> None:
    snap = _snapshot(tmp_path, [_proposal(status="eligible", safe_to_execute=True)])

    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert "upstream_safe_to_execute_true" in row["validation_warnings"]
    assert row["safe_to_execute"] is False


def test_eligible_for_direct_execution_true_blocks(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [_proposal(status="eligible", eligible_for_direct_execution=True)],
    )

    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert "upstream_eligible_for_direct_execution_true" in row["validation_warnings"]
    assert row["eligible_for_direct_execution"] is False


def test_classification_drift_blocks(tmp_path: Path) -> None:
    snap = _snapshot(
        tmp_path,
        [
            _proposal(
                status="eligible",
                risk_class="HIGH",
                execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
            )
        ],
    )

    row = snap["rows"][0]
    assert row["decision_state"] == "blocked"
    assert row["classification_drift"] is True
    assert "classification_drift" in row["validation_warnings"]


def test_missing_required_fields_fail_row_closed_as_blocked(tmp_path: Path) -> None:
    proposal = _proposal()
    proposal.pop("proposal_id")
    proposal.pop("title")
    proposal.pop("risk_class")

    snap = _snapshot(tmp_path, [proposal])

    row = snap["rows"][0]
    assert row["candidate_id"] == "invalid-proposal-0001"
    assert row["decision_state"] == "blocked"
    assert "missing_required_field:proposal_id" in row["validation_warnings"]
    assert "missing_required_field:title" in row["validation_warnings"]
    assert "missing_required_field:risk_class" in row["validation_warnings"]


def test_missing_artifact_fails_closed(tmp_path: Path) -> None:
    snap = promo.collect_snapshot(
        input_artifact_path=tmp_path / "missing.json",
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert snap["input_artifact_available"] is False
    assert snap["rows"] == []
    assert snap["safe_to_execute"] is False
    assert "proposal_intake_artifact_absent" in snap["validation_warnings"]


def test_malformed_payload_fails_closed(tmp_path: Path) -> None:
    path = _write_intake(tmp_path, [], report_kind="wrong_kind")

    snap = promo.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert snap["input_artifact_available"] is True
    assert snap["rows"] == []
    assert "proposal_intake_artifact_unparseable" in snap["validation_warnings"]


def test_deterministic_output_with_injected_timestamp(tmp_path: Path) -> None:
    path = _write_intake(tmp_path, [_proposal(), _proposal(proposal_id="qre-002")])
    snap_a = promo.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )
    snap_b = promo.collect_snapshot(
        input_artifact_path=path,
        generated_at_utc="2026-06-01T12:00:00Z",
    )

    assert json.dumps(snap_a, sort_keys=True) == json.dumps(snap_b, sort_keys=True)


def test_atomic_write_refuses_non_output_dir_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        promo._atomic_write_json(tmp_path / "latest.json", {"x": 1})


def test_write_outputs_writes_only_latest(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "logs" / "qre_development_intake_promotion"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(promo, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(promo, "ARTIFACT_LATEST", latest)

    out = promo.write_outputs({"schema_version": 1, "rows": []})

    assert out == latest
    assert json.loads(latest.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "rows": [],
    }
    assert sorted(path.name for path in artifact_dir.iterdir()) == ["latest.json"]


def _module_source() -> str:
    return Path(promo.__file__).read_text(encoding="utf-8")


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


def test_module_source_has_no_forbidden_runtime_launch_or_network_calls() -> None:
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
    )
    for token in forbidden:
        assert token not in src, token


def test_module_imports_only_stdlib_and_execution_authority() -> None:
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
        "reporting.execution_authority",
    }
    assert _imported_module_names() - allowed == set()


def test_module_source_does_not_write_queue_seed_or_active_queue_paths() -> None:
    src = _module_source()
    forbidden = (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
        "logs/development_work_queue/latest.json",
        "SEED_PATH",
        "GENERATED_SEED_PATH",
    )
    for token in forbidden:
        assert token not in src, token
