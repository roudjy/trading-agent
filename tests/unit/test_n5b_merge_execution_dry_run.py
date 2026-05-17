"""Pin tests for the B2.8c N5b Phase 2 dry-run audit projector
(``reporting/n5b_merge_execution_dry_run.py``).

The projector writes ONLY the preflight artefact under
``logs/n5b_merge_execution/preflight/latest.json``. The dry-run
decision artefact, the dry-run history artefact, and the failure
artefact are reserved for B2.8d / B2.8e per the implementation
plan §2.6 and are NOT exercised here.

Defense-in-depth note: forbidden marker strings the tests search
for are NEVER embedded as literals in this file when they would
also trip the runtime source-text scan; markers are assembled at
runtime from constituent parts so the test source stays inert to
scanners.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import n5b_merge_execution_dry_run as projector

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "reporting" / "n5b_merge_execution_dry_run.py"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert projector is not None


def test_module_version_is_pinned_string() -> None:
    assert projector.MODULE_VERSION == "v3.15.16.N5b.phase2.projector_implemented"


def test_schema_version_is_pinned_integer_1() -> None:
    assert projector.SCHEMA_VERSION == 1


def test_report_kind_is_pinned() -> None:
    assert projector.REPORT_KIND == "n5b_preflight"


def test_step5_enabled_substage_is_pinned_none() -> None:
    assert projector.STEP5_ENABLED_SUBSTAGE == "none"


def test_step5_implementation_allowed_is_pinned_false() -> None:
    assert projector.step5_implementation_allowed is False


def test_pr_base_ref_pinned_main() -> None:
    assert projector.PR_BASE_REF == "main"


def test_dry_run_intent_literal() -> None:
    assert projector.DRY_RUN_INTENT == "mobile_approval_dispatch"


def test_operator_actors_closed_vocab() -> None:
    assert projector.OPERATOR_ACTORS == ("session", "operator_token")


def test_write_prefix_sentinel_pinned() -> None:
    assert projector.WRITE_PREFIX == "logs/n5b_merge_execution/"


def test_preflight_relative_path_pinned() -> None:
    assert (
        projector.PREFLIGHT_LATEST_RELATIVE
        == "logs/n5b_merge_execution/preflight/latest.json"
    )


def test_preflight_snapshot_keys_closed_set() -> None:
    assert set(projector.PREFLIGHT_SNAPSHOT_KEYS) == {
        "schema_version",
        "report_kind",
        "module_version",
        "pr_number",
        "pr_head_sha",
        "pr_base_ref",
        "intent",
        "token_kid",
        "nonce_hash",
        "operator_actor",
        "generated_at_utc",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "discipline_invariants",
    }


def test_all_exports_are_closed() -> None:
    assert set(projector.__all__) == {
        "B2_8D_STOP_CONDITIONS",
        "DRY_RUN_DIR",
        "DRY_RUN_HISTORY",
        "DRY_RUN_HISTORY_RELATIVE",
        "DRY_RUN_INTENT",
        "DRY_RUN_LATEST",
        "DRY_RUN_LATEST_RELATIVE",
        "DRY_RUN_PRECONDITION_COUNT",
        "DRY_RUN_PRECONDITION_KEYS",
        "DRY_RUN_REPORT_KIND",
        "DRY_RUN_SNAPSHOT_KEYS",
        "FAILURE_DIR",
        "FAILURE_DIR_RELATIVE",
        "FAILURE_REPORT_KIND",
        "FAILURE_SNAPSHOT_KEYS",
        "MAX_HISTORY_ROWS",
        "MAX_STOP_REASON_LEN",
        "MODULE_VERSION",
        "OPERATOR_ACTORS",
        "PREFLIGHT_DIR",
        "PREFLIGHT_LATEST",
        "PREFLIGHT_LATEST_RELATIVE",
        "PREFLIGHT_SNAPSHOT_KEYS",
        "PROTECTED_PATH_GRANULARITY_VALUES",
        "PR_BASE_REF",
        "REPORT_KIND",
        "REQUIRED_CHECKS_GRANULARITY_VALUES",
        "SCHEMA_VERSION",
        "STEP5_ENABLED_SUBSTAGE",
        "WRITE_PREFIX",
        "append_dry_run_history",
        "build_dry_run_snapshot",
        "build_failure_snapshot",
        "build_preflight_snapshot",
        "step5_implementation_allowed",
        "write_dry_run_latest",
        "write_failure",
        "write_preflight",
    }


# ---------------------------------------------------------------------------
# AST + source-text guards — no forbidden imports / literals
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORTS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "asyncio",
    # B2.8c projector must NOT import the token runtime — the
    # dashboard module (not the projector) handles verification.
    "reporting.approval_token_runtime",
    "reporting.approval_token_gate",
    # No GitHub API client of any flavour.
    "github",
    "ghapi",
    "PyGithub",
)


def _imported_module_names() -> set[str]:
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_module_has_no_forbidden_imports() -> None:
    names = _imported_module_names()
    offending: list[str] = []
    for name in names:
        for forbidden in _FORBIDDEN_IMPORTS:
            if name == forbidden or name.startswith(forbidden + "."):
                offending.append(name)
    assert offending == [], (
        f"projector imports forbidden modules: {offending!r}"
    )


def test_module_does_not_invoke_subprocess_attrs() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "s" + "ubprocess.run",
        "s" + "ubprocess.Popen",
        "s" + "ubprocess.call",
        "s" + "ubprocess.check_call",
        "s" + "ubprocess.check_output",
        "o" + "s.system",
        "o" + "s.popen",
    )
    hits = [m for m in forbidden if m in src]
    assert hits == [], (
        f"projector source contains shell-spawning attribute: {hits!r}"
    )


def test_module_contains_no_gh_or_git_shellout_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literals = (
        "g" + "h " + "pr " + "merge",
        "g" + "it " + "merge",
        "--" + "admin",
        "--" + "no-verify",
        "p" + "r_merge_approved",
        "m" + "erge" + "Pull" + "Request",
    )
    hits = [m for m in forbidden_literals if m in src]
    assert hits == [], (
        f"projector source contains forbidden shell-out / mutation literal: {hits!r}"
    )


def test_module_does_not_read_env_vars() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "o" + "s.environ",
        "o" + "s.getenv",
        "g" + "etenv(",
    )
    hits = [m for m in forbidden if m in src]
    assert hits == [], (
        f"projector source reads environment variables: {hits!r}"
    )


def test_module_source_pins_step5_invariants() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


def test_module_does_not_carry_token_or_raw_nonce_field_names() -> None:
    """The closed schema must NOT include ``token`` or a raw
    ``nonce`` field — only the verified ``token_kid`` and the
    sha256-hashed ``nonce_hash``."""
    keys = set(projector.PREFLIGHT_SNAPSHOT_KEYS)
    assert "token" not in keys
    assert "nonce" not in keys
    # Sanity: the hashed alternatives ARE in the schema.
    assert "token_kid" in keys
    assert "nonce_hash" in keys


# ---------------------------------------------------------------------------
# build_preflight_snapshot — value-shape invariants
# ---------------------------------------------------------------------------


def _good_kwargs() -> dict[str, Any]:
    nonce_hash = hashlib.sha256(b"synthetic-nonce-for-test").hexdigest()
    return {
        "pr_number": 42,
        "pr_head_sha": "deadbeef" * 5,
        "token_kid": "k1",
        "nonce_hash": nonce_hash,
        "operator_actor": "session",
        "generated_at_utc": "2026-05-16T12:00:00Z",
    }


def test_build_snapshot_happy_path_returns_closed_schema() -> None:
    snap = projector.build_preflight_snapshot(**_good_kwargs())
    assert set(snap.keys()) == set(projector.PREFLIGHT_SNAPSHOT_KEYS)
    # Discipline invariants mirrored verbatim.
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    # Closed scalars.
    assert snap["pr_base_ref"] == "main"
    assert snap["intent"] == "mobile_approval_dispatch"
    assert snap["schema_version"] == 1
    assert snap["report_kind"] == "n5b_preflight"
    assert snap["module_version"] == "v3.15.16.N5b.phase2.projector_implemented"


def test_build_snapshot_discipline_invariants_dict_present() -> None:
    snap = projector.build_preflight_snapshot(**_good_kwargs())
    inv = snap["discipline_invariants"]
    assert isinstance(inv, dict)
    assert inv["dry_run_only"] is True
    assert inv["live_merge_implemented"] is False
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


@pytest.mark.parametrize(
    "field,bad_value,exc",
    [
        ("pr_number", "42", TypeError),
        ("pr_number", True, TypeError),
        ("pr_number", 0, ValueError),
        ("pr_number", -1, ValueError),
        ("pr_head_sha", "", ValueError),
        ("pr_head_sha", "x" * 65, ValueError),
        ("token_kid", "", ValueError),
        ("token_kid", "k" * 65, ValueError),
        ("nonce_hash", "", ValueError),
        ("nonce_hash", "ab" * 31, ValueError),  # only 62 chars
        ("nonce_hash", "G" * 64, ValueError),  # bad charset
        ("operator_actor", "bogus_actor", ValueError),
        ("generated_at_utc", "", ValueError),
    ],
)
def test_build_snapshot_rejects_bad_inputs(
    field: str, bad_value: Any, exc: type[BaseException]
) -> None:
    kwargs = _good_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(exc):
        projector.build_preflight_snapshot(**kwargs)


def test_build_snapshot_accepts_operator_token_actor() -> None:
    kwargs = _good_kwargs()
    kwargs["operator_actor"] = "operator_token"
    snap = projector.build_preflight_snapshot(**kwargs)
    assert snap["operator_actor"] == "operator_token"


# ---------------------------------------------------------------------------
# write_preflight — sentinel-restricted, atomic
# ---------------------------------------------------------------------------


def _tmp_preflight_path(tmp_path: Path) -> Path:
    target = (
        tmp_path
        / "logs"
        / "n5b_merge_execution"
        / "preflight"
        / "latest.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def test_write_preflight_writes_closed_schema_to_target(
    tmp_path: Path,
) -> None:
    target = _tmp_preflight_path(tmp_path)
    out = projector.write_preflight(
        target_path=target,
        **_good_kwargs(),
    )
    assert out == target
    assert target.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(projector.PREFLIGHT_SNAPSHOT_KEYS)
    assert payload["pr_number"] == 42
    assert payload["pr_base_ref"] == "main"
    assert payload["intent"] == "mobile_approval_dispatch"


def test_write_preflight_refuses_non_sentinel_path(tmp_path: Path) -> None:
    """The sentinel guard refuses any path that does NOT contain the
    closed ``logs/n5b_merge_execution/`` substring."""
    bogus = tmp_path / "logs" / "elsewhere" / "preflight.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        projector.write_preflight(target_path=bogus, **_good_kwargs())
    # No file written.
    assert not bogus.is_file()


def test_write_preflight_atomic_no_tmp_residue(tmp_path: Path) -> None:
    target = _tmp_preflight_path(tmp_path)
    projector.write_preflight(target_path=target, **_good_kwargs())
    # No leftover tempfiles in the target's parent.
    leftovers = [
        p
        for p in target.parent.iterdir()
        if p.name.startswith(".n5b_merge_execution_dry_run.")
    ]
    assert leftovers == []


def test_write_preflight_overwrites_existing_atomically(
    tmp_path: Path,
) -> None:
    target = _tmp_preflight_path(tmp_path)
    target.write_text('{"prior": "content"}', encoding="utf-8")
    projector.write_preflight(target_path=target, **_good_kwargs())
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "prior" not in payload
    assert payload["report_kind"] == "n5b_preflight"


def test_write_preflight_runs_assert_no_secrets_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``assert_no_secrets`` raises, NO file is created."""
    target = _tmp_preflight_path(tmp_path)
    # Replace the redactor with one that always raises.
    def _boom(_payload: dict[str, Any]) -> None:
        raise AssertionError("simulated credential leak")

    monkeypatch.setattr(projector, "assert_no_secrets", _boom)
    with pytest.raises(AssertionError):
        projector.write_preflight(target_path=target, **_good_kwargs())
    assert not target.is_file()


