"""Pin-tests for N5b Phase 1 — dry-run merge preflight projector.

Verifies the read-only dry-run preflight projector in
``reporting/development_merge_preflight.py`` against the
closed-vocab schema, the default-deny behaviour, and the runtime
guardrails (no subprocess, no network, no GitHub mutation, no
token mint/verify, no seed writes, Step 5 + Level 6 invariants
intact).

Forbidden marker strings (PEM, shell commands, etc.) that the
source scans search for are assembled at runtime from constituent
parts so this test file itself stays inert to gitleaks and to the
projector's own source-text guards.
"""

from __future__ import annotations

import ast
import datetime as _dt
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import development_merge_preflight as pf
from reporting import development_merge_recommendation as dmr
from reporting import development_pr_lifecycle_observer as a22


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures — isolate the on-disk artefact paths into tmp_path so tests
# never touch the real logs/ tree.
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    rec = tmp_path / "logs" / "development_merge_recommendation" / "latest.json"
    rec.parent.mkdir(parents=True, exist_ok=True)
    lifecycle = (
        tmp_path
        / "logs"
        / "development_pr_lifecycle_observer"
        / "latest.json"
    )
    lifecycle.parent.mkdir(parents=True, exist_ok=True)
    preflight = tmp_path / "logs" / "development_merge_preflight" / "latest.json"
    preflight.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dmr, "ARTIFACT_LATEST", rec)
    monkeypatch.setattr(a22, "ARTIFACT_LATEST", lifecycle)
    monkeypatch.setattr(pf, "ARTIFACT_LATEST", preflight)
    monkeypatch.setattr(
        pf, "ARTIFACT_DIR", preflight.parent
    )
    return {
        "rec": rec,
        "lifecycle": lifecycle,
        "preflight": preflight,
    }


# ---------------------------------------------------------------------------
# Synthetic-row helpers
# ---------------------------------------------------------------------------


def _n5a_row(
    *,
    pr_number: int = 42,
    head_sha: str = "deadbeefdeadbeef0000000000000001",
    head_ref: str = "feature/x",
    base_ref: str = "main",
    observer_classification: str = "open_clean_mergeable",
    inbox_blocked_count: int = 0,
    inbox_critical_count: int = 0,
    inbox_needs_review_count: int = 0,
    recommendation_action: str = "recommend_human_merge",
    recommendation_reason: str = "pr_clean_and_no_blocking_inbox",
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "recommendation_id": f"mr_{pr_number}_{head_sha[:12]}",
        "pr_number": pr_number,
        "head_sha": head_sha,
        "head_ref": head_ref,
        "base_ref": base_ref,
        "observer_classification": observer_classification,
        "inbox_blocked_count": inbox_blocked_count,
        "inbox_critical_count": inbox_critical_count,
        "inbox_needs_review_count": inbox_needs_review_count,
        "recommendation_action": recommendation_action,
        "recommendation_reason": recommendation_reason,
        "evaluated_at": (
            evaluated_at
            if evaluated_at is not None
            else "2026-05-12T20:00:00Z"
        ),
    }


def _a22_row(
    *,
    pr_number: int = 42,
    head_sha: str = "deadbeefdeadbeef0000000000000001",
    head_ref: str = "feature/x",
    base_ref: str = "main",
    merge_state_status: str = "CLEAN",
    checks_summary: str = "SUCCESS",
    observer_classification: str = "open_clean_mergeable",
) -> dict[str, Any]:
    return {
        "pr_number": pr_number,
        "title": "feat: x",
        "head_ref": head_ref,
        "head_sha": head_sha,
        "base_ref": base_ref,
        "state": "OPEN",
        "is_draft": False,
        "merge_state_status": merge_state_status,
        "mergeable": "MERGEABLE",
        "checks_summary": checks_summary,
        "author_login": "operator",
        "is_dependabot": False,
        "observer_classification": observer_classification,
        "url": f"https://github.com/example/repo/pull/{pr_number}",
        "created_at": "2026-05-12T19:00:00Z",
        "updated_at": "2026-05-12T20:00:00Z",
    }


