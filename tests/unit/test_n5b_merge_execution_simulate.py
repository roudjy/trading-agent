"""Pin tests for the B2.9b N5b Phase 3 recorded-fixture simulator
projector (``reporting/n5b_merge_execution_simulate.py``).

The projector writes ONLY the simulation artefacts under
``logs/n5b_merge_execution/phase3_simulation/``. It never calls
GitHub, never opens a network socket, never spawns a subprocess,
never reads an environment variable. The closed fixture +
snapshot schemas are pinned here.

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

from reporting import n5b_merge_execution_simulate as sim

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "reporting" / "n5b_merge_execution_simulate.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "n5b" / "recorded_merge_simulation"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert sim is not None


def test_module_version_is_pinned_string() -> None:
    assert sim.MODULE_VERSION == "v3.15.16.N5b.phase3.simulator_projector"


def test_schema_version_is_pinned_integer_1() -> None:
    assert sim.SCHEMA_VERSION == 1


def test_report_kind_is_pinned_singleton() -> None:
    assert sim.REPORT_KIND == "n5b_phase3_simulation"


def test_step5_enabled_substage_is_pinned_none() -> None:
    assert sim.STEP5_ENABLED_SUBSTAGE == "none"


def test_step5_implementation_allowed_is_pinned_false() -> None:
    assert sim.step5_implementation_allowed is False


def test_pr_base_ref_pinned_main() -> None:
    assert sim.PR_BASE_REF == "main"


def test_dry_run_intent_literal_reused_from_b2_8e() -> None:
    """No new N4b intent literal — the simulator reuses
    ``mobile_approval_dispatch``."""
    assert sim.DRY_RUN_INTENT == "mobile_approval_dispatch"


def test_operator_actors_closed_vocab() -> None:
    assert sim.OPERATOR_ACTORS == ("session", "operator_token")


def test_operator_confirmation_marker_singleton() -> None:
    assert sim.OPERATOR_CONFIRMATION_MARKER == "simulator_execute_confirmed"


def test_write_prefix_sentinel_pinned() -> None:
    """Same sentinel as B2.8c-e — no new write-prefix introduced."""
    assert sim.WRITE_PREFIX == "logs/n5b_merge_execution/"


def test_phase3_simulation_relative_paths_pinned() -> None:
    assert sim.PHASE3_SIMULATION_LATEST_RELATIVE == (
        "logs/n5b_merge_execution/phase3_simulation/latest.json"
    )
    assert sim.PHASE3_SIMULATION_HISTORY_RELATIVE == (
        "logs/n5b_merge_execution/phase3_simulation/history.jsonl"
    )


def test_target_classification_singleton_vocab() -> None:
    """Phase 4 ``production_pr_merge`` is NEVER in this vocab."""
    assert sim.TARGET_CLASSIFICATION_VALUES == ("recorded_fixture_simulator",)
    assert "production_pr_merge" not in sim.TARGET_CLASSIFICATION_VALUES


def test_mode_singleton_vocab() -> None:
    assert sim.MODE_VALUES == ("simulate_only",)


def test_merge_classification_closed_vocab() -> None:
    assert sim.MERGE_CLASSIFICATION_VALUES == (
        "merged_ok",
        "merged_with_warnings",
        "refused_by_github",
        "network_uncertain",
    )


def test_accepted_merge_method_singleton() -> None:
    assert sim.ACCEPTED_MERGE_METHOD == "squash"


def test_fixture_kind_singleton() -> None:
    assert sim.FIXTURE_KIND == "n5b_phase3_recorded_merge_simulation"


def test_fixture_schema_keys_closed_set() -> None:
    assert set(sim.FIXTURE_SCHEMA_KEYS) == {
        "fixture_schema_version",
        "fixture_kind",
        "merge_response",
        "generated_at_utc",
        "fixture_notes",
    }


def test_fixture_required_keys_closed_set() -> None:
    assert set(sim.FIXTURE_REQUIRED_KEYS) == {
        "fixture_schema_version",
        "fixture_kind",
        "merge_response",
        "generated_at_utc",
    }


def test_fixture_merge_response_keys_closed_set() -> None:
    assert set(sim.FIXTURE_MERGE_RESPONSE_KEYS) == {
        "http_status",
        "classification",
        "post_merge_head_sha",
        "merge_method",
        "delete_branch",
    }


def test_max_history_rows_pinned() -> None:
    assert sim.MAX_HISTORY_ROWS == 1024


def test_simulator_safety_invariant_keys_closed_set() -> None:
    assert set(sim.SIMULATOR_SAFETY_INVARIANT_KEYS) == {
        "no_real_github_merge",
        "no_production_merge",
        "no_network",
        "no_git_or_gh_or_subprocess",
        "no_step5_runtime",
        "no_level6",
        "no_live_trading",
        "no_paper_shadow_runtime",
    }


def test_simulate_snapshot_keys_closed_set() -> None:
    assert set(sim.SIMULATE_SNAPSHOT_KEYS) == {
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
        "operator_confirmation_marker",
        "generated_at_utc",
        "target_classification",
        "mode",
        "fixture_kind",
        "fixture_schema_version",
        "fixture_generated_at_utc",
        "merge_response_http_status",
        "merge_response_classification",
        "merge_response_post_merge_head_sha",
        "merge_response_merge_method",
        "merge_response_delete_branch",
        "would_proceed",
        "simulator_safety_invariants",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "discipline_invariants",
    }


def test_all_exports_are_closed() -> None:
    assert set(sim.__all__) == {
        "ACCEPTED_MERGE_METHOD",
        "DRY_RUN_INTENT",
        "FIXTURE_KIND",
        "FIXTURE_MERGE_RESPONSE_KEYS",
        "FIXTURE_REQUIRED_KEYS",
        "FIXTURE_SCHEMA_KEYS",
        "MAX_HISTORY_ROWS",
        "MERGE_CLASSIFICATION_VALUES",
        "MODE_VALUES",
        "MODULE_VERSION",
        "OPERATOR_ACTORS",
        "OPERATOR_CONFIRMATION_MARKER",
        "PHASE3_SIMULATION_DIR",
        "PHASE3_SIMULATION_HISTORY",
        "PHASE3_SIMULATION_HISTORY_RELATIVE",
        "PHASE3_SIMULATION_LATEST",
        "PHASE3_SIMULATION_LATEST_RELATIVE",
        "PR_BASE_REF",
        "REPORT_KIND",
        "SCHEMA_VERSION",
        "SIMULATE_SNAPSHOT_KEYS",
        "SIMULATOR_SAFETY_INVARIANT_KEYS",
        "STEP5_ENABLED_SUBSTAGE",
        "TARGET_CLASSIFICATION_VALUES",
        "WRITE_PREFIX",
        "append_simulate_history",
        "build_simulate_snapshot",
        "read_fixture",
        "step5_implementation_allowed",
        "write_simulate_latest",
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
    "reporting.approval_token_runtime",
    "reporting.approval_token_gate",
    "reporting.github_pr_lifecycle",
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
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def test_module_has_no_forbidden_imports() -> None:
    names = _imported_module_names()
    offending: list[str] = []
    for name in names:
        for forbidden in _FORBIDDEN_IMPORTS:
            if name == forbidden or name.startswith(forbidden + "."):
                offending.append(name)
    assert offending == [], (
        f"simulator projector imports forbidden modules: {offending!r}"
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
        f"simulator projector contains shell-spawning attribute: {hits!r}"
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
        f"simulator projector contains forbidden literal: {hits!r}"
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
        f"simulator projector reads environment variables: {hits!r}"
    )


def test_module_source_pins_step5_invariants() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


def test_module_does_not_carry_token_or_raw_nonce_field_names() -> None:
    """Closed schema must NOT include ``token`` or raw ``nonce``
    field — only ``token_kid`` + sha256-hashed ``nonce_hash``."""
    keys = set(sim.SIMULATE_SNAPSHOT_KEYS)
    assert "token" not in keys
    assert "nonce" not in keys
    assert "token_kid" in keys
    assert "nonce_hash" in keys


def test_module_source_never_mentions_production_pr_merge_literal() -> None:
    """The Phase 4 production-merge literal must never appear
    anywhere in the simulator projector source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "production_pr_merge" not in src, (
        "simulator projector must never mention the Phase 4 "
        "'production_pr_merge' literal"
    )