# ---------------------------------------------------------------------------
# No deferred-artefact writers — preflight only in B2.8c
# ---------------------------------------------------------------------------


def test_projector_exposes_no_decision_or_execution_writer() -> None:
    """B2.8e adds ``write_dry_run_latest`` + ``append_dry_run_history``.
    Decision / execution writers remain reserved for N5b Phase 3+
    (live execute endpoint) and MUST NOT be added without a separate
    operator-go and parent-doc §10 promotion."""
    for forbidden in (
        "write_decision",
        "write_execution",
    ):
        assert not hasattr(projector, forbidden), (
            f"B2.8e projector must not expose {forbidden!r}; "
            "decision/execution writers are Phase 3+ scope"
        )


def test_projector_relative_path_no_decision_or_execution() -> None:
    """The decision / execution path constants remain reserved for
    Phase 3+ (live execute endpoint)."""
    for forbidden in (
        "DECISION_LATEST_RELATIVE",
        "EXECUTION_LATEST_RELATIVE",
    ):
        assert not hasattr(projector, forbidden), (
            f"B2.8e projector must not expose {forbidden!r}; only "
            "preflight + failure + dry_run artefact paths are in scope"
        )


# ---------------------------------------------------------------------------
# B2.8d additions — failure artefact closed schema + write_failure
# ---------------------------------------------------------------------------