def _write_rec(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": dmr.SCHEMA_VERSION,
        "module_version": dmr.MODULE_VERSION,
        "report_kind": dmr.REPORT_KIND,
        "generated_at_utc": "2026-05-12T20:01:00Z",
        "rows": rows,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_lifecycle(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": a22.SCHEMA_VERSION,
        "module_version": a22.MODULE_VERSION,
        "report_kind": a22.REPORT_KIND,
        "generated_at_utc": "2026-05-12T20:01:00Z",
        "rows": rows,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level invariant pins
# ---------------------------------------------------------------------------


def test_module_constants_match_closed_vocab() -> None:
    assert pf.SCHEMA_VERSION == "1.0"
    assert pf.MODULE_VERSION == "v3.15.16.N5b.phase1"
    assert pf.REPORT_KIND == "development_merge_preflight"


def test_step5_invariants_intact_by_import() -> None:
    assert pf.step5_implementation_allowed is False
    assert pf.STEP5_ENABLED_SUBSTAGE == "none"


def test_dry_run_verdicts_are_exact_closed_tuple() -> None:
    assert pf.DRY_RUN_VERDICTS == (
        "would_block",
        "would_require_operator",
        "would_be_live_candidate_if_authorized",
    )


def test_stop_conditions_are_exact_closed_tuple() -> None:
    assert pf.STOP_CONDITIONS == (
        "missing_merge_recommendation_artifact",
        "malformed_merge_recommendation_artifact",
        "missing_pr_lifecycle_artifact",
        "malformed_pr_lifecycle_artifact",
        "recommendation_not_merge",
        "missing_pr_number",
        "missing_head_sha",
        "base_ref_not_main",
        "merge_state_not_clean",
        "checks_not_green",
        "head_sha_mismatch",
        "critical_inbox_rows_present",
        "stale_recommendation",
        "token_required_for_live",
        "live_merge_not_implemented",
        "insufficient_evidence",
    )


def test_candidate_row_keys_are_exact_closed_tuple() -> None:
    assert pf.CANDIDATE_ROW_KEYS == (
        "preflight_id",
        "recommendation_id",
        "pr_number",
        "expected_head_sha",
        "observed_head_sha",
        "base_ref",
        "head_ref",
        "merge_state",
        "checks_state",
        "recommendation_action",
        "recommendation_reason",
        "token_required_for_live",
        "dry_run_verdict",
        "live_merge_implemented",
        "stop_conditions",
        "audit_note",
        "generated_at_utc",
        "evidence_freshness_seconds",
    )


def test_discipline_invariants_match_exact_required_set() -> None:
    """The discipline invariants dict must match the operator's
    specified shape, exactly."""
    expected = {
        "dry_run_only": True,
        "live_merge_implemented": False,
        "executes_merge": False,
        "calls_github_api": False,
        "uses_subprocess_or_network": False,
        "deploy_coupled": False,
        "mints_or_verifies_approval_tokens": False,
        "writes_seed_files": False,
        "writes_generated_seed": False,
        "opens_or_merges_prs": False,
        "step5_implementation_allowed": False,
        "step5_enabled_substage": "none",
        "level6_enabled": False,
    }
    assert pf._DISCIPLINE_INVARIANTS == expected


# ---------------------------------------------------------------------------
# CLI / file invariants
# ---------------------------------------------------------------------------


def test_no_write_creates_no_artifact(
    isolated_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not isolated_paths["preflight"].exists()
    rc = pf.main(["--no-write"])
    assert rc == 0
    assert not isolated_paths["preflight"].exists()
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["report_kind"] == "development_merge_preflight"
    assert parsed["dry_run_only"] is True
    assert parsed["live_merge_implemented"] is False


def test_default_write_creates_preflight_latest(
    isolated_paths: dict[str, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert not isolated_paths["preflight"].exists()
    rc = pf.main([])
    assert rc == 0
    assert isolated_paths["preflight"].is_file()
    parsed = json.loads(isolated_paths["preflight"].read_text(encoding="utf-8"))
    assert parsed["report_kind"] == "development_merge_preflight"
    assert parsed["schema_version"] == "1.0"
    assert parsed["module_version"] == "v3.15.16.N5b.phase1"
    assert parsed["step5_implementation_allowed"] is False
    assert parsed["step5_enabled_substage"] == "none"
    assert parsed["live_merge_implemented"] is False
    assert parsed["dry_run_only"] is True
    assert parsed["deploy_coupled"] is False
    assert parsed["level6_enabled"] is False


def test_atomic_write_refuses_path_outside_write_prefix(
    tmp_path: Path,
) -> None:
    rogue = tmp_path / "logs" / "development_merge_recommendation" / "rogue.json"
    rogue.parent.mkdir(parents=True, exist_ok=True)
    snap = pf.collect_snapshot()
    with pytest.raises(ValueError):
        pf._atomic_write_json(rogue, snap)


def test_assert_no_secrets_runs_inside_collect_snapshot(
    isolated_paths: dict[str, Path],
) -> None:
    # Triggering collect_snapshot at all means assert_no_secrets ran
    # (it raises if any secret-shaped substring is detected).
    snap = pf.collect_snapshot()
    assert isinstance(snap, dict)


# ---------------------------------------------------------------------------
# Behavioural pins: missing / malformed artefacts → default-deny
# ---------------------------------------------------------------------------


def test_missing_recommendation_artifact_yields_no_candidates(
    isolated_paths: dict[str, Path],
) -> None:
    # No recommendation artefact + no lifecycle artefact.
    snap = pf.collect_snapshot()
    assert snap["candidate_count"] == 0
    assert snap["candidates"] == []
    assert (
        "merge_recommendation_artifact_absent" in snap["validation_warnings"]
    )
    assert snap["note"] == "missing_merge_recommendation_artifact"
    assert snap["live_merge_implemented"] is False


def test_missing_lifecycle_artifact_downgrades_each_row(
    isolated_paths: dict[str, Path],
) -> None:
    _write_rec(isolated_paths["rec"], [_n5a_row(pr_number=101)])
    # No lifecycle artefact.
    snap = pf.collect_snapshot()
    assert snap["candidate_count"] == 1
    row = snap["candidates"][0]
    assert "pr_lifecycle_artifact_absent" in snap["validation_warnings"]
    # Verdict must NOT be the green/eligible verdict when lifecycle is absent.
    assert row["dry_run_verdict"] != "would_be_live_candidate_if_authorized"
    assert "insufficient_evidence" in row["stop_conditions"]


def test_malformed_recommendation_artifact_yields_warning(
    isolated_paths: dict[str, Path],
) -> None:
    isolated_paths["rec"].write_text("not json", encoding="utf-8")
    snap = pf.collect_snapshot()
    assert (
        "merge_recommendation_artifact_unparseable" in snap["validation_warnings"]
    )
    assert snap["candidate_count"] == 0


def test_malformed_lifecycle_artifact_yields_warning(
    isolated_paths: dict[str, Path],
) -> None:
    _write_rec(isolated_paths["rec"], [_n5a_row(pr_number=202)])
    isolated_paths["lifecycle"].write_text("garbage", encoding="utf-8")
    snap = pf.collect_snapshot()
    assert (
        "pr_lifecycle_artifact_unparseable" in snap["validation_warnings"]
    )
    # The single recommendation row still produces a candidate but
    # cannot be live-eligible without the lifecycle data.
    assert snap["candidate_count"] == 1
    assert (
        snap["candidates"][0]["dry_run_verdict"]
        != "would_be_live_candidate_if_authorized"
    )


# ---------------------------------------------------------------------------
# Behavioural pins: clean synthetic happy path
# ---------------------------------------------------------------------------


def test_clean_synthetic_yields_would_be_live_candidate(
    isolated_paths: dict[str, Path],
) -> None:
    """Happy path: matching N5a + A22 rows, CLEAN merge state, SUCCESS
    checks, base=main, matching head SHA, no critical inbox, fresh
    timestamp → ``would_be_live_candidate_if_authorized``.

    Stop conditions must contain ONLY the two informational entries
    (token_required_for_live, live_merge_not_implemented)."""
    # Use a current timestamp so freshness < threshold.
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=300, evaluated_at=now)],
    )
    _write_lifecycle(isolated_paths["lifecycle"], [_a22_row(pr_number=300)])
    snap = pf.collect_snapshot()
    assert snap["candidate_count"] == 1
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_be_live_candidate_if_authorized"
    assert row["live_merge_implemented"] is False
    assert row["token_required_for_live"] is True
    assert row["pr_number"] == 300
    assert row["base_ref"] == "main"
    assert row["merge_state"] == "CLEAN"
    assert row["checks_state"] == "SUCCESS"
    assert row["expected_head_sha"] == row["observed_head_sha"]
    assert row["recommendation_action"] == "recommend_human_merge"
    assert set(row["stop_conditions"]) == {
        "token_required_for_live",
        "live_merge_not_implemented",
    }
    # All keys must match the closed schema exactly.
    assert set(row.keys()) == set(pf.CANDIDATE_ROW_KEYS)


# ---------------------------------------------------------------------------
# Behavioural pins: every blocker → would_block + correct stop_condition
# ---------------------------------------------------------------------------


def test_base_ref_not_main_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=400, evaluated_at=now)],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"],
        [_a22_row(pr_number=400, base_ref="release/v1")],
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "base_ref_not_main" in row["stop_conditions"]


