from __future__ import annotations

from pathlib import Path

from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_QRE,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCH_006_DOC = REPO_ROOT / "docs" / "architecture" / (
    "ARCH-006-package-extraction-readiness-decision.md"
)

DECISION_VALUES = (
    "GO_FIRST_EXTRACTION_SLICE",
    "CONDITIONAL_GO_AFTER_BLOCKER_FIX",
    "NO_GO_RETURN_TO_QRE_FEATURE_TRACK",
    "NO_GO_BLOCKED_BY_ARCHITECTURE_RISK",
)


def test_arch_006_uses_one_closed_vocab_decision_and_one_next_action() -> None:
    text = ARCH_006_DOC.read_text(encoding="utf-8")

    assert [value for value in DECISION_VALUES if value in text] == [
        "GO_FIRST_EXTRACTION_SLICE"
    ]
    assert text.count("Recommended next action:") == 1
    assert (
        "Recommended next action: start first package extraction slice: extract\n"
        "`reporting/control_plane_qre_adapter_contract.py`"
    ) in text
    assert "No further ARCH unit is recommended." in text


def test_arch_006_documents_no_extraction_or_runtime_behavior_change() -> None:
    text = ARCH_006_DOC.read_text(encoding="utf-8")

    required_phrases = (
        "This unit performs no package extraction.",
        "It does not move files, rename\npackages, change runtime behavior",
        "frozen contracts unchanged",
        "protected paths untouched",
        "no dashboard mutation routes",
        "no QRE strategy definitions, registry wiring, research orchestration, or\n"
        "  authority semantics may change.",
    )

    for phrase in required_phrases:
        assert phrase in text


def test_arch_006_readiness_gates_are_represented_in_scanner_summary() -> None:
    summary = report_to_summary_dict(scan_repo(REPO_ROOT))

    legacy_by_rule_and_domain = {
        (row["rule"], row["source_domain"], row["target_domain"]): row[
            "finding_count"
        ]
        for row in summary["legacy_finding_categories"]
    }
    legacy_by_source_root = {
        (row["source_root"], row["target_root"], row["rule"]): row["finding_count"]
        for row in summary["legacy_source_target_roots"]
    }

    assert summary["forbidden_edge_count"] == 0
    assert legacy_by_rule_and_domain[
        ("control-plane-to-qre", DOMAIN_CONTROL_PLANE, DOMAIN_QRE)
    ] == 18
    assert legacy_by_rule_and_domain[("ade-to-qre", DOMAIN_ADE, DOMAIN_QRE)] == 2
    assert legacy_by_rule_and_domain[
        ("mixed-domain", DOMAIN_QRE, DOMAIN_EXECUTION)
    ] == 11
    assert legacy_by_source_root[("dashboard", "research", "control-plane-to-qre")] == 16
    assert legacy_by_source_root[("dashboard", "data", "control-plane-to-qre")] == 2
    assert legacy_by_source_root[("reporting", "research", "ade-to-qre")] == 2


def test_arch_006_first_candidate_has_no_domain_or_forbidden_edges() -> None:
    report = scan_repo(REPO_ROOT)

    candidate_edges = [
        edge
        for edge in report.edges
        if edge.source_module == "reporting.control_plane_qre_adapter_contract"
    ]
    candidate_forbidden = [
        finding
        for finding in report.forbidden_edges
        if finding.source_module == "reporting.control_plane_qre_adapter_contract"
    ]
    candidate_legacy = [
        finding
        for finding in report.legacy_edges
        if finding.source_module == "reporting.control_plane_qre_adapter_contract"
    ]

    assert [(edge.target_module, edge.target_domain) for edge in candidate_edges] == [
        ("__future__", "unknown"),
        ("dataclasses", "unknown"),
        ("typing", "unknown"),
    ]
    assert candidate_forbidden == []
    assert candidate_legacy == []
