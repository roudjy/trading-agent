"""Unit tests for ``reporting.autonomous_workloop``.

Properties enforced (round-3 amended):

* ``safe_to_merge`` is unreachable in v3.15.15.16 local mode.
* ``merges_performed`` is always 0.
* Protected-governance edits force ``needs_human_protected_governance``.
* Frozen-contract edits force ``needs_human_contract_risk``.
* Live / paper / shadow / trading paths force
  ``needs_human_trading_or_risk``.
* React / Vite / TypeScript / @types/react majors classify as
  ``dependabot_major_framework_risk``.
* Other Dependabot bumps without external check evidence classify as
  ``dependabot_minor_safe_candidate`` (never ``_safe``).
* Conflict against ``main`` produces ``blocked_conflict``.
* Unknown classification stays ``unknown``, never ``ok``.
* ``push_target_allowed`` denies ``main``, ``dependabot/**``, and
  unrelated branches; allows only the current release branch.
* ``execute_safe_target_allowed`` denies any path under
  ``NO_TOUCH_GLOBS``.
* JSON artifact carries every required top-level key.
* ``frontend_control_state`` is present.
* ``--mode dry-run`` mutates nothing.
* ``--mode execute-safe`` writes only digest paths.
* Frozen contracts byte-identical before/after the snapshot run.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reporting import autonomous_workloop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _existence_and_sha(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return (False, None)
    return (True, _file_sha256(path))


# ---------------------------------------------------------------------------
# Classifier — pure-function tests (no git)
# ---------------------------------------------------------------------------


def test_safe_to_merge_is_unreachable_in_local_mode() -> None:
    """No fixture combination — protected, frozen, live, conflict, or
    just-clean — should produce ``safe_to_merge`` from
    ``_classify_branch``. The label is reserved for v3.15.15.19+ when
    external check evidence becomes available."""
    fixtures = [
        ("fix/feature-x", ["dashboard/api_x.py"], False),
        ("fix/feature-y", [".claude/settings.json"], False),
        ("fix/feature-z", ["research/research_latest.json"], False),
        ("fix/feature-w", ["execution/live/broker.py"], False),
        ("fix/feature-v", ["docs/x.md"], True),
        ("fix/feature-u", ["docs/x.md"], False),
    ]
    for branch, files, has_conflict in fixtures:
        cls, _ = autonomous_workloop._classify_branch(
            branch, files, has_conflict=has_conflict
        )
        assert cls != "safe_to_merge", (
            f"{branch} produced safe_to_merge — must be unreachable in local mode"
        )


def test_protected_governance_path_forces_needs_human_protected_governance() -> None:
    cls, reason = autonomous_workloop._classify_branch(
        "fix/test", [".claude/hooks/audit_emit.py"], has_conflict=False
    )
    assert cls == "needs_human_protected_governance"
    assert ".claude/hooks" in reason


def test_frozen_contract_path_forces_needs_human_contract_risk() -> None:
    cls, reason = autonomous_workloop._classify_branch(
        "fix/test", ["research/research_latest.json"], has_conflict=False
    )
    assert cls == "needs_human_contract_risk"
    assert "research_latest.json" in reason


def test_live_path_forces_needs_human_trading_or_risk() -> None:
    cls, _ = autonomous_workloop._classify_branch(
        "fix/test", ["agent/execution/live/broker.py"], has_conflict=False
    )
    assert cls == "needs_human_trading_or_risk"
    cls2, _ = autonomous_workloop._classify_branch(
        "fix/test", ["execution/some_thing_live.py"], has_conflict=False
    )
    assert cls2 == "needs_human_trading_or_risk"


def test_conflict_forces_blocked_conflict() -> None:
    cls, _ = autonomous_workloop._classify_branch(
        "fix/test", ["docs/clean.md"], has_conflict=True
    )
    assert cls == "blocked_conflict"


def test_clean_branch_classifies_as_waiting_for_checks() -> None:
    cls, reason = autonomous_workloop._classify_branch(
        "fix/test", ["docs/clean.md"], has_conflict=False
    )
    assert cls == "waiting_for_checks"
    assert "safe_to_merge" in reason  # the reason explicitly mentions reservation


# ---------------------------------------------------------------------------
# Dependabot classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("dependabot/npm_and_yarn/react-19.0.0", "dependabot_major_framework_risk"),
        ("dependabot/npm_and_yarn/react-dom-19.0.0", "dependabot_major_framework_risk"),
        ("dependabot/npm_and_yarn/vite-6.0.0", "dependabot_major_framework_risk"),
        ("dependabot/npm_and_yarn/typescript-6.0.0", "dependabot_major_framework_risk"),
        ("dependabot/pip/numpy-gte-1.26.4", "dependabot_minor_safe_candidate"),
        ("dependabot/pip/loguru-gte-0.7.3", "dependabot_minor_safe_candidate"),
        ("dependabot/github_actions/setup-python-6.2.0", "dependabot_minor_safe_candidate"),
    ],
)
def test_dependabot_classifier(branch: str, expected: str) -> None:
    cls, _ = autonomous_workloop._classify_dependabot(branch)
    assert cls == expected


def test_dependabot_branch_with_unparseable_shape_yields_unknown() -> None:
    cls, _ = autonomous_workloop._classify_dependabot(
        "dependabot/something/garbled"
    )
    # ``garbled`` has no version segment, so the regex misses; the
    # fallback is `unknown`.
    assert cls == "unknown"


def test_dependabot_safe_candidate_is_not_safe_to_merge() -> None:
    """Hard amendment-J rule: candidate is not safe to merge without
    green-check evidence. This release never produces ``*_safe``."""
    for branch in (
        "dependabot/pip/numpy-gte-1.26.4",
        "dependabot/github_actions/setup-python-6.2.0",
    ):
        cls, _ = autonomous_workloop._classify_dependabot(branch)
        assert "_candidate" in cls or "framework_risk" in cls or cls == "unknown"
        assert cls != "dependabot_patch_safe"
        assert cls != "dependabot_minor_safe"


# ---------------------------------------------------------------------------
# Push allowlist
# ---------------------------------------------------------------------------


def test_push_to_main_denied() -> None:
    ok, reason = autonomous_workloop.push_target_allowed("main")
    assert not ok
    assert "Doctrine 8" in reason


def test_push_to_dependabot_branch_denied() -> None:
    ok, reason = autonomous_workloop.push_target_allowed(
        "dependabot/pip/numpy-gte-1.26.4"
    )
    assert not ok
    assert "dependabot" in reason


def test_push_to_unrelated_feature_branch_denied() -> None:
    ok, reason = autonomous_workloop.push_target_allowed(
        "fix/v3.15.15.99-something-else"
    )
    assert not ok
    assert "current release branch" in reason


def test_push_to_current_release_branch_allowed() -> None:
    ok, reason = autonomous_workloop.push_target_allowed(
        autonomous_workloop.CURRENT_RELEASE_BRANCH
    )
    assert ok
    assert reason is None


# ---------------------------------------------------------------------------
# execute-safe target allowlist (defense in depth)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        ".claude/settings.json",
        ".claude/hooks/audit_emit.py",
        ".claude/agents/planner.md",
        ".github/CODEOWNERS",
        "VERSION",
        "automation/live_gate.py",
        "research/research_latest.json",
        "research/strategy_matrix.csv",
        "Dockerfile",
        "scripts/deploy.sh",
        "docker-compose.prod.yml",
    ],
)
def test_execute_safe_denies_no_touch_paths(target: str) -> None:
    ok, reason = autonomous_workloop.execute_safe_target_allowed(target)
    assert not ok
    # The denial may cite no-touch / frozen contract / live-trading;
    # any of those is acceptable — the point is the path is blocked.
    assert any(
        kw in reason for kw in ("no-touch", "frozen contract", "live", "trading-flow")
    )


def test_execute_safe_allows_workloop_digest_paths() -> None:
    ok, reason = autonomous_workloop.execute_safe_target_allowed(
        "docs/governance/autonomous_workloop/latest.md"
    )
    assert ok
    assert reason is None


# ---------------------------------------------------------------------------
# Snapshot shape & invariants
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_workloop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect digest output dirs into ``tmp_path`` so the test
    cannot pollute the real repo state. Stub out the network/git
    calls so each snapshot is deterministic and fast — we test the
    snapshot *shape* and *invariants* here, not git plumbing.
    """
    monkeypatch.setattr(
        autonomous_workloop, "DIGEST_DIR_MD", tmp_path / "docs_digest"
    )
    monkeypatch.setattr(
        autonomous_workloop, "DIGEST_DIR_JSON", tmp_path / "logs_digest"
    )
    # Stub git plumbing — no fetches, no merge-trees.
    monkeypatch.setattr(
        autonomous_workloop, "_list_remote_branches", lambda: []
    )
    monkeypatch.setattr(
        autonomous_workloop, "_changed_files", lambda branch: []
    )
    monkeypatch.setattr(
        autonomous_workloop, "_has_conflict_with_main", lambda branch: False
    )
    monkeypatch.setattr(
        autonomous_workloop,
        "_git_state",
        lambda: {
            "branch": "fix/v3.15.15.16-autonomous-workloop-controller",
            "head_sha": "0" * 40,
            "is_clean": True,
            "dirty_paths_count": 0,
        },
    )
    monkeypatch.setattr(
        autonomous_workloop,
        "_governance_status",
        lambda: {"lint_passed": True, "summary": "Governance lint OK"},
    )
    monkeypatch.setattr(
        autonomous_workloop,
        "_audit_chain_status",
        lambda: {
            "ledger_path": "logs/agent_audit.test.jsonl",
            "status": "intact",
            "first_corrupt_index": None,
        },
    )
    return tmp_path