def test_merge_state_not_clean_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=410, evaluated_at=now)],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"],
        [_a22_row(pr_number=410, merge_state_status="DIRTY")],
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "merge_state_not_clean" in row["stop_conditions"]


def test_checks_not_green_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=420, evaluated_at=now)],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"],
        [_a22_row(pr_number=420, checks_summary="FAILURE")],
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "checks_not_green" in row["stop_conditions"]


def test_head_sha_mismatch_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [
            _n5a_row(
                pr_number=430,
                head_sha="aaaaaaaaaaaa0000000000000000000000000001",
                evaluated_at=now,
            )
        ],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"],
        [
            _a22_row(
                pr_number=430,
                head_sha="bbbbbbbbbbbb0000000000000000000000000002",
            )
        ],
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "head_sha_mismatch" in row["stop_conditions"]


def test_missing_head_sha_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=440, head_sha="", evaluated_at=now)],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"], [_a22_row(pr_number=440)]
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "missing_head_sha" in row["stop_conditions"]


def test_recommendation_not_merge_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [
            _n5a_row(
                pr_number=450,
                recommendation_action="recommend_hold",
                recommendation_reason="pr_blocked_or_dirty",
                evaluated_at=now,
            )
        ],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"], [_a22_row(pr_number=450)]
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "recommendation_not_merge" in row["stop_conditions"]


