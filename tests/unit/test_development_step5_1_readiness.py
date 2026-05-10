"""Unit tests for A20 — Step 5.1 readiness report."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_step5_1_readiness as a20


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_readiness_overall_pinned_exactly() -> None:
    assert a20.READINESS_OVERALL == (
        "not_ready",
        "preconditions_partially_met",
        "ready_pending_operator_authorization",
    )


def test_readiness_overall_never_implies_autonomous_flip() -> None:
    """The maximally-positive value must STILL require operator
    authorisation. There is no value that says "ready" /"approved"
    or anything that could be misread as autonomous green-light."""
    forbidden_values = {
        "ready",
        "approved",
        "authorised",
        "authorized",
        "auto_enable",
        "auto_flip",
        "go",
    }
    assert not (forbidden_values & set(a20.READINESS_OVERALL))


def test_check_statuses_pinned_exactly() -> None:
    assert a20.CHECK_STATUSES == ("pass", "fail", "not_applicable")


def test_check_ids_pinned_exactly() -> None:
    assert a20.CHECK_IDS == (
        "step5_implementation_allowed_currently_false",
        "step5_enabled_substage_currently_none",
        "intake_bridge_artifact_present",
        "promotion_artifact_present",
        "admission_artifact_present",
        "progress_artifact_present",
        "step5_history_present",
        "at_least_one_eligible_intake_candidate",
        "at_least_one_admissible_admission_row",
        "at_least_one_step5_plan_emitted_cycle",
        "no_classification_drift_in_promotion_rows",
        "no_blocked_admission_rows",
        "no_phase_marked_complete_by_a19",
    )


def test_check_row_keys_pinned_exactly() -> None:
    assert a20.CHECK_ROW_KEYS == (
        "check_id",
        "status",
        "value",
        "threshold",
        "note",
    )


def test_step5_invariants_pinned() -> None:
    assert a20.step5_implementation_allowed is False
    assert a20.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_readiness_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        a20._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# A20 never flips Step 5 invariants
# ---------------------------------------------------------------------------


def test_module_source_does_not_set_step5_allowed_true() -> None:
    """The literal assignment ``step5_implementation_allowed = True``
    must NOT appear anywhere in this module's executable code.
    Documentation references in docstrings/comments are tolerated
    (the docstring legitimately documents what the module does NOT
    do); the test scans actual AST assignments to rule out a real
    code-path that flips the cap."""
    import ast

    src = Path(a20.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # Module-level Final annotations like
        # ``step5_implementation_allowed: Final[bool] = False`` are
        # the only legitimate assignments.
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if (
                isinstance(target, ast.Name)
                and target.id == "step5_implementation_allowed"
            ):
                # Allowed only when the assigned value is the literal False.
                value = node.value
                assert isinstance(value, ast.Constant), (
                    "step5_implementation_allowed must be assigned a literal"
                )
                assert value.value is False, (
                    f"step5_implementation_allowed must be False; "
                    f"found: {value.value!r}"
                )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "step5_implementation_allowed"
                ):
                    value = node.value
                    assert isinstance(value, ast.Constant), (
                        "step5_implementation_allowed must be assigned a literal"
                    )
                    assert value.value is False, (
                        f"step5_implementation_allowed must be False; "
                        f"found: {value.value!r}"
                    )


def test_module_source_does_not_set_substage_enabled() -> None:
    """The module must not contain code that assigns
    STEP5_ENABLED_SUBSTAGE to anything other than "none"."""
    src = Path(a20.__file__).read_text(encoding="utf-8")
    # Allow the literal `STEP5_ENABLED_SUBSTAGE: Final[str] = "none"`.
    # Anything else assigning a non-"none" string is forbidden.
    forbidden = (
        'STEP5_ENABLED_SUBSTAGE = "5.1"',
        'STEP5_ENABLED_SUBSTAGE = "5.2"',
        "STEP5_ENABLED_SUBSTAGE = '5.1'",
        "STEP5_ENABLED_SUBSTAGE = '5.2'",
    )
    for pattern in forbidden:
        assert pattern not in src


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(a20)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Snapshot + check coverage
# ---------------------------------------------------------------------------


def _make_paths(tmp_path: Path) -> dict[str, Path]:
    intake = tmp_path / "logs" / "development_roadmap_intake" / "latest.json"
    promo = tmp_path / "logs" / "development_intake_promotion" / "latest.json"
    adm = tmp_path / "logs" / "development_queue_admission_policy" / "latest.json"
    progress = tmp_path / "logs" / "development_roadmap_progress" / "latest.json"
    hist = tmp_path / "logs" / "step5_plan" / "history.jsonl"
    for p in (intake, promo, adm, progress, hist):
        p.parent.mkdir(parents=True, exist_ok=True)
    return {
        "intake": intake,
        "promo": promo,
        "adm": adm,
        "progress": progress,
        "hist": hist,
    }


def _wj(p: Path, payload: dict[str, Any]) -> None:
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _wjsonl(p: Path, entries: list[dict[str, Any]]) -> None:
    p.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )


def test_check_coverage_matches_check_ids_set(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    seen = {c["check_id"] for c in snap["checks"]}
    assert seen == set(a20.CHECK_IDS)


def test_no_upstream_yields_not_ready(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    # The two "currently false / none" checks pass; everything
    # downstream fails — so result is "preconditions_partially_met".
    assert snap["readiness_overall"] in (
        "not_ready",
        "preconditions_partially_met",
    )


def test_full_signal_yields_ready_pending_operator_authorization(
    tmp_path: Path,
) -> None:
    paths = _make_paths(tmp_path)
    _wj(
        paths["intake"],
        {
            "candidates": [
                {"candidate_id": "c1", "intake_status": "eligible"},
            ],
        },
    )
    _wj(
        paths["promo"],
        {
            "rows": [
                {
                    "candidate_id": "c1",
                    "decision_state": "eligible",
                    "classification_drift": False,
                },
            ],
        },
    )
    _wj(
        paths["adm"],
        {
            "rows": [
                {"candidate_id": "c1", "admission_decision": "admissible"},
            ],
        },
    )
    _wj(
        paths["progress"],
        {
            "rows": [
                {"roadmap_phase": "p1", "phase_progress_state": "planning_active"},
            ],
        },
    )
    _wjsonl(paths["hist"], [{"source_id": "c1", "outcome": "plan_emitted"}])
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert snap["readiness_overall"] == "ready_pending_operator_authorization"
    # Even when ready, A20 emits the live invariant values intact.
    assert snap["current_step5_implementation_allowed"] is False
    assert snap["current_step5_enabled_substage"] == "none"


def test_blocked_admission_row_fails_quality_check(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _wj(paths["intake"], {"candidates": []})
    _wj(paths["promo"], {"rows": []})
    _wj(
        paths["adm"],
        {
            "rows": [
                {"candidate_id": "c1", "admission_decision": "blocked"},
            ],
        },
    )
    _wj(paths["progress"], {"rows": []})
    _wjsonl(paths["hist"], [])
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
    )
    by_id = {c["check_id"]: c for c in snap["checks"]}
    assert by_id["no_blocked_admission_rows"]["status"] == "fail"
    assert by_id["no_blocked_admission_rows"]["value"] == 1


def test_classification_drift_fails_quality_check(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    _wj(paths["intake"], {"candidates": []})
    _wj(
        paths["promo"],
        {
            "rows": [
                {
                    "candidate_id": "c1",
                    "decision_state": "blocked",
                    "classification_drift": True,
                },
            ],
        },
    )
    _wj(paths["adm"], {"rows": []})
    _wj(paths["progress"], {"rows": []})
    _wjsonl(paths["hist"], [])
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
    )
    by_id = {c["check_id"]: c for c in snap["checks"]}
    assert by_id["no_classification_drift_in_promotion_rows"]["status"] == "fail"


def test_phase_complete_fails_quality_check(tmp_path: Path) -> None:
    """A19 NEVER assigns 'complete'; if A20 sees it in upstream, that
    is a defense-in-depth fail."""
    paths = _make_paths(tmp_path)
    _wj(paths["intake"], {"candidates": []})
    _wj(paths["promo"], {"rows": []})
    _wj(paths["adm"], {"rows": []})
    _wj(
        paths["progress"],
        {
            "rows": [
                {"roadmap_phase": "p1", "phase_progress_state": "complete"},
            ],
        },
    )
    _wjsonl(paths["hist"], [])
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
    )
    by_id = {c["check_id"]: c for c in snap["checks"]}
    assert by_id["no_phase_marked_complete_by_a19"]["status"] == "fail"


def test_step5_invariant_checks_always_reflect_live_constants(
    tmp_path: Path,
) -> None:
    from reporting import development_step5_loop as dsl

    paths = _make_paths(tmp_path)
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
    )
    by_id = {c["check_id"]: c for c in snap["checks"]}
    inv1 = by_id["step5_implementation_allowed_currently_false"]
    inv2 = by_id["step5_enabled_substage_currently_none"]
    assert inv1["value"] is dsl.step5_implementation_allowed
    assert inv2["value"] == dsl.STEP5_ENABLED_SUBSTAGE


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "current_step5_implementation_allowed",
        "current_step5_enabled_substage",
        "readiness_overall",
        "sources_read",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "checks",
        "intake_promotion_module_version",
        "admission_module_version",
        "progress_module_version",
        "step5_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    snap = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
    )
    inv = snap["discipline_invariants"]
    assert inv["flips_step5_implementation_allowed"] is False
    assert inv["changes_step5_enabled_substage"] is False
    assert inv["marks_any_phase_complete"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    paths = _make_paths(tmp_path)
    snap_a = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    snap_b = a20.collect_snapshot(
        intake_artifact_path=paths["intake"],
        promotion_artifact_path=paths["promo"],
        admission_artifact_path=paths["adm"],
        progress_artifact_path=paths["progress"],
        step5_history_path=paths["hist"],
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert (
        json.dumps(snap_a, sort_keys=True, indent=2)
        == json.dumps(snap_b, sort_keys=True, indent=2)
    )


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a20.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_or_network() -> None:
    src = _module_source()
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    )
    for s in forbidden:
        assert s not in src, s


def test_no_dashboard_or_frontend_imports() -> None:
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


def test_module_imports_cleanly() -> None:
    importlib.reload(a20)
    assert callable(a20.collect_snapshot)


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "development_step5_1_readiness.md"
    ).read_text(encoding="utf-8")


def test_doc_states_a20_is_reports_only() -> None:
    text = _doc_text().lower()
    assert "reports only" in text or "report — not the decision" in text


def test_doc_states_cap_flip_remains_operator_authored() -> None:
    text = _doc_text().lower()
    assert "operator-authored" in text
    assert "step5_implementation_allowed" in _doc_text()


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