def test_failure_report_kind_pinned() -> None:
    assert projector.FAILURE_REPORT_KIND == "n5b_failure"


def test_failure_dir_relative_pinned() -> None:
    assert projector.FAILURE_DIR_RELATIVE == "logs/n5b_merge_execution/failure/"


def test_failure_snapshot_keys_closed_set() -> None:
    assert set(projector.FAILURE_SNAPSHOT_KEYS) == {
        "schema_version",
        "report_kind",
        "module_version",
        "cycle_id",
        "pr_number",
        "pr_head_sha",
        "pr_base_ref",
        "intent",
        "stop_condition",
        "stop_reason",
        "preconditions_evaluated",
        "preconditions_passed",
        "operator_actor",
        "generated_at_utc",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "discipline_invariants",
    }


def test_b2_8d_stop_conditions_closed_vocab() -> None:
    """The B2.8d stop-condition closed list. Adding a literal here
    requires a paired doc update (governance §6.3) AND an updated
    pin in the same PR."""
    assert set(projector.B2_8D_STOP_CONDITIONS) == {
        "token_missing",
        "token_invalid",
        "replay_detected",
        "binding_mismatch",
        "pr_number_mismatch",
        "head_sha_mismatch",
        "merge_state_not_clean",
        "checks_not_green",
        "branch_protection_not_satisfied",
        "unexpected_files_touched",
        "deploy_coupling_detected",
        "step5_flag_changed",
        "level_6_attempted",
        "protected_path_violation",
        "stale_recommendation",
        "network_uncertain",
        "audit_write_failure",
    }


