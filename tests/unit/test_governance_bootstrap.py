"""Unit tests for ``reporting.governance_bootstrap`` (v3.15.16.9)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import governance_bootstrap as gb


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "reporting" / "governance_bootstrap.py"


def _strip_strings_and_comments(src: str) -> str:
    """Return ``src`` with triple-quoted string literals and ``#``
    line comments removed. Sufficient for source-text invariant
    checks that need to look only at executable code, not at
    docstrings or in-line documentation that legitimately mentions
    forbidden tokens (e.g. ``git apply``)."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r"#[^\n]*", "", src)
    return src


@pytest.fixture
def isolated_digest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(gb, "DIGEST_DIR_JSON", tmp_path / "gb")
    return tmp_path


def _event(
    event_id: str,
    *,
    reason: str = "governance_bootstrap_required",
    blocking_component: str = "dashboard/dashboard.py:register_xyz_routes",
    required_action: str = "Open a one-shot bootstrap PR.",
    proposed_patch: str | None = (
        "from dashboard.api_xyz import register_xyz_routes\n"
        "register_xyz_routes(app)\n"
    ),
    impact: str = "MEDIUM",
    priority: str = "HIGH",
    related_item: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "reason": reason,
        "blocking_component": blocking_component,
        "required_action": required_action,
        "proposed_patch": proposed_patch,
        "impact": impact,
        "priority": priority,
        "related_item": related_item,
        "evidence": {},
    }


def _hn(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "human_needed_digest",
        "module_version": "v3.15.16.8",
        "events": events,
    }


