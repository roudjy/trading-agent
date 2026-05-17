"""Pin tests for the B2.9c N5b Phase 3 recorded-fixture simulator
endpoint (``dashboard/api_merge_execution_simulate.py``).

The module under test is the POST route that exposes the B2.9b
simulator core. It reuses N4b's ``verify_runtime_for_dry_run``
(no new N4b intent), reads two new Phase 3 env vars
(``ADE_N5B_SIMULATOR_ENABLED`` + ``ADE_N5B_SIMULATOR_FIXTURE_PATH``),
consumes a closed on-disk fixture, and writes the closed
simulation artefacts via the B2.9b projector. It never calls
GitHub, never opens a network socket, never spawns a subprocess.

Defense-in-depth note: forbidden marker strings the tests
search for are NEVER embedded as literals in this file when
they would also trip the runtime source-text scan; markers are
assembled at runtime from constituent parts.
"""

from __future__ import annotations

import ast
import json
import secrets as _secrets
import shutil
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_merge_execution_simulate as mod
from reporting import approval_token_runtime as atr
from reporting import n5b_merge_execution_simulate as projector

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "dashboard" / "api_merge_execution_simulate.py"
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "n5b" / "recorded_merge_simulation"

ROUTE_URL = "/api/agent-control/merge-execution/simulate"


# ---------------------------------------------------------------------------
# Test isolation — env + seen-nonce store + simulator paths
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect the approval-token-runtime seen-nonce store + the
    simulator artefact write paths into ``tmp_path/...``."""
    seen_target = tmp_path / "state" / "approval_token_seen_nonces.jsonl"
    seen_target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(atr, "SEEN_NONCES_PATH", seen_target)

    # Tmp-redirect simulator artefact paths.
    sim_dir = tmp_path / "logs" / "n5b_merge_execution" / "phase3_simulation"
    sim_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        projector, "PHASE3_SIMULATION_LATEST", sim_dir / "latest.json"
    )
    monkeypatch.setattr(
        projector,
        "PHASE3_SIMULATION_HISTORY",
        sim_dir / "history.jsonl",
    )

    # Place a synthetic fixture in tmp_path/state/ and point the
    # env var to it.
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    fixture_target = state_dir / "n5b_simulator_fixture.json"
    shutil.copyfile(FIXTURE_DIR / "merged_ok.json", fixture_target)
    monkeypatch.setenv(mod.ENV_SIMULATOR_FIXTURE_PATH, str(fixture_target))
    monkeypatch.setenv(mod.ENV_SIMULATOR_ENABLED, "true")
    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)
    yield tmp_path


def _mint_simulator_token(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pr_number: int = 123,
    pr_head_sha: str = "abc1234567890def1234567890abcdef12345678",
    evidence_hash: str = "deadbeef" * 8,
    event_id: str = "evt_simulator_test",
    intent: str = "mobile_approval_dispatch",
) -> str:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _secrets.token_hex(32)
    )
    out = atr.mint_runtime(
        intent=intent,
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
    )
    assert out["status"] == "ok", out
    return out["token"]


def _good_body(
    token: str,
    *,
    pr_number: int = 123,
    pr_head_sha: str = "abc1234567890def1234567890abcdef12345678",
    evidence_hash: str = "deadbeef" * 8,
    intent: str = "mobile_approval_dispatch",
    operator_confirmation_marker: str = "simulator_execute_confirmed",
) -> dict[str, Any]:
    return {
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "token": token,
        "intent": intent,
        "evidence_hash": evidence_hash,
        "operator_confirmation_marker": operator_confirmation_marker,
    }


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    mod.register_merge_execution_simulate_routes(app)
    return app


def _post_json(client: Any, body: Any) -> Any:
    if body is None:
        return client.post(ROUTE_URL)
    if isinstance(body, str):
        return client.post(ROUTE_URL, data=body, content_type="application/json")
    return client.post(
        ROUTE_URL,
        data=json.dumps(body),
        content_type="application/json",
    )


def _envelope_after(client: Any, body: Any) -> tuple[int, dict[str, Any]]:
    resp = _post_json(client, body)
    return resp.status_code, resp.get_json()


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert mod is not None


def test_module_version_is_pinned_string() -> None:
    assert mod.MODULE_VERSION == "v3.15.16.N5b.phase3.simulator_route"


def test_schema_version_is_pinned_integer_1() -> None:
    assert mod.SCHEMA_VERSION == 1


def test_step5_enabled_substage_pinned_none() -> None:
    assert mod.STEP5_ENABLED_SUBSTAGE == "none"


def test_step5_implementation_allowed_pinned_false() -> None:
    assert mod.step5_implementation_allowed is False


def test_env_var_names_pinned() -> None:
    assert mod.ENV_SIMULATOR_ENABLED == "ADE_N5B_SIMULATOR_ENABLED"
    assert mod.ENV_SIMULATOR_FIXTURE_PATH == "ADE_N5B_SIMULATOR_FIXTURE_PATH"


def test_all_exports_are_closed() -> None:
    assert set(mod.__all__) == {
        "ENV_SIMULATOR_ENABLED",
        "ENV_SIMULATOR_FIXTURE_PATH",
        "MODULE_VERSION",
        "SCHEMA_VERSION",
        "STEP5_ENABLED_SUBSTAGE",
        "register_merge_execution_simulate_routes",
        "step5_implementation_allowed",
    }


# ---------------------------------------------------------------------------
# AST + source-text guards
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_TOPS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "asyncio",
    "github",
    "ghapi",
    "PyGithub",
    "reporting.github_pr_lifecycle",
)

_REQUIRED_IMPORTS = (
    "reporting.approval_token_runtime",
    "reporting.n5b_merge_execution_simulate",
)


def _module_imports() -> list[str]:
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
            for alias in node.names:
                names.append(f"{node.module}.{alias.name}")
    return names


def test_module_has_no_forbidden_top_level_imports() -> None:
    imported = _module_imports()
    offending: list[str] = []
    for name in imported:
        for forbidden in _FORBIDDEN_IMPORT_TOPS:
            if name == forbidden or name.startswith(forbidden + "."):
                offending.append(name)
    assert offending == [], (
        f"simulator route imports forbidden modules: {offending!r}"
    )


def test_module_imports_token_runtime_and_simulator_projector() -> None:
    imported = set(_module_imports())
    for required in _REQUIRED_IMPORTS:
        assert required in imported, (
            f"simulator route must import {required!r}"
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
        f"simulator route source contains shell-spawning attribute: {hits!r}"
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
        f"simulator route source contains forbidden literal: {hits!r}"
    )


def test_module_source_never_mentions_production_pr_merge_literal() -> None:
    """The Phase 4 production-merge literal must never appear in
    the simulator route source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "production_pr_merge" not in src