def test_critical_inbox_rows_present_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [
            _n5a_row(
                pr_number=460,
                inbox_critical_count=2,
                evaluated_at=now,
            )
        ],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"], [_a22_row(pr_number=460)]
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "critical_inbox_rows_present" in row["stop_conditions"]


def test_stale_recommendation_yields_would_block(
    isolated_paths: dict[str, Path],
) -> None:
    """An evaluated_at older than STALE_THRESHOLD_SECONDS triggers
    the stale stop-condition."""
    very_old = "2020-01-01T00:00:00Z"
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=470, evaluated_at=very_old)],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"], [_a22_row(pr_number=470)]
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_block"
    assert "stale_recommendation" in row["stop_conditions"]


def test_only_insufficient_evidence_yields_would_require_operator(
    isolated_paths: dict[str, Path],
) -> None:
    """When the lifecycle artefact is present but contains no row
    for the bound PR, the candidate gets ``insufficient_evidence``
    only — verdict should be ``would_require_operator`` (the
    operator needs to refresh the upstream artefact)."""
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [_n5a_row(pr_number=480, evaluated_at=now)],
    )
    # Lifecycle artefact present but no row for PR 480.
    _write_lifecycle(
        isolated_paths["lifecycle"], [_a22_row(pr_number=999)]
    )
    snap = pf.collect_snapshot()
    row = snap["candidates"][0]
    assert row["dry_run_verdict"] == "would_require_operator"
    assert "insufficient_evidence" in row["stop_conditions"]