def test_max_stop_reason_len_pinned() -> None:
    assert projector.MAX_STOP_REASON_LEN == 200


def _good_failure_kwargs() -> dict[str, Any]:
    return {
        "cycle_id": "pr123_20260516T093417Z",
        "pr_number": 123,
        "pr_head_sha": "deadbeef" * 5,
        "stop_condition": "merge_state_not_clean",
        "stop_reason": "A22 merge_state_status = BLOCKED",
        "preconditions_evaluated": 9,
        "preconditions_passed": 8,
        "operator_actor": "session",
        "generated_at_utc": "2026-05-16T09:34:17Z",
    }


def test_build_failure_snapshot_happy_path() -> None:
    snap = projector.build_failure_snapshot(**_good_failure_kwargs())
    assert set(snap.keys()) == set(projector.FAILURE_SNAPSHOT_KEYS)
    assert snap["report_kind"] == "n5b_failure"
    assert snap["cycle_id"] == "pr123_20260516T093417Z"
    assert snap["stop_condition"] == "merge_state_not_clean"
    assert snap["preconditions_evaluated"] == 9
    assert snap["preconditions_passed"] == 8
    # Discipline invariants mirrored.
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    assert snap["pr_base_ref"] == "main"
    assert snap["intent"] == "mobile_approval_dispatch"


def test_build_failure_snapshot_truncates_stop_reason() -> None:
    kwargs = _good_failure_kwargs()
    kwargs["stop_reason"] = "x" * 500
    snap = projector.build_failure_snapshot(**kwargs)
    assert len(snap["stop_reason"]) == projector.MAX_STOP_REASON_LEN


