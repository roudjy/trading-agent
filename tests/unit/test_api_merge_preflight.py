"""Unit tests for N5b Phase 1 — ``dashboard.api_merge_preflight``
(UNWIRED).

Pins:

* exactly two GET routes (list + detail); no other HTTP method
  registered;
* list with missing artifact → ``not_available`` envelope;
* list with valid artifact → bounded rows + counts;
* list with malformed artifact → safe ``not_available`` envelope;
* list filters invalid row shapes (closed-schema key-set
  defense-in-depth);
* detail with missing artifact → 404 ``not_available``;
* detail with valid artifact but unknown id → 404 ``not_found``;
* detail with valid id → 200 with exactly one row;
* detail with empty / too-long / bad-charset id →
  400 ``invalid_preflight_id``;
* every envelope carries the closed Step 5 + Level 6 + dry-run /
  live-merge / deploy-coupled invariants verbatim;
* AST + source-text scans: no subprocess / ``gh`` / ``git`` /
  pywebpush / approval-token / ``approve(`` / ``reject(`` /
  ``merge(`` / ``deploy(`` call patterns / ``seed.jsonl``
  writes / forbidden module imports;
* the blueprint is auth-agnostic; the dashboard.py wiring is
  enforced as a both-or-neither skip-or-enforce pin (the
  operator-applied two-line diff is the live wiring step).
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_merge_preflight as amp
from reporting import development_merge_preflight as dmp


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = (
        tmp_path
        / "logs"
        / "development_merge_preflight"
        / "latest.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dmp, "ARTIFACT_LATEST", target)
    return target


def _make_app() -> Flask:
    app = Flask(__name__)
    amp.register_merge_preflight_routes(app)
    return app


def _valid_row(
    pr_number: int = 42,
    head_sha_prefix: str = "deadbeefdead",
    verdict: str = "would_be_live_candidate_if_authorized",
) -> dict[str, Any]:
    """Build one closed-schema N5b candidate row. Key-set matches
    ``dmp.CANDIDATE_ROW_KEYS`` exactly."""
    preflight_id = f"pf_{pr_number}_{head_sha_prefix[:12]}"
    expected_head_sha = (head_sha_prefix + "0" * 64)[:64]
    return {
        "preflight_id": preflight_id,
        "recommendation_id": f"rec_pr_{pr_number}",
        "pr_number": pr_number,
        "expected_head_sha": expected_head_sha,
        "observed_head_sha": expected_head_sha,
        "base_ref": "main",
        "head_ref": "feature/branch",
        "merge_state": "CLEAN",
        "checks_state": "SUCCESS",
        "recommendation_action": "recommend_human_merge",
        "recommendation_reason": "pr_clean_and_no_blocking_inbox",
        "token_required_for_live": True,
        "dry_run_verdict": verdict,
        "live_merge_implemented": False,
        "stop_conditions": [
            "token_required_for_live",
            "live_merge_not_implemented",
        ],
        "audit_note": "dry-run only",
        "generated_at_utc": "2026-05-13T12:00:00Z",
        "evidence_freshness_seconds": 30,
    }


def _write_artifact(
    artifact_path: Path, candidates: list[dict[str, Any]]
) -> None:
    payload = {
        "schema_version": dmp.SCHEMA_VERSION,
        "module_version": dmp.MODULE_VERSION,
        "report_kind": dmp.REPORT_KIND,
        "generated_at_utc": "2026-05-13T12:00:00Z",
        "step5_implementation_allowed": False,
        "step5_enabled_substage": "none",
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "level6_enabled": False,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "sources_read": {},
        "validation_warnings": [],
        "note": "candidates_present" if candidates else "no_recommendation_rows",
    }
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_routes_registers_only_two_get_routes() -> None:
    app = _make_app()
    rules = sorted(
        (rule.rule, frozenset(rule.methods or set()))
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/agent-control/merge-preflight/")
    )
    assert rules == [
        (
            "/api/agent-control/merge-preflight/detail/<string:preflight_id>",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
        (
            "/api/agent-control/merge-preflight/list",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
    ]


def test_no_mutating_routes_registered() -> None:
    app = _make_app()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/agent-control/merge-preflight/"):
            methods = rule.methods or set()
            assert not (
                methods & {"POST", "PUT", "PATCH", "DELETE"}
            ), (
                f"unexpected mutating method on {rule.rule}: {methods}"
            )


def test_blueprint_not_yet_wired_into_dashboard_dashboard() -> None:
    """Operator step pending: dashboard.py must contain BOTH the
    import and the register call for api_merge_preflight, or
    NEITHER. The two-line wiring diff is operator-applied per the
    no-touch hook on ``dashboard/dashboard.py``."""
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_merge_preflight "
        "import register_merge_preflight_routes"
        in text
    )
    register_present = (
        "register_merge_preflight_routes(app)" in text
    )
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_merge_preflight, or NEITHER."
    )


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_missing_artifact_returns_not_available() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "not_available"
    assert body["counts"]["rows"] == 0
    assert body["rows"] == []
    # by_dry_run_verdict counts dict is present and zeroed across
    # the closed vocabulary.
    bdv = body["counts"]["by_dry_run_verdict"]
    assert set(bdv.keys()) == set(dmp.DRY_RUN_VERDICTS)
    assert all(v == 0 for v in bdv.values())


def test_list_valid_artifact_returns_bounded_rows(
    _isolate_artifact: Path,
) -> None:
    rows = [
        _valid_row(pr_number=i, head_sha_prefix=f"abcd{i:04x}eeee")
        for i in range(3)
    ]
    _write_artifact(_isolate_artifact, rows)
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    )
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["counts"]["rows"] == 3
    assert len(body["rows"]) == 3
    # by_dry_run_verdict counts the closed vocab.
    assert sum(body["counts"]["by_dry_run_verdict"].values()) == 3


def test_list_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


def test_list_envelope_carries_level6_and_dry_run_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["level6_enabled"] is False
    assert body["dry_run_only"] is True
    assert body["live_merge_implemented"] is False
    assert body["deploy_coupled"] is False


def test_list_envelope_when_not_available_still_carries_invariants() -> None:
    """Even on the not_available path the envelope must restate the
    six discipline invariants — consumers must never be able to
    observe an N5b envelope without seeing them."""
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"
    assert body["level6_enabled"] is False
    assert body["dry_run_only"] is True
    assert body["live_merge_implemented"] is False
    assert body["deploy_coupled"] is False


def test_list_malformed_artifact_returns_not_available(
    _isolate_artifact: Path,
) -> None:
    _isolate_artifact.write_text("not json", encoding="utf-8")
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["status"] == "not_available"
    assert "malformed" in body["reason"]


def test_list_non_object_top_level_returns_not_available(
    _isolate_artifact: Path,
) -> None:
    _isolate_artifact.write_text("[1, 2, 3]", encoding="utf-8")
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["status"] == "not_available"
    assert "malformed" in body["reason"]


def test_list_artifact_with_invalid_row_shapes_is_filtered(
    _isolate_artifact: Path,
) -> None:
    rows: list[dict[str, Any]] = [
        _valid_row(pr_number=1, head_sha_prefix="aaaaaaaaaaaa"),
        # missing required keys — closed key-set check filters it out
        {"preflight_id": "pf_2_bbbb"},
    ]
    _write_artifact(_isolate_artifact, rows)
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert [r["pr_number"] for r in body["rows"]] == [1]


def test_list_carries_artifact_path_constant(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    ).get_json()
    assert body["artifact_path"] == dmp.ARTIFACT_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_detail_missing_artifact_returns_404_not_available() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/detail/pf_42_deadbeefdead"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_available"


def test_detail_unknown_id_returns_404_not_found(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row(pr_number=7)])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/detail/pf_99_ffffffffffff"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_found"
    assert body["reason"] == "no_matching_preflight_id"


def test_detail_valid_id_returns_exact_row(
    _isolate_artifact: Path,
) -> None:
    rows = [
        _valid_row(pr_number=1, head_sha_prefix="111122223333"),
        _valid_row(pr_number=2, head_sha_prefix="444455556666"),
        _valid_row(pr_number=3, head_sha_prefix="777788889999"),
    ]
    _write_artifact(_isolate_artifact, rows)
    target = rows[1]["preflight_id"]
    res = _make_app().test_client().get(
        f"/api/agent-control/merge-preflight/detail/{target}"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["row"]["preflight_id"] == target
    assert body["row"]["pr_number"] == 2
    # Closed-schema row → no decision-verb literal in any scalar
    # value (the projector's CANDIDATE_ROW_KEYS schema excludes
    # such fields by construction, but defense-in-depth here).
    for v in body["row"].values():
        if isinstance(v, str):
            lv = v.lower()
            # Closed N5a recommendation_action uses recommend_human_*.
            assert "approve_" not in lv or "recommend" in lv
            assert "deploy" not in lv
            assert "reject" not in lv


def test_detail_empty_id_returns_400_invalid() -> None:
    # Flask's routing rejects empty path segments at the URL-map
    # level (it would be a 404 from werkzeug), so we exercise the
    # underlying view function directly to pin the empty-id branch.
    envelope, code = amp._detail_envelope("")
    assert code == 400
    assert envelope["status"] == "invalid_preflight_id"
    assert envelope["reason"] == "empty"


def test_detail_too_long_id_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    big = "x" * 200
    res = _make_app().test_client().get(
        f"/api/agent-control/merge-preflight/detail/{big}"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_preflight_id"
    assert body["reason"] == "too_long"


def test_detail_bad_charset_id_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/detail/bad%20id"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_preflight_id"
    assert body["reason"] == "bad_charset"


def test_detail_id_with_dot_returns_400(
    _isolate_artifact: Path,
) -> None:
    """A ``.`` in the path segment is the canonical shape of a token
    (``header.payload.signature``). The pattern must refuse it."""
    _write_artifact(_isolate_artifact, [_valid_row()])
    # Use bytes/url-encoded form so Flask doesn't normalise the dot.
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/detail/has%2Edots"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_preflight_id"


def test_detail_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    row = _valid_row()
    _write_artifact(_isolate_artifact, [row])
    body = _make_app().test_client().get(
        f"/api/agent-control/merge-preflight/detail/{row['preflight_id']}"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


def test_detail_envelope_carries_level6_and_dry_run_invariants(
    _isolate_artifact: Path,
) -> None:
    row = _valid_row()
    _write_artifact(_isolate_artifact, [row])
    body = _make_app().test_client().get(
        f"/api/agent-control/merge-preflight/detail/{row['preflight_id']}"
    ).get_json()
    assert body["level6_enabled"] is False
    assert body["dry_run_only"] is True
    assert body["live_merge_implemented"] is False
    assert body["deploy_coupled"] is False


def test_detail_not_found_envelope_still_carries_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/detail/pf_99_zzzzzzzzzzzz"
    ).get_json()
    assert body["status"] == "invalid_preflight_id" or body["status"] == "not_found"
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"
    assert body["level6_enabled"] is False
    assert body["dry_run_only"] is True
    assert body["live_merge_implemented"] is False
    assert body["deploy_coupled"] is False


# ---------------------------------------------------------------------------
# Response payload safety
# ---------------------------------------------------------------------------


def test_response_payload_has_no_unexpected_secret_markers(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-preflight/list"
    )
    raw = res.data.decode("utf-8")
    # No VAPID / push / token-secret material should ever land here.
    assert "BEGIN PRIVATE KEY" not in raw
    assert "p256dh" not in raw
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in raw
    assert "ADE_GENERATED_LANE_WRITER_ENABLED" not in raw
    assert "ADE_N5B_LIVE_EXECUTE_ENABLED" not in raw


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(amp.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_in_module() -> None:
    src = _module_source()
    for needle in ("subprocess.run", " gh ", " git "):
        assert needle not in src, needle


def test_no_network_library_import_in_module() -> None:
    names = _imported_module_names()
    forbidden = {
        "socket",
        "urllib",
        "urllib.request",
        "urllib.parse",
        "requests",
        "httpx",
        "aiohttp",
        "http.client",
    }
    for n in names:
        top = n.split(".", 1)[0]
        assert top not in {
            "socket",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
        }, f"forbidden network import: {n}"
        assert n not in forbidden, f"forbidden network import: {n}"


def test_no_web_push_library_import_in_module() -> None:
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n


def test_no_vapid_private_key_literal_in_module() -> None:
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_approval_token_secret_literal_in_module() -> None:
    """N5b Phase 1 is a read-only inspector — it must not reference
    the approval-token env secret. Token issuance/verification is
    N4b territory."""
    src = _module_source()
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in src


def test_no_token_mint_helpers_imported() -> None:
    """N5b Phase 1 must not import the approval-token mint/verify
    helpers. Acting on a preflight verdict is N5b Phase 2+
    territory and requires explicit operator authorisation."""
    names = _imported_module_names()
    for forbidden in (
        "reporting.approval_token_gate",
        "reporting.approval_token_runtime",
    ):
        assert forbidden not in names, forbidden


def test_no_decision_verb_call_in_module() -> None:
    src = _module_source().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in src, verb


def test_no_seed_jsonl_writes_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_module_imports() -> None:
    forbidden_prefixes = (
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
            assert module != prefix, module
            assert not module.startswith(prefix + "."), module


def test_imports_only_dmp_aas_flask_and_stdlib() -> None:
    """The blueprint must import only the N5b Phase 1 projector
    module, the secret-redactor guard, and Flask."""
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.development_merge_preflight",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


def test_no_a18b_or_n5b_live_execute_env_flag_in_module() -> None:
    """The blueprint must not reference the A18b runtime writer
    enable flag or the N5b Phase 4 live-execute enable flag."""
    src = _module_source()
    for forbidden in (
        "ADE_GENERATED_LANE_WRITER_ENABLED",
        "ADE_N5B_LIVE_EXECUTE_ENABLED",
    ):
        assert forbidden not in src, forbidden


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(amp)
    assert amp.step5_implementation_allowed is False
    assert amp.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src


def test_module_source_pins_level6_disabled() -> None:
    src = _module_source().lower()
    assert "level6_enabled" in src
    # the literal True is never assigned to level6_enabled in this
    # module — only False (via the _DISCIPLINE_FIELDS dict).
    assert "level6_enabled = true" not in src
    assert "level6_enabled=true" not in src
    assert '"level6_enabled": true' not in src
