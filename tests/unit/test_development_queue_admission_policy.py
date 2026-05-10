"""Unit tests for A17 — Queue Admission Policy."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_queue_admission_policy as qap
from reporting import execution_authority as ea


REPO_ROOT = Path(__file__).resolve().parents[2]


def _eligible_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "candidate_id": "syn_001",
        "title": "Synthetic eligible candidate",
        "source_document": "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        "source_kind": "operating_manual",
        "roadmap_phase": "v3.15.16",
        "candidate_kind": "docs",
        "category": "docs",
        "required_agent_role": "planner",
        "risk_level": "LOW",
        "target_path": "docs/governance/agent_run_summaries/syn.md",
        "upstream_intake_status": "eligible",
        "upstream_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "reclassified_execution_authority_decision": ea.DECISION_AUTO_ALLOWED,
        "classification_drift": False,
        "human_needed": False,
        "human_needed_reason": "none",
        "decision_state": "eligible",
        "already_in_seed_jsonl": False,
        "already_in_delegation_seed": False,
    }
    base.update(overrides)
    return base


def _write_promotion_artifact(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    p = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    p.parent.mkdir(parents=True)
    payload = {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "development_intake_promotion",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "step5_enabled_substage": "none",
        "step5_implementation_allowed": False,
        "rows": rows,
        "counts": {"total": len(rows)},
    }
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_admission_decisions_pinned_exactly() -> None:
    assert qap.ADMISSION_DECISIONS == (
        "admissible",
        "needs_human",
        "blocked",
        "duplicate_of_existing",
        "not_eligible_upstream",
    )


def test_admission_reasons_pinned_exactly() -> None:
    assert qap.ADMISSION_REASONS == (
        "auto_allowed_low_risk_eligible_promotion",
        "needs_human_authority_decision",
        "needs_human_unknown_or_invalid_risk",
        "needs_human_classification_drift",
        "needs_human_protected_target_path",
        "blocked_authority_permanently_denied",
        "blocked_classification_drift_to_denied",
        "already_in_seed_jsonl",
        "already_in_delegation_seed",
        "upstream_intake_status_not_eligible",
        "upstream_decision_state_not_eligible",
    )


def test_promotion_targets_pinned() -> None:
    assert qap.PROMOTION_TARGETS == (
        "none",
        "development_work_queue",
        "development_delegation",
    )


def test_admission_schema_keys_pinned_exactly_and_ordered() -> None:
    assert qap.ADMISSION_SCHEMA_KEYS == (
        "candidate_id",
        "title",
        "source_document",
        "source_kind",
        "roadmap_phase",
        "candidate_kind",
        "required_agent_role",
        "risk_level",
        "target_path",
        "upstream_intake_status",
        "upstream_decision_state",
        "upstream_execution_authority_decision",
        "reclassified_execution_authority_decision",
        "classification_drift",
        "human_needed",
        "human_needed_reason",
        "admission_decision",
        "admission_reason",
        "would_target_lane",
        "already_in_seed_jsonl",
        "already_in_delegation_seed",
        "policy_version",
        "evaluated_at",
    )


def test_step5_invariants_pinned() -> None:
    assert qap.step5_implementation_allowed is False
    assert qap.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_policy_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        qap._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_other_logs_subdir(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    with pytest.raises(ValueError):
        qap._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Decision rules — every priority row
# ---------------------------------------------------------------------------


def test_eligible_low_risk_auto_allowed_is_admissible() -> None:
    decision, reason = qap.evaluate_promotion_record(_eligible_row())
    assert decision == "admissible"
    assert reason == "auto_allowed_low_risk_eligible_promotion"


def test_already_in_seed_overrides_admissible() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(already_in_seed_jsonl=True)
    )
    assert decision == "duplicate_of_existing"
    assert reason == "already_in_seed_jsonl"


def test_already_in_delegation_overrides_admissible() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(already_in_delegation_seed=True)
    )
    assert decision == "duplicate_of_existing"
    assert reason == "already_in_delegation_seed"


def test_permanently_denied_upstream_blocks() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(
            upstream_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
            reclassified_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
        )
    )
    assert decision == "blocked"
    assert reason == "blocked_authority_permanently_denied"


def test_classification_drift_to_denied_blocks() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(
            upstream_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
            reclassified_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
            classification_drift=True,
        )
    )
    assert decision == "blocked"


def test_needs_human_upstream_decision() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(
            upstream_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
            reclassified_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
        )
    )
    assert decision == "needs_human"
    assert reason in (
        "needs_human_authority_decision",
        "needs_human_protected_target_path",
    )


def test_needs_human_protected_target_path() -> None:
    """A target under canonical_roadmap classifies as NEEDS_HUMAN
    via the surrounding execution_authority machinery."""
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(
            target_path="docs/roadmap/Roadmap v6.md",
            risk_level="MEDIUM",
            upstream_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
            reclassified_execution_authority_decision=ea.DECISION_NEEDS_HUMAN,
        )
    )
    assert decision == "needs_human"
    assert reason == "needs_human_protected_target_path"


def test_human_needed_true_overrides() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(human_needed=True)
    )
    assert decision == "needs_human"
    assert reason == "needs_human_authority_decision"


def test_classification_drift_non_denied_needs_human() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(
            classification_drift=True,
            reclassified_execution_authority_decision=ea.DECISION_AUTO_ALLOWED,
        )
    )
    assert decision == "needs_human"
    assert reason == "needs_human_classification_drift"


def test_decision_state_not_eligible() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(decision_state="pending")
    )
    assert decision == "not_eligible_upstream"
    assert reason == "upstream_decision_state_not_eligible"


def test_intake_status_not_eligible() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(upstream_intake_status="proposed")
    )
    assert decision == "not_eligible_upstream"
    assert reason == "upstream_intake_status_not_eligible"


def test_unknown_risk_is_needs_human() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(risk_level="UNKNOWN")
    )
    assert decision == "needs_human"
    assert reason == "needs_human_unknown_or_invalid_risk"


def test_invalid_risk_is_needs_human() -> None:
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(risk_level="EXTREME")
    )
    assert decision == "needs_human"
    assert reason == "needs_human_unknown_or_invalid_risk"


def test_default_deny_for_medium_risk_auto_allowed() -> None:
    """Even AUTO_ALLOWED + eligible-state, MEDIUM risk falls through
    to the default-deny needs_human row."""
    decision, reason = qap.evaluate_promotion_record(
        _eligible_row(risk_level="MEDIUM")
    )
    assert decision == "needs_human"


def test_non_dict_input_returns_not_eligible() -> None:
    decision, reason = qap.evaluate_promotion_record("not a dict")  # type: ignore[arg-type]
    assert decision == "not_eligible_upstream"


# ---------------------------------------------------------------------------
# Snapshot integration
# ---------------------------------------------------------------------------


def test_real_a15_candidate_lands_admissible(tmp_path: Path) -> None:
    """Mirror the live A15 candidate shape and confirm admissible."""
    real = _eligible_row(
        candidate_id="qre_v3_15_16_addendum_source_manifest_001",
        title="Draft diagnostic-source manifest operating surface for Roadmap v6 Addendum §9.3 fields",
        target_path=(
            "docs/governance/agent_run_summaries/"
            "qre_addendum_source_manifest_001.md"
        ),
    )
    artifact = _write_promotion_artifact(tmp_path, [real])
    snap = qap.collect_snapshot(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["counts"]["admissible"] == 1
    row = snap["rows"][0]
    assert row["admission_decision"] == "admissible"
    assert row["admission_reason"] == "auto_allowed_low_risk_eligible_promotion"
    assert row["would_target_lane"] == "development_work_queue"
    assert row["policy_version"] == qap.MODULE_VERSION


def test_would_target_lane_only_set_for_admissible(tmp_path: Path) -> None:
    rows = [
        _eligible_row(candidate_id="ok_1"),
        _eligible_row(candidate_id="hn_1", human_needed=True),
        _eligible_row(
            candidate_id="bl_1",
            upstream_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
            reclassified_execution_authority_decision=ea.DECISION_PERMANENTLY_DENIED,
        ),
    ]
    artifact = _write_promotion_artifact(tmp_path, rows)
    snap = qap.collect_snapshot(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    by_id = {r["candidate_id"]: r for r in snap["rows"]}
    assert by_id["ok_1"]["would_target_lane"] == "development_work_queue"
    assert by_id["hn_1"]["would_target_lane"] == "none"
    assert by_id["bl_1"]["would_target_lane"] == "none"


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    artifact = _write_promotion_artifact(tmp_path, [])
    snap = qap.collect_snapshot(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "promotion_artifact_path",
        "promotion_artifact_available",
        "policy_version",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "intake_promotion_module_version",
        "execution_authority_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    artifact = _write_promotion_artifact(tmp_path, [])
    snap = qap.collect_snapshot(promotion_artifact_path=artifact)
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    artifact = _write_promotion_artifact(tmp_path, [_eligible_row()])
    snap_a = qap.collect_snapshot(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    snap_b = qap.collect_snapshot(
        promotion_artifact_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert (
        json.dumps(snap_a, sort_keys=True, indent=2).encode("utf-8")
        == json.dumps(snap_b, sort_keys=True, indent=2).encode("utf-8")
    )


def test_promotion_artifact_absent_handled(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.json"
    snap = qap.collect_snapshot(
        promotion_artifact_path=missing,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["promotion_artifact_available"] is False
    assert snap["rows"] == []
    assert snap["note"] == "promotion_artifact_absent"


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(qap.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
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
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_does_not_open_seed_jsonl_for_writing() -> None:
    """Defense-in-depth: A17 must not contain code that opens a seed
    file for writing or appending. Documentation references to
    `generated_seed.jsonl` (where the doc explains we DON'T write to
    it) are explicitly tolerated. This test scans for code-shaped
    write/append patterns only."""
    src = _module_source()
    forbidden_code_patterns = (
        # Write/append flags against seed paths.
        "seed.jsonl\", \"w",
        "seed.jsonl', 'w",
        "seed.jsonl\", \"a",
        "seed.jsonl', 'a",
        "delegation_seed.jsonl\", \"w",
        "delegation_seed.jsonl', 'w",
        "delegation_seed.jsonl\", \"a",
        "delegation_seed.jsonl', 'a",
        # Direct call shapes that would imply writing.
        "SEED_PATH.write_text",
        "SEED_PATH.open(\"w",
        "DELEGATION_SEED_PATH.write_text",
        "DELEGATION_SEED_PATH.open(\"w",
        "GENERATED_SEED_PATH",
    )
    for s in forbidden_code_patterns:
        assert s not in src, s


def test_module_imports_cleanly() -> None:
    importlib.reload(qap)
    assert callable(qap.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(qap)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "queue_admission_policy.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_seed_writes() -> None:
    text = _doc_text().lower()
    assert "no automatic queue write" in text or "no automatic queue promotion" in text or "writes nothing" in text
    assert "operator-authored" in text


def test_doc_states_a18_is_operator_gated() -> None:
    text = _doc_text().lower()
    assert "a18" in text
    assert "operator" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window