def test_build_failure_snapshot_rejects_unknown_stop_condition() -> None:
    kwargs = _good_failure_kwargs()
    kwargs["stop_condition"] = "not_a_real_stop_condition"
    with pytest.raises(ValueError):
        projector.build_failure_snapshot(**kwargs)


@pytest.mark.parametrize(
    "field,bad_value,exc",
    [
        ("cycle_id", "", ValueError),
        ("cycle_id", "with space", ValueError),
        ("cycle_id", "with/slash", ValueError),
        ("cycle_id", "with.dot", ValueError),
        ("cycle_id", "x" * 200, ValueError),
        ("pr_number", "123", TypeError),
        ("pr_number", True, TypeError),
        ("pr_number", 0, ValueError),
        ("pr_head_sha", "", ValueError),
        ("pr_head_sha", "x" * 65, ValueError),
        ("preconditions_evaluated", "9", TypeError),
        ("preconditions_evaluated", True, TypeError),
        ("preconditions_evaluated", -1, ValueError),
        ("preconditions_passed", -1, ValueError),
        ("operator_actor", "bogus", ValueError),
        ("generated_at_utc", "", ValueError),
    ],
)
def test_build_failure_snapshot_rejects_bad_inputs(
    field: str, bad_value: Any, exc: type[BaseException]
) -> None:
    kwargs = _good_failure_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(exc):
        projector.build_failure_snapshot(**kwargs)


def test_build_failure_snapshot_rejects_passed_gt_evaluated() -> None:
    kwargs = _good_failure_kwargs()
    kwargs["preconditions_passed"] = 10
    kwargs["preconditions_evaluated"] = 5
    with pytest.raises(ValueError):
        projector.build_failure_snapshot(**kwargs)