# ---------------------------------------------------------------------------
# Hard-coded digest invariants
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false_with_templates() -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn([_event("h_aaaaaaaaaa")]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["safe_to_execute"] is False


def test_safe_to_execute_is_false_when_not_available() -> None:
    snap = gb.collect_snapshot(
        human_needed_override={"events": "not a list"},
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["final_recommendation"] == gb.REC_NOT_AVAILABLE
    assert snap["safe_to_execute"] is False


def test_module_version_pinned() -> None:
    assert gb.MODULE_VERSION == "v3.15.16.9"


def test_schema_version_pinned() -> None:
    assert gb.SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Template synthesis
# ---------------------------------------------------------------------------


def test_governance_bootstrap_event_produces_template() -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn([_event("h_aaaaaaaaaa")]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["counts"]["templates_total"] == 1
    t = snap["templates"][0]
    assert t["source_event_id"] == "h_aaaaaaaaaa"
    assert t["source_reason"] == "governance_bootstrap_required"
    assert t["branch_name"] == "governance-bootstrap/h_aaaaaaaaaa"
    assert t["commit_message"].startswith("governance-bootstrap:")
    assert t["pr_title"].startswith("governance-bootstrap:")
    # file_diff is byte-identical to proposed_patch
    assert t["file_diff"] == (
        "from dashboard.api_xyz import register_xyz_routes\n"
        "register_xyz_routes(app)\n"
    )
    # PR body references the source event id
    assert "h_aaaaaaaaaa" in t["pr_body"]
    # validation_checklist is the canonical list
    assert isinstance(t["validation_checklist"], list)
    assert len(t["validation_checklist"]) == 5


def test_event_without_proposed_patch_is_skipped() -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn(
            [_event("h_aaaaaaaaaa", proposed_patch=None)]
        ),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["counts"]["templates_total"] == 0
    assert snap["source_human_needed"]["skipped_events"] == 1


def test_decision_unclear_event_is_skipped() -> None:
    """decision_cannot_be_inferred is not in BOOTSTRAPPABLE_REASONS."""
    snap = gb.collect_snapshot(
        human_needed_override=_hn(
            [
                _event(
                    "h_aaaaaaaaaa",
                    reason="decision_cannot_be_inferred",
                    proposed_patch="some text",
                )
            ]
        ),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["counts"]["templates_total"] == 0


def test_v3_15_16_5_wiring_gap_template_is_byte_identical_across_runs() -> None:
    """Determinism canary: feed the canonical v3.15.16.5 wiring gap
    event and assert the synthesized template is byte-identical
    across two runs."""
    ev = _event(
        "h_canonical1",
        blocking_component="dashboard/dashboard.py:register_roadmap_priority_routes",
        proposed_patch=(
            "from dashboard.api_roadmap_priority import register_roadmap_priority_routes\n"
            "register_roadmap_priority_routes(app)\n"
        ),
    )
    s1 = gb.collect_snapshot(
        human_needed_override=_hn([ev]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    s2 = gb.collect_snapshot(
        human_needed_override=_hn([ev]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert s1["templates"] == s2["templates"]
    t = s1["templates"][0]
    # The proposed_patch is the literal two-line wiring edit.
    assert "from dashboard.api_roadmap_priority import register_roadmap_priority_routes" in t["file_diff"]
    assert "register_roadmap_priority_routes(app)" in t["file_diff"]
    # The branch name is deterministic.
    assert t["branch_name"] == "governance-bootstrap/h_canonical1"


def test_template_id_deterministic() -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn([_event("h_aaaaaaaaaa")]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    t = snap["templates"][0]
    # Strips the h_ prefix and re-prefixes with gb_.
    assert t["template_id"] == "gb_aaaaaaaaaa"


# ---------------------------------------------------------------------------
# Source availability
# ---------------------------------------------------------------------------


def test_missing_human_needed_yields_not_available() -> None:
    snap = gb.collect_snapshot(
        human_needed_override={"not": "valid"},
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["final_recommendation"] == gb.REC_NOT_AVAILABLE


def test_empty_events_list_is_ok_with_zero_templates() -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn([]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    assert snap["final_recommendation"] == gb.REC_OK
    assert snap["counts"]["templates_total"] == 0


# ---------------------------------------------------------------------------
# Module-source guarantees
# ---------------------------------------------------------------------------


def test_module_source_no_subprocess_no_network() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "shell=True",
        "os.system(",
        "Popen(",
        "import requests",
        "import urllib.request",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden token: {tok!r}"


def test_module_source_no_gh_or_git_invocation() -> None:
    """Strip docstrings + comments before checking — the module's
    docstring legitimately documents what it does NOT do (mentions
    `gh`, `git`, etc. as prose). We only care about executable code."""
    src = _strip_strings_and_comments(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen", "gh pr ", "git checkout ")
    for tok in forbidden:
        assert tok not in src, f"forbidden gh/git token in executable code: {tok!r}"


def test_module_source_does_not_apply_patches() -> None:
    """The synthesizer produces text only — never applies patches.
    Strip docstrings + comments so the test inspects executable
    code only (the module's docstring explicitly mentions
    `git apply` / `subprocess.run` as the forbidden behaviours)."""
    src = _strip_strings_and_comments(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden = (
        "git apply",
        "patch -",
        "subprocess.run",
        "subprocess.Popen",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"forbidden patch-application token in executable code: {tok!r}"
        )


def test_module_source_no_branch_or_pr_creation() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "git checkout -b",
        "git push",
        "gh pr create",
        "gh pr merge",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden action: {tok!r}"


def test_safe_to_execute_field_is_hard_coded_false() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    occurrences = re.findall(r'"safe_to_execute":\s*([A-Za-z]+)', src)
    assert occurrences, "safe_to_execute key not found in module source"
    assert all(v == "False" for v in occurrences), (
        f"safe_to_execute is not hard-coded False everywhere: {occurrences!r}"
    )


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_outputs_atomic_and_scoped(isolated_digest_dir: Path) -> None:
    snap = gb.collect_snapshot(
        human_needed_override=_hn([_event("h_aaaaaaaaaa")]),
        frozen_utc="2026-05-05T12:00:00Z",
    )
    paths = gb.write_outputs(snap)
    base = isolated_digest_dir / "gb"
    assert (base / "latest.json").exists()
    assert (base / "history.jsonl").exists()
    assert paths["latest"].endswith("latest.json")
    leftover = list(base.glob("*.tmp"))
    assert leftover == []


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_only_dry_run_mode_allowed() -> None:
    with pytest.raises(SystemExit):
        gb.main(["--mode", "execute-safe"])


def test_cli_status_returns_not_available_when_missing(
    isolated_digest_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = gb.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not_available" in out
