"""Unit tests for A9 — Agentic Release-Gate Integration.

Synthetic deterministic fixtures only. The pure scorer consumes
two read-only inputs (the A8 work-queue artifact and the structured
evidence input contract) and emits closed-vocabulary verdicts.
ADE core never collects evidence itself; the architecture explicitly
preserves a future collector/adapter path outside ADE core.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_release_gate as drg
from reporting import development_work_queue as dwq
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _queue_path(tmp_path: Path) -> Path:
    return tmp_path / "queue.json"


def _evidence_path(tmp_path: Path) -> Path:
    return tmp_path / "evidence.json"


def _release_item(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "item_id": "dwq_a9releaseaaa",
        "title": "Cut release v3.15.16.A9",
        "source_document": "docs/operator/release_notes.md",
        "source_section_or_anchor": "A9-release",
        "roadmap_track": "sidecar_seed",
        "category": "release",
        "required_agent_role": "release_gate_agent",
        "supporting_agent_roles": ["evidence_verifier"],
        "execution_authority": ea.DECISION_AUTO_ALLOWED,
        "status": "validation_needed",
        "human_needed": False,
        "human_needed_reason": "none",
        "blocked_by": [],
        "priority": 2,
        "risk_level": "LOW",
        "protected_surface": False,
        "acceptance_criteria": ["release notes drafted"],
        "validation_requirements": [],
        "created_at_placeholder": "deterministic_seed_placeholder",
        "updated_at_placeholder": "deterministic_seed_placeholder",
        "notes": "",
    }
    base.update(overrides)
    return base


def _write_queue(tmp_path: Path, items: list[dict[str, Any]]) -> Path:
    p = _queue_path(tmp_path)
    p.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": dwq.MODULE_VERSION,
                "report_kind": "development_work_queue",
                "items": items,
            }
        ),
        encoding="utf-8",
    )
    return p


def _all_clean_evidence() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "evidence": {
            "ci_status": {"present": True, "value": "green"},
            "smoke_status": {"present": True, "value": "passed"},
            "governance_lint_status": {"present": True, "value": "ok"},
            "frozen_hash_status": {"present": True, "value": "stable"},
            "no_touch_path_delta_status": {"present": True, "value": "clean"},
            "queue_cross_reference_status": {"present": True, "value": "consistent"},
        },
    }


def _write_evidence(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = _evidence_path(tmp_path)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Vocabulary integrity
# ---------------------------------------------------------------------------


def test_verdicts_vocabulary_is_closed_and_ordered() -> None:
    assert drg.VERDICTS == (
        "go",
        "go_with_followups",
        "no_go_blocked",
        "no_go_human_needed",
        "not_evaluated",
    )
    assert len(drg.VERDICTS) == 5


def test_verdict_reasons_vocabulary_is_closed_and_ordered() -> None:
    assert drg.VERDICT_REASONS == (
        "all_required_evidence_clean",
        "clean_with_advisory_followups",
        "ci_failed",
        "smoke_failed",
        "governance_lint_failed",
        "frozen_contract_change_detected",
        "protected_path_modification_detected",
        "queue_cross_reference_inconsistent",
        "protected_surface_present",
        "execution_authority_needs_human",
        "execution_authority_permanently_denied",
        "evidence_input_missing",
        "required_evidence_absent",
        "ci_status_pending",
        "queue_artifact_missing",
        "queue_item_not_release_validation_needed",
    )
    assert len(drg.VERDICT_REASONS) == 16


def test_evidence_keys_vocabulary_is_closed_and_ordered() -> None:
    assert drg.EVIDENCE_KEYS == (
        "ci_status",
        "smoke_status",
        "governance_lint_status",
        "frozen_hash_status",
        "no_touch_path_delta_status",
        "queue_cross_reference_status",
    )
    assert len(drg.EVIDENCE_KEYS) == 6


def test_evidence_value_vocab_is_closed_per_key() -> None:
    assert drg.EVIDENCE_VALUE_VOCAB["ci_status"] == ("green", "red", "pending", "unknown")
    assert drg.EVIDENCE_VALUE_VOCAB["smoke_status"] == ("passed", "failed", "unknown")
    assert drg.EVIDENCE_VALUE_VOCAB["governance_lint_status"] == ("ok", "fail", "unknown")
    assert drg.EVIDENCE_VALUE_VOCAB["frozen_hash_status"] == ("stable", "drift", "unknown")
    assert drg.EVIDENCE_VALUE_VOCAB["no_touch_path_delta_status"] == ("clean", "violation", "unknown")
    assert drg.EVIDENCE_VALUE_VOCAB["queue_cross_reference_status"] == ("consistent", "missing_item", "unknown")
    # Every evidence key has a value vocabulary.
    assert set(drg.EVIDENCE_VALUE_VOCAB) == set(drg.EVIDENCE_KEYS)


def test_row_schema_keys_are_exact_and_ordered() -> None:
    assert drg.ROW_SCHEMA_KEYS == (
        "gate_id",
        "queue_item_id",
        "title",
        "verdict",
        "verdict_reason",
        "evidence_inputs",
        "missing_evidence",
        "required_followups",
        "human_needed",
        "human_needed_reason",
        "execution_authority_decision",
        "risk_level",
        "protected_surface",
        "created_at_placeholder",
        "updated_at_placeholder",
        "notes",
    )


# ---------------------------------------------------------------------------
# Artifact path discipline
# ---------------------------------------------------------------------------


def test_artifact_path_is_under_logs_not_research() -> None:
    assert drg.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in drg.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "not_logs" / "latest.json"
    with pytest.raises(ValueError):
        drg._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=ep,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "queue_artifact_path",
        "queue_artifact_present",
        "evidence_input_path",
        "evidence_input_present",
        "evidence_snapshot_id",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "execution_authority_module_version",
        "queue_module_version",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_release_gate"
    assert snap["queue_artifact_present"] is True
    assert snap["evidence_input_present"] is True


def test_snapshot_when_queue_artifact_missing(tmp_path: Path) -> None:
    qp = tmp_path / "missing_queue.json"
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=tmp_path / "missing_ev.json")
    assert snap["queue_artifact_present"] is False
    assert snap["rows"] == []
    assert snap["note"] == drg.NOTE_NO_QUEUE_ARTIFACT
    assert snap["counts"]["total"] == 0


def test_snapshot_when_no_qualifying_items(tmp_path: Path) -> None:
    """Items not in category=release or not in status=validation_needed
    must not appear in the gate."""
    items = [
        _release_item(item_id="dwq_other001", category="docs"),
        _release_item(item_id="dwq_other002", status="ready"),
    ]
    qp = _write_queue(tmp_path, items)
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(
        queue_artifact_path=qp, evidence_input_path=ep
    )
    assert snap["rows"] == []
    assert snap["note"] == drg.NOTE_NO_QUALIFYING_ITEMS


def test_snapshot_when_evidence_input_missing(tmp_path: Path) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    snap = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=tmp_path / "missing_ev.json",
    )
    assert snap["note"] == drg.NOTE_NO_EVIDENCE_INPUT
    assert snap["rows"][0]["verdict"] == drg.VERDICT_NOT_EVALUATED
    assert snap["rows"][0]["verdict_reason"] == "evidence_input_missing"


# ---------------------------------------------------------------------------
# Verdict semantics — happy path
# ---------------------------------------------------------------------------


def test_all_clean_evidence_yields_go(tmp_path: Path) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert snap["counts"]["total"] == 1
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_GO
    assert row["verdict_reason"] == "all_required_evidence_clean"
    assert set(row["evidence_inputs"]) == set(drg.EVIDENCE_KEYS)
    assert row["missing_evidence"] == []
    assert row["required_followups"] == []
    assert row["human_needed"] is False


def test_clean_with_validation_requirements_yields_go_with_followups(
    tmp_path: Path,
) -> None:
    item = _release_item(
        validation_requirements=["operator confirms changelog drafted"]
    )
    qp = _write_queue(tmp_path, [item])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_GO_WITH_FOLLOWUPS
    assert row["verdict_reason"] == "clean_with_advisory_followups"
    assert "operator confirms changelog drafted" in row["required_followups"]


# ---------------------------------------------------------------------------
# Verdict semantics — protected-surface and authority overrides
# ---------------------------------------------------------------------------


def test_protected_surface_always_no_go_human_needed_even_with_clean_evidence(
    tmp_path: Path,
) -> None:
    item = _release_item(protected_surface=True)
    qp = _write_queue(tmp_path, [item])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NO_GO_HUMAN_NEEDED
    assert row["verdict_reason"] == "protected_surface_present"
    assert row["human_needed"] is True
    assert row["human_needed_reason"] == "protected_governance_change"


def test_execution_authority_needs_human_blocks_go(tmp_path: Path) -> None:
    item = _release_item(execution_authority=ea.DECISION_NEEDS_HUMAN)
    qp = _write_queue(tmp_path, [item])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NO_GO_HUMAN_NEEDED
    assert row["verdict_reason"] == "execution_authority_needs_human"


def test_execution_authority_permanently_denied_blocks_go(tmp_path: Path) -> None:
    item = _release_item(execution_authority=ea.DECISION_PERMANENTLY_DENIED)
    qp = _write_queue(tmp_path, [item])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NO_GO_HUMAN_NEEDED
    assert row["verdict_reason"] == "execution_authority_permanently_denied"


# ---------------------------------------------------------------------------
# Verdict semantics — hard blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("evidence_key", "bad_value", "expected_reason"),
    [
        ("frozen_hash_status", "drift", "frozen_contract_change_detected"),
        ("no_touch_path_delta_status", "violation", "protected_path_modification_detected"),
        ("ci_status", "red", "ci_failed"),
        ("smoke_status", "failed", "smoke_failed"),
        ("governance_lint_status", "fail", "governance_lint_failed"),
        ("queue_cross_reference_status", "missing_item", "queue_cross_reference_inconsistent"),
    ],
)
def test_hard_block_evidence_yields_no_go_blocked(
    tmp_path: Path,
    evidence_key: str,
    bad_value: str,
    expected_reason: str,
) -> None:
    payload = _all_clean_evidence()
    payload["evidence"][evidence_key]["value"] = bad_value
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NO_GO_BLOCKED
    assert row["verdict_reason"] == expected_reason


def test_frozen_drift_overrides_other_signals(tmp_path: Path) -> None:
    """Frozen-contract drift takes precedence over any other hard
    block, by precedence ordering."""
    payload = _all_clean_evidence()
    payload["evidence"]["frozen_hash_status"]["value"] = "drift"
    payload["evidence"]["ci_status"]["value"] = "red"
    payload["evidence"]["smoke_status"]["value"] = "failed"
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert snap["rows"][0]["verdict_reason"] == "frozen_contract_change_detected"


# ---------------------------------------------------------------------------
# Verdict semantics — not_evaluated
# ---------------------------------------------------------------------------


def test_ci_pending_yields_not_evaluated(tmp_path: Path) -> None:
    payload = _all_clean_evidence()
    payload["evidence"]["ci_status"]["value"] = "pending"
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NOT_EVALUATED
    assert row["verdict_reason"] == "ci_status_pending"


def test_required_evidence_absent_yields_not_evaluated(tmp_path: Path) -> None:
    payload = _all_clean_evidence()
    payload["evidence"]["governance_lint_status"]["present"] = False
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NOT_EVALUATED
    assert row["verdict_reason"] == "required_evidence_absent"
    assert "governance_lint_status" in row["missing_evidence"]


def test_unknown_evidence_value_yields_not_evaluated(tmp_path: Path) -> None:
    payload = _all_clean_evidence()
    payload["evidence"]["smoke_status"]["value"] = "unknown"
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    row = snap["rows"][0]
    assert row["verdict"] == drg.VERDICT_NOT_EVALUATED
    assert row["verdict_reason"] == "required_evidence_absent"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_gate_id_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap_a = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=ep,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    snap_b = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=ep,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    assert snap_a["rows"][0]["gate_id"] == snap_b["rows"][0]["gate_id"]
    assert snap_a["rows"][0]["gate_id"].startswith("rg_")


def test_artifact_bytes_are_deterministic_with_injected_timestamp(
    tmp_path: Path,
) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap_a = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=ep,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    snap_b = drg.collect_snapshot(
        queue_artifact_path=qp,
        evidence_input_path=ep,
        generated_at_utc="2026-05-07T00:00:00Z",
    )
    bytes_a = json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
    bytes_b = json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    assert bytes_a == bytes_b


def test_runtime_timestamp_changes_but_rows_remain_stable(tmp_path: Path) -> None:
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    a = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    b = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert a["rows"] == b["rows"]
    assert a["evidence_snapshot_id"] == b["evidence_snapshot_id"]


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_aggregate_and_close_vocabularies(tmp_path: Path) -> None:
    items = [
        _release_item(item_id="dwq_clean__001"),
        _release_item(item_id="dwq_protec_002", protected_surface=True),
        _release_item(
            item_id="dwq_needhu_003",
            execution_authority=ea.DECISION_NEEDS_HUMAN,
        ),
    ]
    qp = _write_queue(tmp_path, items)
    payload = _all_clean_evidence()
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    counts = snap["counts"]
    assert counts["total"] == 3
    assert sum(counts["by_verdict"].values()) == 3
    assert counts["by_verdict"][drg.VERDICT_GO] == 1
    assert counts["by_verdict"][drg.VERDICT_NO_GO_HUMAN_NEEDED] == 2
    assert counts["human_needed"] == 2
    assert counts["protected_surface"] == 1
    assert set(counts["by_verdict"]) == set(drg.VERDICTS)
    assert set(counts["by_verdict_reason"]) == set(drg.VERDICT_REASONS)


# ---------------------------------------------------------------------------
# Validation warnings
# ---------------------------------------------------------------------------


def test_invalid_evidence_value_records_warning(tmp_path: Path) -> None:
    payload = _all_clean_evidence()
    payload["evidence"]["ci_status"]["value"] = "not_a_real_value"
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert any("evidence_ci_status_value_invalid" in w for w in snap["validation_warnings"])
    # Bad value should be coerced to "unknown".
    assert snap["rows"][0]["verdict"] == drg.VERDICT_NOT_EVALUATED


def test_unknown_evidence_extra_key_records_warning(tmp_path: Path) -> None:
    payload = {
        "evidence": {
            **_all_clean_evidence()["evidence"],
            "made_up_key": {"present": True, "value": "anything"},
        }
    }
    qp = _write_queue(tmp_path, [_release_item()])
    ep = _write_evidence(tmp_path, payload)
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert any("evidence_unknown_key_made_up_key" in w for w in snap["validation_warnings"])


def test_missing_acceptance_criteria_records_warning(tmp_path: Path) -> None:
    item = _release_item(acceptance_criteria=[])
    qp = _write_queue(tmp_path, [item])
    ep = _write_evidence(tmp_path, _all_clean_evidence())
    snap = drg.collect_snapshot(queue_artifact_path=qp, evidence_input_path=ep)
    assert any(
        "missing_acceptance_criteria" in w for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(drg.__file__).read_text(encoding="utf-8")


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
    ):
        assert forbidden not in src
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src
    assert "from requests" not in src


def _imported_module_names() -> set[str]:
    """Return the set of fully-qualified module names imported by the
    scorer module, parsed via ``ast`` so that docstring/comment
    mentions of forbidden modules do not produce false positives."""
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    """ADE core never imports dashboard/automation/broker/agent
    risk/execution/research/Intelligent Routing modules. Pinned by
    AST-level inspection so docstring mentions are safe."""
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (module == prefix or module.startswith(prefix + ".")), (
                f"forbidden import: {module}"
            )


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    # The module must not shell out — these tokens would suggest it.
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(drg)
    assert callable(drg.collect_snapshot)
    assert callable(drg.write_outputs)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(drg.SCHEMA_VERSION, str) and drg.SCHEMA_VERSION
    assert isinstance(drg.MODULE_VERSION, str) and drg.MODULE_VERSION
    assert "A9" in drg.MODULE_VERSION