def test_snapshot_has_every_required_top_level_key(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    required = {
        "schema_version",
        "report_kind",
        "controller_version",
        "generated_at_utc",
        "mode",
        "cycle_id",
        "current_branch",
        "git_state",
        "governance_status",
        "audit_chain_status",
        "frozen_contracts",
        "pr_queue",
        "dependabot_queue",
        "roadmap_queue",
        "actions_taken",
        "merges_performed",
        "blocked_items",
        "needs_human",
        "next_recommended_item",
        "frontend_control_state",
        "limitations",
    }
    assert required <= set(snap.keys())


def test_merges_performed_is_zero_invariant(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    assert snap["merges_performed"] == 0


def test_safe_to_merge_never_appears_in_pr_queue(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    for row in snap["pr_queue"] + snap["dependabot_queue"]:
        assert row["risk_class"] != "safe_to_merge"


def test_frontend_control_state_present(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    fcs = snap["frontend_control_state"]
    assert fcs["read_only"] is True
    assert "json_artifact_path" in fcs
    assert "execute_actions_unlocked_in" in fcs


def test_limitations_section_lists_required_statements(
    isolated_workloop: Path,
) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    lims = " ".join(snap["limitations"])
    # The 10 required final-report statements should each appear in
    # some form. We probe a few distinctive phrases.
    assert "not full PR automation" in lims
    assert "merges: 0" in lims
    assert "operator-click merge is still required" in lims
    assert "recommendation-only" in lims
    assert "candidates are not safe to merge" in lims
    assert "ADR-016" in lims
    assert "convenience-only" in lims
    assert "v3.15.15.19" in lims
    assert "JSON artifacts" in lims


def test_roadmap_queue_is_recommendation_only(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    for row in snap["roadmap_queue"]:
        assert row["decision"] in ("recommendation_only", "needs_human")
        assert "no autonomous execution" in row["reason"] or row["decision"] == "needs_human"


def test_pr_queue_checks_status_is_not_available(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    for row in snap["pr_queue"] + snap["dependabot_queue"]:
        assert row["checks_status"] == "not_available"


# ---------------------------------------------------------------------------
# Read-only / mutation invariants
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write_outputs(
    isolated_workloop: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = autonomous_workloop.main(["--mode", "dry-run", "--indent", "0"])
    assert rc == 0
    md_dir = autonomous_workloop.DIGEST_DIR_MD
    json_dir = autonomous_workloop.DIGEST_DIR_JSON
    # The dirs should not have been created by dry-run.
    assert not md_dir.exists() or not any(md_dir.iterdir())
    assert not json_dir.exists() or not any(json_dir.iterdir())


def test_execute_safe_writes_only_digest_paths(
    isolated_workloop: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = autonomous_workloop.main(["--mode", "execute-safe"])
    assert rc == 0
    md_dir = autonomous_workloop.DIGEST_DIR_MD
    json_dir = autonomous_workloop.DIGEST_DIR_JSON
    assert (md_dir / "latest.md").exists()
    assert (json_dir / "latest.json").exists()
    # No other paths under the test tmp tree should be touched.
    for entry in isolated_workloop.iterdir():
        assert entry.name in {"docs_digest", "logs_digest"}, (
            f"execute-safe touched unexpected path: {entry}"
        )


def test_no_secrets_in_snapshot(isolated_workloop: Path) -> None:
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    autonomous_workloop.assert_no_secrets(snap)


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_plan_mode_returns_zero_and_valid_json(
    isolated_workloop: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = autonomous_workloop.main(["--mode", "plan", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert parsed["report_kind"] == "autonomous_workloop_digest"
    assert parsed["mode"] == "plan"


def test_cli_continuous_mode_clamps_max_cycles(
    isolated_workloop: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Asking for 1000 cycles must clamp to 25 — but the test only
    # checks that the run completes (clamped) without explosion.
    # Use a small value to keep the test fast.
    rc = autonomous_workloop.main(["--mode", "continuous", "--max-cycles", "2"])
    assert rc == 0


# ---------------------------------------------------------------------------
# Frozen contracts unchanged
# ---------------------------------------------------------------------------


def test_collect_does_not_touch_frozen_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frozen-contract integrity check. Uses the same git stubs as the
    isolated fixture so the test is fast and deterministic."""
    monkeypatch.setattr(autonomous_workloop, "_list_remote_branches", lambda: [])
    monkeypatch.setattr(autonomous_workloop, "_changed_files", lambda branch: [])
    monkeypatch.setattr(
        autonomous_workloop, "_has_conflict_with_main", lambda branch: False
    )

    repo_root = Path(__file__).resolve().parent.parent.parent
    research_latest = repo_root / "research" / "research_latest.json"
    strategy_matrix = repo_root / "research" / "strategy_matrix.csv"
    before_a = _existence_and_sha(research_latest)
    before_b = _existence_and_sha(strategy_matrix)
    snap = autonomous_workloop.collect_snapshot(mode="dry-run")
    autonomous_workloop.assert_no_secrets(snap)
    after_a = _existence_and_sha(research_latest)
    after_b = _existence_and_sha(strategy_matrix)
    assert before_a == after_a
    assert before_b == after_b