def test_every_candidate_stop_condition_is_in_closed_vocab(
    isolated_paths: dict[str, Path],
) -> None:
    """Defense in depth: across all candidates, every stop_condition
    string must be in the closed STOP_CONDITIONS vocabulary."""
    now = (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    _write_rec(
        isolated_paths["rec"],
        [
            _n5a_row(pr_number=501, evaluated_at=now),
            _n5a_row(
                pr_number=502,
                evaluated_at=now,
                recommendation_action="recommend_hold",
            ),
            _n5a_row(
                pr_number=503,
                evaluated_at=now,
                inbox_critical_count=1,
            ),
        ],
    )
    _write_lifecycle(
        isolated_paths["lifecycle"],
        [
            _a22_row(pr_number=501),
            _a22_row(pr_number=502, merge_state_status="DIRTY"),
            _a22_row(pr_number=503, base_ref="main"),
        ],
    )
    snap = pf.collect_snapshot()
    for row in snap["candidates"]:
        for sc in row["stop_conditions"]:
            assert sc in pf.STOP_CONDITIONS, f"unknown stop_condition: {sc!r}"
        assert row["dry_run_verdict"] in pf.DRY_RUN_VERDICTS


def test_top_level_step5_and_level6_invariants_pinned(
    isolated_paths: dict[str, Path],
) -> None:
    snap = pf.collect_snapshot()
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    inv = snap["discipline_invariants"]
    assert inv["dry_run_only"] is True
    assert inv["live_merge_implemented"] is False
    assert inv["executes_merge"] is False
    assert inv["calls_github_api"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["deploy_coupled"] is False
    assert inv["mints_or_verifies_approval_tokens"] is False
    assert inv["writes_seed_files"] is False
    assert inv["writes_generated_seed"] is False
    assert inv["opens_or_merges_prs"] is False
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"
    assert inv["level6_enabled"] is False


# ---------------------------------------------------------------------------
# Source-text + AST scans — pin the runtime guardrails
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(pf.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_or_network_imports() -> None:
    forbidden = {
        "subprocess",
        "socket",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "http.client",
        "requests",
        "httpx",
        "aiohttp",
        "selectors",
        "asyncio",
    }
    overlap = _imported_module_names() & forbidden
    assert not overlap, (
        "development_merge_preflight must not import "
        f"network/subprocess modules: {overlap!r}"
    )


def test_no_forbidden_subsystem_imports() -> None:
    """No import of dashboard, frontend, automation, broker,
    agent.risk, agent.execution, research, intelligent_routing,
    live, paper, shadow, trading, approval-token runtime."""
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
        "reporting.approval_token_runtime",
        "reporting.approval_token_gate",
    )
    names = _imported_module_names()
    for prefix in forbidden_prefixes:
        for name in names:
            assert not (
                name == prefix or name.startswith(prefix + ".")
            ), (
                f"development_merge_preflight must not import "
                f"{prefix!r}; got {name!r}"
            )


def test_no_env_access_in_source() -> None:
    text = _module_source()
    forbidden = ("os.environ", "os.getenv", "environ[")
    for tok in forbidden:
        assert tok not in text, (
            f"development_merge_preflight must not access env: {tok!r}"
        )


def test_no_gh_or_git_cli_literal() -> None:
    """No ``gh pr merge``, ``gh pr review``, ``gh api``, ``git merge``,
    ``git push`` literals in the source. We build the patterns at
    runtime so the test file itself is inert."""
    text = _module_source()
    forbidden_literals = (
        "g" + "h pr merge",
        "g" + "h pr review",
        "g" + "h api",
        "g" + "it merge",
        "g" + "it push",
    )
    for tok in forbidden_literals:
        assert tok not in text, (
            f"development_merge_preflight contains forbidden CLI "
            f"literal: {tok!r}"
        )


def test_no_seed_file_literal() -> None:
    """The projector must never reference a seed file by name."""
    text = _module_source()
    forbidden = ("seed.jsonl", "delegation_seed.jsonl", "generated_seed.jsonl")
    for tok in forbidden:
        assert tok not in text, (
            f"development_merge_preflight must not reference {tok!r}"
        )


def test_no_pem_secret_block_in_source() -> None:
    """Markers assembled at runtime so the test source is inert to
    gitleaks' private-key rule."""
    text = _module_source()
    dashes = "-" * 5
    for kind in ("PRIVATE KEY", "EC PRIVATE KEY", "RSA PRIVATE KEY"):
        marker = f"{dashes}BEGIN {kind}{dashes}"
        assert marker not in text, (
            f"development_merge_preflight contains a PEM block: {marker!r}"
        )


def test_no_non_loopback_ip_literal_in_source() -> None:
    text = _module_source()
    ip_re = re.compile(
        r"(?<![\w.])(?!127\.0\.0\.1\b)"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![.\d])"
    )
    matches = ip_re.findall(text)
    assert matches == [], (
        f"development_merge_preflight contains a non-loopback IP "
        f"literal: {matches!r}"
    )


def test_no_token_or_approval_secret_reference_in_source() -> None:
    """Forbid USE-pattern occurrences of the approval-token /
    Web-Push subsystems. The discipline-invariant *key*
    ``mints_or_verifies_approval_tokens`` legitimately contains
    the substring ``approval_token`` — that key is exactly the
    declaration that we do NOT mint or verify tokens — so we
    cannot ban that substring outright. Instead we ban concrete
    use patterns: imports of the runtime/gate modules, function
    calls to mint/verify, and the canonical env-var name."""
    text = _module_source()
    forbidden = (
        "ADE_APPROVAL_TOKEN_HMAC_SECRET",
        "from reporting.approval_token_runtime",
        "from reporting.approval_token_gate",
        "from dashboard.api_approval_token_gate",
        "import approval_token_runtime",
        "import approval_token_gate",
        "mint_runtime(",
        "verify_runtime(",
        "mint_token(",
        "verify_token(",
        "VAPID",
        "p256dh",
    )
    for tok in forbidden:
        assert tok not in text, (
            f"development_merge_preflight must not reference {tok!r}"
        )


# ---------------------------------------------------------------------------
# Re-import sanity: the module must be importable without flipping
# Step 5 / Level 6 state anywhere.
# ---------------------------------------------------------------------------


def test_reimport_does_not_flip_step5() -> None:
    pre_allowed = pf.step5_implementation_allowed
    pre_substage = pf.STEP5_ENABLED_SUBSTAGE
    importlib.reload(pf)
    assert pf.step5_implementation_allowed is False
    assert pf.STEP5_ENABLED_SUBSTAGE == "none"
    # And the pre-reload state was already correct.
    assert pre_allowed is False
    assert pre_substage == "none"