def test_module_source_never_mentions_live_execute_env_flag() -> None:
    """The Phase 4 env flag must never appear in the simulator
    projector source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "ADE_N5B_LIVE_EXECUTE_ENABLED" not in src, (
        "simulator projector must never mention the Phase 4 "
        "'ADE_N5B_LIVE_EXECUTE_ENABLED' env flag"
    )


def test_module_source_never_mentions_n5b_execution_report_kind() -> None:
    """The Phase 4 execution-artefact report_kind must never
    appear in the simulator projector source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # The simulator uses "n5b_phase3_simulation"; "n5b_execution"
    # is reserved for Phase 4 and must not appear.
    assert '"n5b_execution"' not in src, (
        "simulator projector must never mention the Phase 4 "
        "report_kind 'n5b_execution'"
    )


# ---------------------------------------------------------------------------
# Fixture reader — closed-shape validation
# ---------------------------------------------------------------------------


def _read_canned(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_canned_merged_ok_fixture_parses() -> None:
    data = sim.read_fixture(FIXTURE_DIR / "merged_ok.json")
    assert data["fixture_kind"] == "n5b_phase3_recorded_merge_simulation"
    assert data["merge_response"]["classification"] == "merged_ok"


def test_canned_refused_by_github_fixture_parses() -> None:
    data = sim.read_fixture(FIXTURE_DIR / "refused_by_github.json")
    assert data["merge_response"]["classification"] == "refused_by_github"


def test_fixture_read_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        sim.read_fixture(tmp_path / "nonexistent.json")


def test_fixture_read_rejects_non_json_content(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_non_object_top_level(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_unknown_top_level_keys(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["unknown_field"] = "evil"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_missing_required_keys(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    del payload["generated_at_utc"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_wrong_fixture_kind(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["fixture_kind"] = "not_the_singleton"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_wrong_schema_version(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["fixture_schema_version"] = 999
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_unknown_merge_response_keys(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["merge_response"]["extra_field"] = "evil"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_non_squash_merge_method(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["merge_response"]["merge_method"] = "rebase"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_unknown_classification(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["merge_response"]["classification"] = "made_up_classification"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


def test_fixture_read_rejects_oversized_notes(tmp_path: Path) -> None:
    payload = _read_canned("merged_ok.json")
    payload["fixture_notes"] = "x" * 1000
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        sim.read_fixture(bad)


# ---------------------------------------------------------------------------
# build_simulate_snapshot — value-shape invariants
# ---------------------------------------------------------------------------


def _good_snapshot_kwargs() -> dict[str, Any]:
    return {
        "pr_number": 42,
        "pr_head_sha": "deadbeef" * 5,
        "token_kid": "k1",
        "nonce_hash": hashlib.sha256(b"synth-nonce").hexdigest(),
        "operator_actor": "session",
        "operator_confirmation_marker": "simulator_execute_confirmed",
        "generated_at_utc": "2026-05-17T10:00:00Z",
        "fixture": sim.read_fixture(FIXTURE_DIR / "merged_ok.json"),
    }


def test_build_snapshot_happy_path() -> None:
    snap = sim.build_simulate_snapshot(**_good_snapshot_kwargs())
    assert set(snap.keys()) == set(sim.SIMULATE_SNAPSHOT_KEYS)
    assert snap["report_kind"] == "n5b_phase3_simulation"
    assert snap["target_classification"] == "recorded_fixture_simulator"
    assert snap["mode"] == "simulate_only"
    assert snap["fixture_kind"] == "n5b_phase3_recorded_merge_simulation"
    assert snap["merge_response_classification"] == "merged_ok"
    assert snap["merge_response_merge_method"] == "squash"
    assert snap["would_proceed"] is True
    # Discipline invariants nailed.
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    # Safety invariants — every key True.
    si = snap["simulator_safety_invariants"]
    for key in (
        "no_real_github_merge",
        "no_production_merge",
        "no_network",
        "no_git_or_gh_or_subprocess",
        "no_step5_runtime",
        "no_level6",
        "no_live_trading",
        "no_paper_shadow_runtime",
    ):
        assert si[key] is True


def test_build_snapshot_discipline_invariants_dict_present() -> None:
    snap = sim.build_simulate_snapshot(**_good_snapshot_kwargs())
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


def test_build_snapshot_rejects_wrong_operator_confirmation_marker() -> None:
    kwargs = _good_snapshot_kwargs()
    kwargs["operator_confirmation_marker"] = "i_authorise_production_merge"
    with pytest.raises(ValueError):
        sim.build_simulate_snapshot(**kwargs)


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
        ("nonce_hash", "ab" * 31, ValueError),
        ("nonce_hash", "G" * 64, ValueError),
        ("operator_actor", "bogus_actor", ValueError),
        ("generated_at_utc", "", ValueError),
    ],
)
def test_build_snapshot_rejects_bad_inputs(
    field: str, bad_value: Any, exc: type[BaseException]
) -> None:
    kwargs = _good_snapshot_kwargs()
    kwargs[field] = bad_value
    with pytest.raises(exc):
        sim.build_simulate_snapshot(**kwargs)


def test_build_snapshot_deterministic_replay() -> None:
    """Given the same inputs (incl. timestamp), the snapshot must
    be byte-stable. This is the deterministic-fixture-replay pin."""
    snap1 = sim.build_simulate_snapshot(**_good_snapshot_kwargs())
    snap2 = sim.build_simulate_snapshot(**_good_snapshot_kwargs())
    assert json.dumps(snap1, sort_keys=True) == json.dumps(snap2, sort_keys=True)


# ---------------------------------------------------------------------------
# Writers — sentinel-restricted, atomic, assert_no_secrets
# ---------------------------------------------------------------------------


def _tmp_sim_paths(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "logs" / "n5b_merge_execution" / "phase3_simulation"
    base.mkdir(parents=True, exist_ok=True)
    return base / "latest.json", base / "history.jsonl"


def test_write_simulate_latest_writes_closed_schema(tmp_path: Path) -> None:
    latest, _history = _tmp_sim_paths(tmp_path)
    out = sim.write_simulate_latest(
        target_path=latest, **_good_snapshot_kwargs()
    )
    assert out == latest
    assert latest.is_file()
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert set(payload.keys()) == set(sim.SIMULATE_SNAPSHOT_KEYS)
    assert payload["report_kind"] == "n5b_phase3_simulation"
    assert payload["target_classification"] == "recorded_fixture_simulator"


def test_write_simulate_latest_refuses_non_sentinel_path(tmp_path: Path) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "latest.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        sim.write_simulate_latest(target_path=bogus, **_good_snapshot_kwargs())
    assert not bogus.is_file()


def test_write_simulate_latest_runs_assert_no_secrets_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest, _history = _tmp_sim_paths(tmp_path)

    def _boom(_payload: dict[str, Any]) -> None:
        raise AssertionError("simulated credential leak")

    monkeypatch.setattr(sim, "assert_no_secrets", _boom)
    with pytest.raises(AssertionError):
        sim.write_simulate_latest(target_path=latest, **_good_snapshot_kwargs())
    assert not latest.is_file()


def test_write_simulate_latest_atomic_no_tmp_residue(tmp_path: Path) -> None:
    latest, _history = _tmp_sim_paths(tmp_path)
    sim.write_simulate_latest(target_path=latest, **_good_snapshot_kwargs())
    leftovers = [
        p
        for p in latest.parent.iterdir()
        if p.name.startswith(".n5b_merge_execution_simulate.")
    ]
    assert leftovers == []


def test_append_simulate_history_creates_and_appends(tmp_path: Path) -> None:
    _latest, history = _tmp_sim_paths(tmp_path)
    out = sim.append_simulate_history(
        target_path=history, **_good_snapshot_kwargs()
    )
    assert out == history
    assert history.is_file()
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row.keys()) == set(sim.SIMULATE_SNAPSHOT_KEYS)


def test_append_simulate_history_appends_subsequent(tmp_path: Path) -> None:
    _latest, history = _tmp_sim_paths(tmp_path)
    sim.append_simulate_history(target_path=history, **_good_snapshot_kwargs())
    second = _good_snapshot_kwargs()
    second["generated_at_utc"] = "2026-05-17T10:00:30Z"
    sim.append_simulate_history(target_path=history, **second)
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 2


def test_append_simulate_history_compacts_to_max_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sim, "MAX_HISTORY_ROWS", 5)
    _latest, history = _tmp_sim_paths(tmp_path)
    for i in range(12):
        kwargs = _good_snapshot_kwargs()
        kwargs["generated_at_utc"] = f"2026-05-17T10:00:{i:02d}Z"
        sim.append_simulate_history(target_path=history, **kwargs)
    lines = [
        line for line in history.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 5
    rows = [json.loads(line) for line in lines]
    assert rows[-1]["generated_at_utc"] == "2026-05-17T10:00:11Z"


def test_append_simulate_history_refuses_non_sentinel_path(
    tmp_path: Path,
) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "history.jsonl"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        sim.append_simulate_history(target_path=bogus, **_good_snapshot_kwargs())
    assert not bogus.is_file()


def test_simulator_artefact_carries_no_raw_token_or_nonce(tmp_path: Path) -> None:
    """The closed schema must NOT include ``token`` or raw
    ``nonce`` fields — only ``token_kid`` + sha256 ``nonce_hash``."""
    latest, _history = _tmp_sim_paths(tmp_path)
    sim.write_simulate_latest(target_path=latest, **_good_snapshot_kwargs())
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert "token" not in payload
    assert "nonce" not in payload
    assert "token_kid" in payload
    assert "nonce_hash" in payload
    # Sanity: the literal raw nonce input we used must NOT appear in
    # the persisted artefact.
    assert "synth-nonce" not in latest.read_text(encoding="utf-8")