def test_module_source_never_mentions_live_execute_env_flag() -> None:
    """The Phase 4 env flag must never appear in the simulator
    route source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "ADE_N5B_LIVE_EXECUTE_ENABLED" not in src


def test_module_source_never_mentions_n5b_execution_report_kind() -> None:
    """The Phase 4 execution-artefact report_kind literal must
    never appear in the simulator route source."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert '"n5b_execution"' not in src


def test_module_source_pins_step5_invariants() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


def test_module_does_not_add_new_n4b_intent_literal() -> None:
    """The simulator route MUST reuse the existing
    ``mobile_approval_dispatch`` intent. No new N4b intent
    literal is added (N4a/N4b frozen contract preserved)."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # The only intent literal that may appear quoted is the
    # existing closed N4a one.
    assert '"mobile_approval_dispatch"' in src
    # The other existing N4a literal may NOT appear (this route
    # is not for review dispatch).
    assert '"mobile_review_dispatch"' not in src
    # No made-up intent.
    assert '"simulate_intent"' not in src
    assert '"mobile_execute_confirm"' not in src
    assert '"mobile_simulate_dispatch"' not in src


# ---------------------------------------------------------------------------
# Route surface — exactly one POST route
# ---------------------------------------------------------------------------


def test_route_table_has_exactly_one_route() -> None:
    assert len(mod._MERGE_EXECUTION_SIMULATE_ROUTES) == 1


def test_route_url_pinned() -> None:
    (path, method, _handler, _endpoint) = mod._MERGE_EXECUTION_SIMULATE_ROUTES[0]
    assert path == ROUTE_URL
    assert method == "POST"


def test_route_registers_post_only() -> None:
    app = _build_app()
    matches = [r for r in app.url_map.iter_rules() if r.rule == ROUTE_URL]
    assert len(matches) == 1
    methods = matches[0].methods or set()
    assert "POST" in methods
    assert methods.isdisjoint({"GET", "PUT", "PATCH", "DELETE"})


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_non_post_methods_return_405(method: str) -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = client.open(ROUTE_URL, method=method)
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------


_REQUIRED_ENVELOPE_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "module_version",
        "status",
        "stop_condition",
        "would_proceed",
        "pr_number",
        "pr_head_sha",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "target_classification",
        "mode",
    }
)


def test_envelope_contains_all_closed_fields() -> None:
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    missing = _REQUIRED_ENVELOPE_FIELDS - set(payload.keys())
    assert not missing, f"envelope missing required fields: {missing!r}"


def test_envelope_pins_six_discipline_invariants_plus_simulator_invariants() -> None:
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    # Six discipline invariants.
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
    assert payload["level6_enabled"] is False
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False
    # Two simulator-specific invariants.
    assert payload["target_classification"] == "recorded_fixture_simulator"
    assert payload["mode"] == "simulate_only"


# ---------------------------------------------------------------------------
# Body validation failures
# ---------------------------------------------------------------------------


def test_missing_body_returns_400_rejected() -> None:
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, None)
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["reason"] == "body_missing"


def test_missing_operator_confirmation_marker_rejected() -> None:
    app = _build_app()
    body = {
        "pr_number": 1,
        "pr_head_sha": "x" * 40,
        "token": "t",
        "intent": "mobile_approval_dispatch",
        "evidence_hash": "e",
    }
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["reason"] == "field_missing:operator_confirmation_marker"


def test_wrong_operator_confirmation_marker_rejected() -> None:
    app = _build_app()
    body = {
        "pr_number": 1,
        "pr_head_sha": "x" * 40,
        "token": "t",
        "intent": "mobile_approval_dispatch",
        "evidence_hash": "e",
        "operator_confirmation_marker": "i_authorise_production_merge",
    }
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert (
        payload["reason"] == "field_value:operator_confirmation_marker_not_pinned"
    )


def test_wrong_intent_rejected() -> None:
    app = _build_app()
    body = {
        "pr_number": 1,
        "pr_head_sha": "x" * 40,
        "token": "t",
        "intent": "mobile_review_dispatch",
        "evidence_hash": "e",
        "operator_confirmation_marker": "simulator_execute_confirmed",
    }
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["reason"] == "field_value:intent_not_pinned"


# ---------------------------------------------------------------------------
# Env-flag enforcement
# ---------------------------------------------------------------------------


def test_simulator_disabled_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(mod.ENV_SIMULATOR_ENABLED, raising=False)
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "configuration_missing"
    assert payload["reason"] == "simulator_disabled"


def test_simulator_disabled_when_env_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(mod.ENV_SIMULATOR_ENABLED, "false")
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert payload["status"] == "configuration_missing"
    assert payload["reason"] == "simulator_disabled"


# ---------------------------------------------------------------------------
# Fixture-file presence
# ---------------------------------------------------------------------------


def test_fixture_missing_returns_configuration_missing(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        mod.ENV_SIMULATOR_FIXTURE_PATH,
        str(_isolate_state / "state" / "nonexistent.json"),
    )
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert payload["status"] == "configuration_missing"
    assert payload["reason"] == "fixture_file_missing"


def test_fixture_invalid_returns_configuration_missing(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = _isolate_state / "state" / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    monkeypatch.setenv(mod.ENV_SIMULATOR_FIXTURE_PATH, str(bad))
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert payload["status"] == "configuration_missing"
    assert payload["reason"] == "fixture_invalid"


# ---------------------------------------------------------------------------
# Token-verification failures
# ---------------------------------------------------------------------------


def test_invalid_token_emits_token_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _secrets.token_hex(32)
    )
    body = _good_body(token="not.a.real.token")
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "token_invalid"


def test_pr_number_mismatch_emits_pr_number_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch, pr_number=999)
    body = _good_body(token, pr_number=123)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "pr_number_mismatch"


def test_head_sha_mismatch_emits_binding_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch, pr_head_sha="cafebabe" * 5)
    body = _good_body(token, pr_head_sha="deadbeef" * 5)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "binding_mismatch"


def test_replay_detected_on_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code1, payload1 = _envelope_after(client, body)
    assert payload1["status"] == "ok"
    with app.test_client() as client:
        code2, payload2 = _envelope_after(client, body)
    assert payload2["status"] == "rejected"
    assert payload2["stop_condition"] == "replay_detected"


# ---------------------------------------------------------------------------
# Happy path — status=ok + artefacts written
# ---------------------------------------------------------------------------


def test_happy_simulator_emits_ok_with_artefacts(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["stop_condition"] is None
    assert payload["would_proceed"] is True
    assert payload["target_classification"] == "recorded_fixture_simulator"
    assert payload["mode"] == "simulate_only"
    # Discipline invariants nailed.
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False
    # Both artefacts on disk.
    latest = projector.PHASE3_SIMULATION_LATEST
    history = projector.PHASE3_SIMULATION_HISTORY
    assert latest.is_file()
    assert history.is_file()
    snap = json.loads(latest.read_text(encoding="utf-8"))
    assert snap["report_kind"] == "n5b_phase3_simulation"
    assert snap["target_classification"] == "recorded_fixture_simulator"
    assert snap["mode"] == "simulate_only"
    assert snap["merge_response_classification"] == "merged_ok"
    # No raw token / nonce in the artefact.
    blob = json.dumps(snap, default=str)
    assert token not in blob


def test_happy_simulator_carries_safety_invariants_in_artefact(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        _envelope_after(client, body)
    snap = json.loads(
        projector.PHASE3_SIMULATION_LATEST.read_text(encoding="utf-8")
    )
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


def test_happy_simulator_would_proceed_co_occurs_with_dry_run_invariants(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator-mandated semantic pin: ``would_proceed=true``
    means *"dry-run checks passed and audit artefacts written"* —
    NEVER live merge authority. Both envelope and persisted
    artefact must carry the 6 dry-run invariants when
    would_proceed=True."""
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, body)
    # Envelope side.
    assert payload["would_proceed"] is True
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False
    assert payload["level6_enabled"] is False
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
    # Persisted artefact side.
    snap = json.loads(
        projector.PHASE3_SIMULATION_LATEST.read_text(encoding="utf-8")
    )
    assert snap["would_proceed"] is True
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False
    assert snap["level6_enabled"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


# ---------------------------------------------------------------------------
# Audit-write failure paths
# ---------------------------------------------------------------------------


def test_simulate_latest_write_failure_emits_audit_write_failure(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)

    def _boom(**_kwargs: Any) -> Any:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(projector, "write_simulate_latest", _boom)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "audit_write_failure"


def test_history_append_failure_emits_audit_write_failure(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_simulator_token(monkeypatch)
    body = _good_body(token)
    real = projector.append_simulate_history

    def _boom(**_kwargs: Any) -> Any:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(projector, "append_simulate_history", _boom)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "audit_write_failure"
    monkeypatch.setattr(projector, "append_simulate_history", real)


# ---------------------------------------------------------------------------
# UNWIRED contract — blueprint not registered in dashboard.py YET
#
# B2.9d will land the operator-applied wiring patch as a separate
# commit on this same branch (B2.0c precedent).
# ---------------------------------------------------------------------------


def test_dashboard_py_present() -> None:
    assert DASHBOARD_PY.is_file()


def test_simulator_blueprint_not_yet_registered_in_dashboard_py() -> None:
    """B2.9c keeps the simulator route module UNWIRED. The 2-line
    operator-applied wiring patch is B2.9d (operator manual,
    B2.0c precedent). This pin will be REPLACED by a positive
    ``test_simulator_blueprint_registered_in_dashboard_py`` pin
    in the wiring commit (same B2.0c precedent as the B2.8e
    wiring PR #239)."""
    src = DASHBOARD_PY.read_text(encoding="utf-8")
    forbidden_substrings = (
        "from dashboard.api_merge_execution_simulate",
        "import api_merge_execution_simulate",
        "register_merge_execution_simulate_routes",
    )
    hits = [s for s in forbidden_substrings if s in src]
    assert not hits, (
        "B2.9c simulator route must remain UNWIRED until B2.9d "
        f"operator-applied wiring. dashboard.py contains: {hits!r}"
    )


# ---------------------------------------------------------------------------
# Bounded caps — defense-in-depth
# ---------------------------------------------------------------------------


def test_token_size_cap_pinned() -> None:
    assert mod._MAX_TOKEN_LEN == 4096


def test_pr_head_sha_size_cap_pinned() -> None:
    assert mod._MAX_PR_HEAD_SHA_LEN == 64


def test_intent_size_cap_pinned() -> None:
    assert mod._MAX_INTENT_LEN == 64


def test_evidence_hash_size_cap_pinned() -> None:
    assert mod._MAX_EVIDENCE_HASH_LEN == 256


def test_operator_confirmation_marker_size_cap_pinned() -> None:
    assert mod._MAX_OPERATOR_CONFIRMATION_MARKER_LEN == 64


def test_reason_size_cap_pinned() -> None:
    assert mod._MAX_REASON_LEN == 200


def test_intent_literal_pinned() -> None:
    assert mod._INTENT_LITERAL == "mobile_approval_dispatch"


def test_operator_confirmation_marker_literal_pinned() -> None:
    assert (
        mod._OPERATOR_CONFIRMATION_MARKER_LITERAL == "simulator_execute_confirmed"
    )


def test_required_body_fields_closed_six_set() -> None:
    assert set(mod._REQUIRED_BODY_FIELDS) == {
        "pr_number",
        "pr_head_sha",
        "token",
        "intent",
        "evidence_hash",
        "operator_confirmation_marker",
    }
