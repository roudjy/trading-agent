"""Unit tests for A23 — Merge Recommendation."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_merge_recommendation as a23


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _pr_row(
    *,
    pr_number: int = 167,
    head_sha: str = "abc1234567890abcdef1234567890abcdef12345",
    head_ref: str = "feature/foo",
    base_ref: str = "main",
    observer_classification: str = "open_clean_mergeable",
) -> dict[str, Any]:
    return {
        "pr_number": pr_number,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "base_ref": base_ref,
        "observer_classification": observer_classification,
    }


def _write_observer(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    p = tmp_path / "logs" / "development_pr_lifecycle_observer" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "development_pr_lifecycle_observer",
        "generated_at_utc": "2026-05-11T00:00:00Z",
        "rows": rows,
    }
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _write_inbox(
    tmp_path: Path,
    *,
    blocked: int = 0,
    critical: int = 0,
    needs_review: int = 0,
) -> Path:
    p = tmp_path / "logs" / "mobile_approval_inbox" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "module_version": "v0",
        "report_kind": "mobile_approval_inbox",
        "generated_at_utc": "2026-05-11T00:00:00Z",
        "counts": {
            "total": blocked + critical + needs_review,
            "blocked_attention": blocked,
            "critical_attention": critical,
            "needs_review": needs_review,
        },
        "rows": [],
    }
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_recommendation_actions_pinned_exactly() -> None:
    assert a23.RECOMMENDATION_ACTIONS == (
        "recommend_human_merge",
        "recommend_human_review",
        "recommend_no_action",
        "recommend_update_branch",
        "recommend_hold",
    )


def test_recommendation_actions_avoid_decision_verb_in_value() -> None:
    """The closed action names must not contain `approve` / `reject`
    / `deploy` as standalone verbs. `merge` is allowed only when
    prefixed with `recommend_human_` — i.e. the recommendation is to
    a human, never to an agent."""
    for action in a23.RECOMMENDATION_ACTIONS:
        lo = action.lower()
        assert "approve" not in lo, action
        assert "reject" not in lo, action
        assert "deploy" not in lo, action
        # `merge` is only allowed in `recommend_human_merge`.
        if "merge" in lo:
            assert action == "recommend_human_merge", action


def test_recommendation_reasons_pinned() -> None:
    assert a23.RECOMMENDATION_REASONS == (
        "pr_clean_and_no_blocking_inbox",
        "pr_clean_but_inbox_has_blocked_attention",
        "pr_clean_but_inbox_has_critical_attention",
        "pr_clean_but_inbox_has_needs_review",
        "pr_closed_or_merged",
        "pr_open_but_draft",
        "pr_behind_base_branch",
        "pr_blocked_or_dirty",
        "pr_unstable_checks",
        "pr_unknown_state",
        "no_upstream_signal",
        "ineligible_pr_shape",
    )


def test_validation_warnings_pinned() -> None:
    assert a23.VALIDATION_WARNINGS == (
        "pr_lifecycle_observer_absent",
        "pr_lifecycle_observer_unparseable",
        "mobile_approval_inbox_absent",
        "mobile_approval_inbox_unparseable",
        "no_open_prs",
    )


def test_recommendation_row_keys_pinned_exactly_and_ordered() -> None:
    assert a23.RECOMMENDATION_ROW_KEYS == (
        "recommendation_id",
        "pr_number",
        "head_sha",
        "head_ref",
        "base_ref",
        "observer_classification",
        "inbox_blocked_count",
        "inbox_critical_count",
        "inbox_needs_review_count",
        "recommendation_action",
        "recommendation_reason",
        "evaluated_at",
    )


def test_step5_invariants_pinned() -> None:
    assert a23.step5_implementation_allowed is False
    assert a23.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_recommendation_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        a23._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_upstream_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "development_pr_lifecycle_observer" / "latest.json"
    with pytest.raises(ValueError):
        a23._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# Decision rules — every row
# ---------------------------------------------------------------------------


def test_rule_closed_or_merged_recommends_no_action() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="closed_or_merged"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_no_action"
    assert reason == "pr_closed_or_merged"


def test_rule_draft_recommends_no_action() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_draft"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_no_action"
    assert reason == "pr_open_but_draft"


def test_rule_blocked_or_dirty_recommends_hold() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_blocked_or_dirty"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_hold"
    assert reason == "pr_blocked_or_dirty"


def test_rule_unstable_recommends_hold() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_unstable"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_hold"
    assert reason == "pr_unstable_checks"


def test_rule_behind_base_recommends_update_branch() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_behind_base"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_update_branch"
    assert reason == "pr_behind_base_branch"


def test_rule_unknown_recommends_hold() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_unknown"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_hold"
    assert reason == "pr_unknown_state"


def test_rule_clean_with_critical_inbox_recommends_human_review() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_clean_mergeable"),
        inbox_blocked_count=0,
        inbox_critical_count=1,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_human_review"
    assert reason == "pr_clean_but_inbox_has_critical_attention"


def test_rule_clean_with_blocked_inbox_recommends_human_review() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_clean_mergeable"),
        inbox_blocked_count=1,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_human_review"
    assert reason == "pr_clean_but_inbox_has_blocked_attention"


def test_rule_clean_with_needs_review_inbox_recommends_human_review() -> None:
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_clean_mergeable"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=1,
    )
    assert action == "recommend_human_review"
    assert reason == "pr_clean_but_inbox_has_needs_review"


def test_rule_clean_with_empty_inbox_recommends_human_merge() -> None:
    """The only path to recommend_human_merge: PR is clean AND
    inbox has zero attention rows. Recommendation is to a HUMAN —
    A23 never executes the merge itself."""
    action, reason = a23.evaluate_pr(
        _pr_row(observer_classification="open_clean_mergeable"),
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_human_merge"
    assert reason == "pr_clean_and_no_blocking_inbox"


def test_rule_non_dict_input_recommends_hold() -> None:
    action, reason = a23.evaluate_pr(
        "not a dict",  # type: ignore[arg-type]
        inbox_blocked_count=0,
        inbox_critical_count=0,
        inbox_needs_review_count=0,
    )
    assert action == "recommend_hold"
    assert reason == "ineligible_pr_shape"


# ---------------------------------------------------------------------------
# recommendation_id stability + head-advance invalidation
# ---------------------------------------------------------------------------


def test_recommendation_id_stable_for_same_pr_and_sha(tmp_path: Path) -> None:
    observer = _write_observer(tmp_path, [_pr_row(pr_number=42, head_sha="abc1234567890")])
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    assert snap["rows"][0]["recommendation_id"] == "mr_42_abc123456789"


def test_recommendation_id_changes_when_head_advances(tmp_path: Path) -> None:
    observer = _write_observer(
        tmp_path,
        [_pr_row(pr_number=42, head_sha="abc1234567890")],
    )
    inbox = _write_inbox(tmp_path)
    snap1 = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    id1 = snap1["rows"][0]["recommendation_id"]
    # Re-write observer with new head sha.
    observer.unlink()
    observer = _write_observer(
        tmp_path,
        [_pr_row(pr_number=42, head_sha="newdeadbeefcafe")],
    )
    snap2 = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    id2 = snap2["rows"][0]["recommendation_id"]
    assert id1 != id2


# ---------------------------------------------------------------------------
# Bounded artefact
# ---------------------------------------------------------------------------


def test_recommendation_rows_bounded(tmp_path: Path) -> None:
    rows = [_pr_row(pr_number=i, head_sha=f"sha{i:012d}") for i in range(1, 100)]
    observer = _write_observer(tmp_path, rows)
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    assert len(snap["rows"]) <= a23.MAX_RECOMMENDATION_ROWS


# ---------------------------------------------------------------------------
# Wrapper shape + counts
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    observer = _write_observer(tmp_path, [_pr_row()])
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "pr_observer_artifact_path",
        "pr_observer_artifact_available",
        "inbox_artifact_path",
        "inbox_artifact_available",
        "max_recommendation_rows",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "pr_lifecycle_observer_module_version",
        "mobile_approval_inbox_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    observer = _write_observer(tmp_path, [_pr_row()])
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    inv = snap["discipline_invariants"]
    assert inv["calls_gh_cli"] is False
    assert inv["merges_or_deploys"] is False
    assert inv["mints_approval_token"] is False
    assert inv["verifies_approval_token"] is False
    assert inv["executes_approve_or_reject"] is False
    assert inv["registers_flask_blueprint"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"
    assert inv["no_approval_from_notification_click_alone"] is True


def test_counts_aggregate_by_action(tmp_path: Path) -> None:
    rows = [
        _pr_row(pr_number=1, head_sha="aaa1", observer_classification="open_clean_mergeable"),
        _pr_row(pr_number=2, head_sha="aaa2", observer_classification="open_blocked_or_dirty"),
        _pr_row(pr_number=3, head_sha="aaa3", observer_classification="open_draft"),
        _pr_row(pr_number=4, head_sha="aaa4", observer_classification="open_behind_base"),
    ]
    observer = _write_observer(tmp_path, rows)
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
    )
    by_action = snap["counts"]["by_recommendation_action"]
    assert by_action["recommend_human_merge"] == 1
    assert by_action["recommend_hold"] == 1
    assert by_action["recommend_no_action"] == 1
    assert by_action["recommend_update_branch"] == 1


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    observer = _write_observer(tmp_path, [_pr_row()])
    inbox = _write_inbox(tmp_path)
    a = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    b = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=inbox,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_absent_observer_yields_warning(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "development_pr_lifecycle_observer" / "latest.json"
    inbox = _write_inbox(tmp_path)
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=missing,
        inbox_artifact_path=inbox,
        generated_at_utc="2026-05-11T00:00:00Z",
    )
    assert "pr_lifecycle_observer_absent" in snap["validation_warnings"]
    assert snap["pr_observer_artifact_available"] is False
    assert snap["rows"] == []


def test_absent_inbox_yields_warning(tmp_path: Path) -> None:
    observer = _write_observer(tmp_path, [])
    missing = tmp_path / "logs" / "mobile_approval_inbox" / "latest.json"
    snap = a23.collect_snapshot(
        pr_observer_artifact_path=observer,
        inbox_artifact_path=missing,
    )
    assert "mobile_approval_inbox_absent" in snap["validation_warnings"]
    assert snap["inbox_artifact_available"] is False


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a23.__file__).read_text(encoding="utf-8")


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


def test_no_flask_blueprint_registration() -> None:
    src = _module_source()
    forbidden = (
        ".register_blueprint(",
        "add_url_rule(",
        "from flask",
        "import flask",
    )
    for s in forbidden:
        assert s not in src, s


def test_no_gh_cli_invocation() -> None:
    """A23 must NEVER spawn `gh` or any other CLI. Source-text scan
    rules out any literal hint of such a call."""
    src = _module_source()
    forbidden = (
        '"gh "',
        "'gh '",
        '"gh"',
        "'gh'",
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
    )
    for s in forbidden:
        assert s not in src, s


def test_module_imports_cleanly() -> None:
    importlib.reload(a23)
    assert callable(a23.collect_snapshot)
    assert callable(a23.evaluate_pr)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(a23)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "development_merge_recommendation.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_autonomous_merge() -> None:
    text = _doc_text().lower()
    assert "never merges" in text
    assert "never calls" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
    )


def test_doc_states_a23_never_calls_gh() -> None:
    text = _doc_text().lower()
    assert "never calls `gh`" in text or "never calls gh" in text


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
        raw = text[start:end].lower()
        cleaned = re.sub(r"\n\s*>\s*", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned)
        assert "permanently disabled" in cleaned
