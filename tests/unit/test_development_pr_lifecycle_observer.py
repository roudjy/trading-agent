"""Unit tests for A22 — Draft PR lifecycle observer."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_pr_lifecycle_observer as a22


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_digest(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return p


def _digest_with_prs(prs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.17",
        "report_kind": "github_pr_lifecycle_digest",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "provider_status": "available",
        "prs": prs,
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_pr_states_pinned_exactly() -> None:
    assert a22.PR_STATES == ("OPEN", "CLOSED", "MERGED", "DRAFT", "UNKNOWN")


def test_merge_state_statuses_pinned_exactly() -> None:
    assert a22.MERGE_STATE_STATUSES == (
        "BEHIND",
        "BLOCKED",
        "CLEAN",
        "DIRTY",
        "DRAFT",
        "HAS_HOOKS",
        "UNKNOWN",
        "UNSTABLE",
    )


def test_observer_classifications_pinned_exactly() -> None:
    assert a22.OBSERVER_CLASSIFICATIONS == (
        "open_clean_mergeable",
        "open_blocked_or_dirty",
        "open_behind_base",
        "open_draft",
        "open_unstable",
        "open_unknown",
        "closed_or_merged",
        "ineligible_shape",
    )


def test_pr_row_keys_pinned_exactly_and_ordered() -> None:
    assert a22.PR_ROW_KEYS == (
        "pr_number",
        "title",
        "head_ref",
        "head_sha",
        "base_ref",
        "state",
        "is_draft",
        "merge_state_status",
        "mergeable",
        "checks_summary",
        "author_login",
        "is_dependabot",
        "observer_classification",
        "url",
        "created_at",
        "updated_at",
    )


def test_validation_warnings_pinned() -> None:
    assert a22.VALIDATION_WARNINGS == (
        "upstream_digest_absent",
        "upstream_digest_unparseable",
        "upstream_provider_not_available",
        "upstream_pr_record_invalid",
    )


def test_step5_invariants_pinned() -> None:
    assert a22.step5_implementation_allowed is False
    assert a22.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_observer_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        a22._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_upstream_gh_lifecycle_path(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    with pytest.raises(ValueError):
        a22._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# classify_pr — every merge_state_status row
# ---------------------------------------------------------------------------


def test_classify_clean_open_is_clean_mergeable() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "CLEAN"})
        == "open_clean_mergeable"
    )


def test_classify_blocked_is_blocked_or_dirty() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "BLOCKED"})
        == "open_blocked_or_dirty"
    )


def test_classify_dirty_is_blocked_or_dirty() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "DIRTY"})
        == "open_blocked_or_dirty"
    )


def test_classify_has_hooks_is_blocked_or_dirty() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "HAS_HOOKS"})
        == "open_blocked_or_dirty"
    )


def test_classify_behind_is_behind_base() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "BEHIND"})
        == "open_behind_base"
    )


def test_classify_draft_via_is_draft() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "is_draft": True})
        == "open_draft"
    )


def test_classify_draft_via_merge_state() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "DRAFT"})
        == "open_draft"
    )


def test_classify_unstable() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "UNSTABLE"})
        == "open_unstable"
    )


def test_classify_unknown() -> None:
    assert (
        a22.classify_pr({"state": "OPEN", "merge_state_status": "UNKNOWN"})
        == "open_unknown"
    )


def test_classify_closed() -> None:
    assert (
        a22.classify_pr({"state": "CLOSED", "merge_state_status": "CLEAN"})
        == "closed_or_merged"
    )


def test_classify_merged() -> None:
    assert (
        a22.classify_pr({"state": "MERGED", "merge_state_status": "CLEAN"})
        == "closed_or_merged"
    )


def test_classify_non_dict_is_ineligible() -> None:
    assert a22.classify_pr("not a dict") == "ineligible_shape"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Field coercion (camelCase → snake_case)
# ---------------------------------------------------------------------------


def test_camelcase_upstream_fields_coerce(tmp_path: Path) -> None:
    digest = _digest_with_prs(
        [
            {
                "number": 167,
                "title": "Synthetic PR",
                "headRefName": "feature/foo",
                "headRefOid": "abc1234567890abcdef1234567890abcdef12345",
                "baseRefName": "main",
                "state": "OPEN",
                "isDraft": False,
                "mergeStateStatus": "CLEAN",
                "author": {"login": "operator"},
                "createdAt": "2026-05-10T00:00:00Z",
                "updatedAt": "2026-05-10T00:00:00Z",
                "url": "https://github.com/x/y/pull/167",
            }
        ]
    )
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(
        upstream_digest_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert len(snap["rows"]) == 1
    row = snap["rows"][0]
    assert set(row.keys()) == set(a22.PR_ROW_KEYS)
    assert row["pr_number"] == 167
    assert row["head_ref"] == "feature/foo"
    assert row["head_sha"].startswith("abc1234567890abcdef")
    assert row["state"] == "OPEN"
    assert row["merge_state_status"] == "CLEAN"
    assert row["author_login"] == "operator"
    assert row["is_dependabot"] is False
    assert row["observer_classification"] == "open_clean_mergeable"


def test_dependabot_author_detected(tmp_path: Path) -> None:
    digest = _digest_with_prs(
        [
            {
                "number": 99,
                "state": "OPEN",
                "mergeStateStatus": "CLEAN",
                "author": {"login": "dependabot[bot]"},
            }
        ]
    )
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(upstream_digest_path=artifact)
    assert snap["rows"][0]["is_dependabot"] is True
    assert snap["counts"]["dependabot_count"] == 1


# ---------------------------------------------------------------------------
# Upstream-error paths
# ---------------------------------------------------------------------------


def test_absent_digest_emits_warning(tmp_path: Path) -> None:
    missing = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    snap = a22.collect_snapshot(
        upstream_digest_path=missing,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert "upstream_digest_absent" in snap["validation_warnings"]
    assert snap["upstream_digest_available"] is False
    assert snap["rows"] == []


def test_unparseable_digest_emits_warning(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "github_pr_lifecycle" / "latest.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("not json", encoding="utf-8")
    snap = a22.collect_snapshot(upstream_digest_path=bad)
    assert "upstream_digest_absent" in snap["validation_warnings"] or (
        "upstream_digest_unparseable" in snap["validation_warnings"]
    )
    assert snap["rows"] == []


def test_provider_not_available_emits_warning(tmp_path: Path) -> None:
    digest = {
        "schema_version": 1,
        "report_kind": "github_pr_lifecycle_digest",
        "generated_at_utc": "2026-05-10T00:00:00Z",
        "provider_status": "not_available",
        "prs": [],
    }
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(upstream_digest_path=artifact)
    assert "upstream_provider_not_available" in snap["validation_warnings"]


def test_invalid_pr_record_emits_warning(tmp_path: Path) -> None:
    digest = _digest_with_prs(["not a dict"])  # type: ignore[list-item]
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(upstream_digest_path=artifact)
    assert any(
        "upstream_pr_record_invalid" in w for w in snap["validation_warnings"]
    )


# ---------------------------------------------------------------------------
# Counts + determinism
# ---------------------------------------------------------------------------


def test_counts_aggregate_per_classification(tmp_path: Path) -> None:
    digest = _digest_with_prs(
        [
            {"number": 1, "state": "OPEN", "mergeStateStatus": "CLEAN"},
            {"number": 2, "state": "OPEN", "mergeStateStatus": "BLOCKED"},
            {"number": 3, "state": "OPEN", "mergeStateStatus": "BEHIND"},
            {"number": 4, "state": "OPEN", "isDraft": True},
            {"number": 5, "state": "MERGED"},
        ]
    )
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(upstream_digest_path=artifact)
    counts = snap["counts"]
    assert counts["total"] == 5
    assert counts["open_clean_mergeable"] == 1
    assert counts["open_blocked_or_dirty"] == 1
    assert counts["open_behind_base"] == 1
    assert counts["open_draft"] == 1
    assert counts["closed_or_merged"] == 1
    assert counts["open_total"] == 4


def test_determinism_with_injected_timestamp(tmp_path: Path) -> None:
    digest = _digest_with_prs(
        [
            {"number": 1, "state": "OPEN", "mergeStateStatus": "CLEAN"},
        ]
    )
    artifact = _write_digest(tmp_path, digest)
    a = a22.collect_snapshot(
        upstream_digest_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    b = a22.collect_snapshot(
        upstream_digest_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    assert (
        json.dumps(a, sort_keys=True, indent=2)
        == json.dumps(b, sort_keys=True, indent=2)
    )


def test_snapshot_top_level_keys(tmp_path: Path) -> None:
    digest = _digest_with_prs([])
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(
        upstream_digest_path=artifact,
        generated_at_utc="2026-05-10T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "step5_enabled_substage",
        "step5_implementation_allowed",
        "upstream_digest_path",
        "upstream_digest_available",
        "upstream_provider_status",
        "upstream_module_version",
        "note",
        "validation_warnings",
        "vocabularies",
        "counts",
        "rows",
        "github_pr_lifecycle_module_version",
        "discipline_invariants",
    }
    assert set(snap.keys()) == expected


def test_discipline_invariants_present(tmp_path: Path) -> None:
    digest = _digest_with_prs([])
    artifact = _write_digest(tmp_path, digest)
    snap = a22.collect_snapshot(upstream_digest_path=artifact)
    inv = snap["discipline_invariants"]
    assert inv["calls_gh_cli"] is False
    assert inv["merges_or_comments_on_prs"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["step5_implementation_allowed"] is False


# ---------------------------------------------------------------------------
# Source / AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a22.__file__).read_text(encoding="utf-8")


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


def test_module_does_not_call_upstream_gh_functions() -> None:
    """A22 imports `reporting.github_pr_lifecycle` only for its
    `MODULE_VERSION` constant. It must NOT call any of the
    gh-using functions defined there."""
    import ast

    src = _module_source()
    tree = ast.parse(src)
    forbidden_calls = {
        "list_open_prs",
        "pr_inspect",
        "pr_changed_files",
        "pr_checks",
        "comment_dependabot_rebase",
        "merge_squash",
        "_gh",
        "_run",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in forbidden_calls:
                pytest.fail(f"forbidden call to {func.attr}")
            if isinstance(func, ast.Name) and func.id in forbidden_calls:
                pytest.fail(f"forbidden call to {func.id}")


def test_module_imports_cleanly() -> None:
    importlib.reload(a22)
    assert callable(a22.collect_snapshot)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(a22)
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
        / "development_pr_lifecycle_observer.md"
    ).read_text(encoding="utf-8")


def test_doc_states_a22_does_not_call_gh() -> None:
    text = _doc_text().lower()
    assert "never calls" in text
    assert "gh" in text


def test_doc_states_a22_does_not_recommend_merges() -> None:
    text = _doc_text().lower()
    assert "no recommendation" in text or "makes no recommendation" in text


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
        # Strip markdown blockquote markers ("> ") and collapse
        # whitespace so wrapped lines like "permanently\n> disabled"
        # still register as "permanently disabled".
        raw = text[start:end].lower()
        cleaned = re.sub(r"\n\s*>\s*", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned)
        assert "permanently disabled" in cleaned
