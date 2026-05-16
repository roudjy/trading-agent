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
    assert projector.MODULE_VERSION == "v3.15.16.N5b.phase2.projector"


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
        "DRY_RUN_INTENT",
        "MODULE_VERSION",
        "OPERATOR_ACTORS",
        "PREFLIGHT_DIR",
        "PREFLIGHT_LATEST",
        "PREFLIGHT_LATEST_RELATIVE",
        "PREFLIGHT_SNAPSHOT_KEYS",
        "PR_BASE_REF",
        "REPORT_KIND",
        "SCHEMA_VERSION",
        "STEP5_ENABLED_SUBSTAGE",
        "WRITE_PREFIX",
        "build_preflight_snapshot",
        "step5_implementation_allowed",
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
    assert snap["module_version"] == "v3.15.16.N5b.phase2.projector"


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


def test_projector_exposes_no_dry_run_decision_writer() -> None:
    for forbidden in (
        "write_dry_run",
        "write_dry_run_latest",
        "write_decision",
        "write_failure",
        "write_history",
        "write_execution",
    ):
        assert not hasattr(projector, forbidden), (
            f"B2.8c projector must not expose {forbidden!r}; "
            "decision/failure/history writers are B2.8d / B2.8e scope"
        )


def test_projector_relative_path_only_preflight() -> None:
    """The projector exposes exactly the preflight relative path. No
    dry_run / failure / history / decision constants in B2.8c."""
    for forbidden in (
        "DRY_RUN_LATEST_RELATIVE",
        "DRY_RUN_HISTORY_RELATIVE",
        "FAILURE_DIR_RELATIVE",
        "DECISION_LATEST_RELATIVE",
        "EXECUTION_LATEST_RELATIVE",
    ):
        assert not hasattr(projector, forbidden), (
            f"B2.8c projector must not expose {forbidden!r}; only "
            "preflight artefact paths are in scope"
        )