def _tmp_failure_path(tmp_path: Path, cycle_id: str) -> Path:
    target = (
        tmp_path
        / "logs"
        / "n5b_merge_execution"
        / "failure"
        / f"{cycle_id}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def test_write_failure_writes_closed_schema_to_target(tmp_path: Path) -> None:
    kwargs = _good_failure_kwargs()
    target = _tmp_failure_path(tmp_path, kwargs["cycle_id"])
    out = projector.write_failure(target_path=target, **kwargs)
    assert out == target
    assert target.is_file()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(projector.FAILURE_SNAPSHOT_KEYS)
    assert payload["stop_condition"] == "merge_state_not_clean"
    assert payload["cycle_id"] == "pr123_20260516T093417Z"


def test_write_failure_refuses_non_sentinel_path(tmp_path: Path) -> None:
    """The sentinel guard refuses any path that does NOT contain
    ``logs/n5b_merge_execution/``."""
    kwargs = _good_failure_kwargs()
    bogus = tmp_path / "logs" / "elsewhere" / f"{kwargs['cycle_id']}.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        projector.write_failure(target_path=bogus, **kwargs)
    assert not bogus.is_file()


def test_write_failure_atomic_no_tmp_residue(tmp_path: Path) -> None:
    kwargs = _good_failure_kwargs()
    target = _tmp_failure_path(tmp_path, kwargs["cycle_id"])
    projector.write_failure(target_path=target, **kwargs)
    leftovers = [
        p
        for p in target.parent.iterdir()
        if p.name.startswith(".n5b_merge_execution_dry_run.")
    ]
    assert leftovers == []


def test_write_failure_runs_assert_no_secrets_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If ``assert_no_secrets`` raises, NO failure file is created."""
    kwargs = _good_failure_kwargs()
    target = _tmp_failure_path(tmp_path, kwargs["cycle_id"])

    def _boom(_payload: dict[str, Any]) -> None:
        raise AssertionError("simulated credential leak")

    monkeypatch.setattr(projector, "assert_no_secrets", _boom)
    with pytest.raises(AssertionError):
        projector.write_failure(target_path=target, **kwargs)
    assert not target.is_file()


@pytest.mark.parametrize(
    "stop_condition",
    sorted({
        "token_missing", "token_invalid", "replay_detected",
        "binding_mismatch", "pr_number_mismatch",
        "head_sha_mismatch", "merge_state_not_clean", "checks_not_green",
        "branch_protection_not_satisfied", "unexpected_files_touched",
        "deploy_coupling_detected", "step5_flag_changed",
        "level_6_attempted", "protected_path_violation",
        "stale_recommendation", "network_uncertain", "audit_write_failure",
    }),
)
def test_write_failure_accepts_each_closed_stop(
    stop_condition: str, tmp_path: Path
) -> None:
    """Every closed §6.3 / B2.8c stop must be writable as a
    failure artefact."""
    kwargs = _good_failure_kwargs()
    kwargs["stop_condition"] = stop_condition
    kwargs["cycle_id"] = f"pr1_{stop_condition[:20]}"
    target = _tmp_failure_path(tmp_path, kwargs["cycle_id"])
    projector.write_failure(target_path=target, **kwargs)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["stop_condition"] == stop_condition


# ---------------------------------------------------------------------------
# B2.8e additions — dry-run snapshot closed schema + writers
# ---------------------------------------------------------------------------


def test_dry_run_report_kind_pinned() -> None:
    assert projector.DRY_RUN_REPORT_KIND == "n5b_dry_run"


def test_dry_run_latest_relative_pinned() -> None:
    assert projector.DRY_RUN_LATEST_RELATIVE == (
        "logs/n5b_merge_execution/dry_run/latest.json"
    )


def test_dry_run_history_relative_pinned() -> None:
    assert projector.DRY_RUN_HISTORY_RELATIVE == (
        "logs/n5b_merge_execution/dry_run/history.jsonl"
    )


def test_max_history_rows_pinned() -> None:
    assert projector.MAX_HISTORY_ROWS == 1024


def test_dry_run_precondition_keys_closed_set() -> None:
    assert projector.DRY_RUN_PRECONDITION_COUNT == 17
    assert projector.DRY_RUN_PRECONDITION_KEYS == tuple(
        f"precondition_{i}" for i in range(1, 18)
    )


def test_required_checks_granularity_closed_vocab() -> None:
    """B2.8e ships only the rollup-only signal. Future per-check
    granularity requires an upstream extension AND an updated pin."""
    assert projector.REQUIRED_CHECKS_GRANULARITY_VALUES == ("rollup_only",)


def test_protected_path_granularity_closed_vocab() -> None:
    """B2.8e ships only the boolean signal. Future per-file
    granularity requires an upstream extension AND an updated pin."""
    assert projector.PROTECTED_PATH_GRANULARITY_VALUES == ("boolean_only",)


def test_dry_run_snapshot_keys_closed_set() -> None:
    assert set(projector.DRY_RUN_SNAPSHOT_KEYS) == {
        "schema_version",
        "report_kind",
        "module_version",
        "pr_number",
        "pr_head_sha",
        "pr_base_ref",
        "intent",
        "token_kid",
        "nonce_hash",
        "operator_actor",
        "generated_at_utc",
        "preconditions",
        "recommendation_action_seen",
        "recommendation_reason_seen",
        "merge_state_status_seen",
        "required_checks_summary",
        "required_checks_granularity",
        "protected_path_violations",
        "protected_path_granularity",
        "would_proceed",
        "stop_condition",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "discipline_invariants",
    }


def _all_pass_preconditions() -> dict[str, bool]:
    return {key: True for key in projector.DRY_RUN_PRECONDITION_KEYS}


def _good_dry_run_kwargs() -> dict[str, Any]:
    return {
        "pr_number": 123,
        "pr_head_sha": "deadbeef" * 5,
        "token_kid": "k1",
        "nonce_hash": hashlib.sha256(b"synthetic-nonce").hexdigest(),
        "operator_actor": "session",
        "generated_at_utc": "2026-05-16T15:00:00Z",
        "preconditions": _all_pass_preconditions(),
        "recommendation_action_seen": "recommend_human_merge",
        "recommendation_reason_seen": "pr_clean_and_no_blocking_inbox",
        "merge_state_status_seen": "CLEAN",
        "required_checks_summary": {"_rollup": "SUCCESS"},
        "required_checks_granularity": "rollup_only",
        "protected_path_violations": [],
        "protected_path_granularity": "boolean_only",
        "would_proceed": True,
        "stop_condition": None,
    }


def test_build_dry_run_snapshot_happy_path() -> None:
    snap = projector.build_dry_run_snapshot(**_good_dry_run_kwargs())
    assert set(snap.keys()) == set(projector.DRY_RUN_SNAPSHOT_KEYS)
    assert snap["report_kind"] == "n5b_dry_run"
    assert snap["would_proceed"] is True
    assert snap["stop_condition"] is None
    assert snap["pr_base_ref"] == "main"
    assert snap["intent"] == "mobile_approval_dispatch"
    # Discipline invariants preserved on the ok envelope.
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    # Granularity sentinels.
    assert snap["required_checks_granularity"] == "rollup_only"
    assert snap["protected_path_granularity"] == "boolean_only"


def test_build_dry_run_snapshot_rejected_path() -> None:
    kwargs = _good_dry_run_kwargs()
    failing = _all_pass_preconditions()
    failing["precondition_9"] = False
    kwargs["preconditions"] = failing
    kwargs["would_proceed"] = False
    kwargs["stop_condition"] = "merge_state_not_clean"
    snap = projector.build_dry_run_snapshot(**kwargs)
    assert snap["would_proceed"] is False
    assert snap["stop_condition"] == "merge_state_not_clean"


def test_build_dry_run_snapshot_rejects_unknown_stop_condition() -> None:
    kwargs = _good_dry_run_kwargs()
    kwargs["would_proceed"] = False
    kwargs["stop_condition"] = "made_up_stop"
    with pytest.raises(ValueError):
        projector.build_dry_run_snapshot(**kwargs)


def test_build_dry_run_snapshot_rejects_would_proceed_with_stop() -> None:
    """would_proceed=True with a non-null stop_condition is a
    contradiction; the builder must reject it."""
    kwargs = _good_dry_run_kwargs()
    kwargs["would_proceed"] = True
    kwargs["stop_condition"] = "merge_state_not_clean"
    with pytest.raises(ValueError):
        projector.build_dry_run_snapshot(**kwargs)


def test_build_dry_run_snapshot_rejects_no_stop_when_not_proceeding() -> None:
    kwargs = _good_dry_run_kwargs()
    kwargs["would_proceed"] = False
    kwargs["stop_condition"] = None
    with pytest.raises(ValueError):
        projector.build_dry_run_snapshot(**kwargs)


@pytest.mark.parametrize(
    "field,bad_value,exc",
    [
        ("preconditions", {"precondition_1": True}, ValueError),  # missing 16 keys
        ("preconditions", "not_a_dict", TypeError),
        ("required_checks_summary", {}, ValueError),  # empty dict
        ("required_checks_summary", "not_a_dict", TypeError),
        ("required_checks_granularity", "per_check", ValueError),  # not in vocab
        ("protected_path_granularity", "per_file", ValueError),  # not in vocab
        ("protected_path_violations", "not_a_list", TypeError),
        ("protected_path_violations", [123], TypeError),  # non-str entry
        ("would_proceed", "true", TypeError),
    ],
)
def test_build_dry_run_snapshot_rejects_bad_inputs(
    field: str, bad_value: Any, exc: type[BaseException]
) -> None:
    kwargs = _good_dry_run_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(exc):
        projector.build_dry_run_snapshot(**kwargs)


def test_build_dry_run_snapshot_preconditions_must_be_bool() -> None:
    kwargs = _good_dry_run_kwargs()
    bad = _all_pass_preconditions()
    bad["precondition_5"] = "yes"  # type: ignore[assignment]
    kwargs["preconditions"] = bad
    with pytest.raises(TypeError):
        projector.build_dry_run_snapshot(**kwargs)


def _tmp_dry_run_paths(tmp_path: Path) -> tuple[Path, Path]:
    """Return ``(latest_path, history_path)`` under the tmp sentinel."""
    base = tmp_path / "logs" / "n5b_merge_execution" / "dry_run"
    base.mkdir(parents=True, exist_ok=True)
    return base / "latest.json", base / "history.jsonl"


def test_write_dry_run_latest_writes_closed_schema(tmp_path: Path) -> None:
    latest, _history = _tmp_dry_run_paths(tmp_path)
    out = projector.write_dry_run_latest(target_path=latest, **_good_dry_run_kwargs())
    assert out == latest
    assert latest.is_file()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(projector.DRY_RUN_SNAPSHOT_KEYS)
    assert payload["report_kind"] == "n5b_dry_run"
    assert payload["would_proceed"] is True


def test_write_dry_run_latest_refuses_non_sentinel_path(tmp_path: Path) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "latest.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        projector.write_dry_run_latest(target_path=bogus, **_good_dry_run_kwargs())
    assert not bogus.is_file()


def test_write_dry_run_latest_runs_assert_no_secrets_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest, _history = _tmp_dry_run_paths(tmp_path)

    def _boom(_payload: dict[str, Any]) -> None:
        raise AssertionError("simulated credential leak")

    monkeypatch.setattr(projector, "assert_no_secrets", _boom)
    with pytest.raises(AssertionError):
        projector.write_dry_run_latest(
            target_path=latest, **_good_dry_run_kwargs()
        )
    assert not latest.is_file()


def test_append_dry_run_history_creates_file_and_appends_line(
    tmp_path: Path,
) -> None:
    _latest, history = _tmp_dry_run_paths(tmp_path)
    out = projector.append_dry_run_history(
        target_path=history, **_good_dry_run_kwargs()
    )
    assert out == history
    assert history.is_file()
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row.keys()) == set(projector.DRY_RUN_SNAPSHOT_KEYS)


def test_append_dry_run_history_appends_to_existing_file(tmp_path: Path) -> None:
    _latest, history = _tmp_dry_run_paths(tmp_path)
    projector.append_dry_run_history(
        target_path=history, **_good_dry_run_kwargs()
    )
    second = _good_dry_run_kwargs()
    second["generated_at_utc"] = "2026-05-16T15:01:00Z"
    projector.append_dry_run_history(target_path=history, **second)
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 2


def test_append_dry_run_history_compacts_to_max_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Shrink retention so the test is cheap.
    monkeypatch.setattr(projector, "MAX_HISTORY_ROWS", 5)
    _latest, history = _tmp_dry_run_paths(tmp_path)
    for i in range(12):
        kwargs = _good_dry_run_kwargs()
        kwargs["generated_at_utc"] = f"2026-05-16T15:00:{i:02d}Z"
        projector.append_dry_run_history(target_path=history, **kwargs)
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 5
    # The newest entry is the last appended.
    rows = [json.loads(line) for line in lines]
    assert rows[-1]["generated_at_utc"] == "2026-05-16T15:00:11Z"


def test_append_dry_run_history_refuses_non_sentinel_path(tmp_path: Path) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "history.jsonl"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        projector.append_dry_run_history(
            target_path=bogus, **_good_dry_run_kwargs()
        )
    assert not bogus.is_file()


def test_append_dry_run_history_runs_assert_no_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _latest, history = _tmp_dry_run_paths(tmp_path)

    def _boom(_payload: dict[str, Any]) -> None:
        raise AssertionError("simulated credential leak")

    monkeypatch.setattr(projector, "assert_no_secrets", _boom)
    with pytest.raises(AssertionError):
        projector.append_dry_run_history(
            target_path=history, **_good_dry_run_kwargs()
        )
    assert not history.is_file()


def test_dry_run_schema_carries_no_raw_token_or_nonce_field_name() -> None:
    """Closed schema must NOT include ``token`` or a raw ``nonce``
    field — only the verified ``token_kid`` and the sha256-hashed
    ``nonce_hash``."""
    keys = set(projector.DRY_RUN_SNAPSHOT_KEYS)
    assert "token" not in keys
    assert "nonce" not in keys
    assert "token_kid" in keys
    assert "nonce_hash" in keys


def test_dry_run_snapshot_carries_granularity_sentinels_explicitly() -> None:
    """Operator-mandated contract: the artefact and tests must make
    clear that ``required_checks_granularity`` and
    ``protected_path_granularity`` are bounded ('rollup_only' /
    'boolean_only') and do not imply per-check or per-file
    coverage. This pin prevents silent removal of either sentinel
    from the closed schema."""
    keys = set(projector.DRY_RUN_SNAPSHOT_KEYS)
    assert "required_checks_granularity" in keys
    assert "protected_path_granularity" in keys


def test_module_source_pins_step5_invariants_still_intact() -> None:
    """Re-pinned for B2.8e — the new dry_run + history writers must
    not flip Step 5 invariants."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
