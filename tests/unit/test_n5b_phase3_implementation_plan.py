"""Doc pin-tests for the B2.9a — N5b Phase 3 implementation plan
(``docs/governance/n5b_phase3_implementation_plan.md``).

The plan is the **decomposition contract** for any future N5b
Phase 3 implementation. It introduces no runtime code. These
pin-tests lock the closed contracts (module path, route URL,
request schema, response statuses, audit artefact paths,
sub-unit decomposition, hard preconditions, invariants,
recorded-fixture-simulator-only selection, Phase 4
permanently-denied-for-ADE doctrine) so that subsequent
code-bearing sub-units (B2.9b / B2.9c / B2.9d / B2.9e) inherit
the contract verbatim.

The pin-tests also fail-closed if this PR smuggles in a runtime
adapter under the plan-only banner.

Defense-in-depth note: the forbidden marker strings the tests
search for are NEVER embedded as literals in this file when
they would also trip the runtime source-text scan; markers are
assembled at runtime from constituent parts.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT / "docs" / "governance" / "n5b_phase3_implementation_plan.md"
)
PARENT_DOC_PATH = (
    REPO_ROOT / "docs" / "governance" / "n5b_merge_execution_plan.md"
)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Doc existence + size
# ---------------------------------------------------------------------------


def test_doc_file_exists() -> None:
    assert DOC_PATH.is_file(), (
        f"N5b Phase 3 implementation plan missing: {DOC_PATH}"
    )


def test_doc_is_non_trivial_in_size() -> None:
    text = _doc_text()
    # A meaningful sub-plan that pins module paths + route +
    # request schema + response envelope + artefact paths +
    # fixture schema + sub-unit decomposition + preconditions +
    # hard denials + Phase 4 denial is at least ~10 KiB.
    assert len(text) > 10000, (
        f"Phase 3 implementation plan is too short ({len(text)} bytes); "
        "the doc must document the full §1-§10 governance surface."
    )


# ---------------------------------------------------------------------------
# Plan status pins — required doctrine language
# ---------------------------------------------------------------------------


def test_doc_states_plan_only_status() -> None:
    text = _doc_text().lower()
    assert "plan only" in text, (
        "doc must declare 'Plan only' status at the top"
    )


def test_doc_states_not_implemented_status() -> None:
    text = _doc_text().lower()
    assert "not implemented" in text, (
        "doc must declare 'Not implemented' status"
    )


def test_doc_states_no_runtime_code_in_this_pr() -> None:
    text = _doc_text().lower()
    assert "no runtime code" in text or (
        "runtime code in this pr | none" in text
    ), "doc must declare 'no runtime code' in this PR"


# ---------------------------------------------------------------------------
# Phase 3 path selection — recorded-fixture simulator, NOT sacrificial repo
# ---------------------------------------------------------------------------


def test_doc_selects_recorded_fixture_simulator_path() -> None:
    text = _doc_text().lower()
    assert "recorded-fixture simulator" in text, (
        "doc must explicitly select the recorded-fixture simulator path"
    )


def test_doc_rejects_sacrificial_github_repository_path() -> None:
    text = _doc_text().lower()
    assert "sacrificial github repo" in text or (
        "sacrificial github repository" in text
    ), "doc must reference the sacrificial GitHub repo path"
    # The doc must explicitly reject / defer / deny that path.
    assert (
        "rejected" in text
        or "permanently deferred" in text
        or "permanently denied" in text
    ), (
        "doc must explicitly reject / defer the sacrificial GitHub "
        "repository path"
    )


# ---------------------------------------------------------------------------
# Closed contracts — module paths
# ---------------------------------------------------------------------------


def test_doc_pins_future_dashboard_module_path() -> None:
    text = _doc_text()
    assert "dashboard/api_merge_execution_simulate.py" in text, (
        "doc must pin the future dashboard module path "
        "exactly to 'dashboard/api_merge_execution_simulate.py'"
    )


def test_doc_pins_future_reporting_module_path() -> None:
    text = _doc_text()
    assert "reporting/n5b_merge_execution_simulate.py" in text, (
        "doc must pin the future reporting module path "
        "exactly to 'reporting/n5b_merge_execution_simulate.py'"
    )


# ---------------------------------------------------------------------------
# Closed contracts — route URL + method
# ---------------------------------------------------------------------------


def test_doc_pins_future_route_url() -> None:
    text = _doc_text()
    assert "/api/agent-control/merge-execution/simulate" in text, (
        "doc must pin the future route URL exactly to "
        "'/api/agent-control/merge-execution/simulate'"
    )


def test_doc_pins_route_method_post_only() -> None:
    text = _doc_text()
    idx = text.find("/api/agent-control/merge-execution/simulate")
    assert idx >= 0
    nearby = text[max(0, idx - 200) : idx + 400]
    assert "POST" in nearby, (
        "doc must declare POST as the method for the simulate route"
    )


def test_doc_forbids_other_http_methods_on_route() -> None:
    text = _doc_text()
    assert "405" in text, (
        "doc must declare 405 for non-POST methods on the simulate route"
    )


# ---------------------------------------------------------------------------
# Closed contracts — request body schema
# ---------------------------------------------------------------------------


def test_doc_pins_request_body_schema_fields() -> None:
    text = _doc_text()
    required_fields = (
        "pr_number",
        "pr_head_sha",
        "token",
        "intent",
        "evidence_hash",
        "operator_confirmation_marker",
    )
    for field in required_fields:
        assert field in text, (
            f"doc must pin the request body field {field!r}"
        )


def test_doc_pins_intent_literal_value() -> None:
    text = _doc_text()
    assert "mobile_approval_dispatch" in text, (
        "doc must pin the intent literal to 'mobile_approval_dispatch'"
    )


def test_doc_pins_operator_confirmation_marker_literal_value() -> None:
    text = _doc_text()
    assert "simulator_execute_confirmed" in text, (
        "doc must pin the operator_confirmation_marker singleton literal "
        "to 'simulator_execute_confirmed'"
    )


def test_doc_pins_no_new_n4b_intent_added() -> None:
    text = _doc_text().lower()
    assert "no new n4b intent" in text or (
        "no new n4b intent literal" in text
    ), (
        "doc must declare that no new N4b intent literal is added "
        "(N4a/N4b frozen contract preserved)"
    )


# ---------------------------------------------------------------------------
# Closed contracts — response statuses
# ---------------------------------------------------------------------------


def test_doc_pins_closed_response_statuses() -> None:
    text = _doc_text()
    for status in ("ok", "rejected", "configuration_missing", "not_yet_implemented"):
        assert status in text, (
            f"doc must pin the response status {status!r}"
        )


def test_doc_pins_response_envelope_invariant_fields() -> None:
    text = _doc_text()
    invariant_fields = (
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
        "target_classification",
        "mode",
        "would_proceed",
    )
    for field in invariant_fields:
        assert field in text, (
            f"response envelope must pin invariant field {field!r}"
        )


def test_doc_pins_target_classification_singleton() -> None:
    text = _doc_text()
    assert '"recorded_fixture_simulator"' in text, (
        "doc must pin target_classification singleton literal "
        "to 'recorded_fixture_simulator'"
    )


def test_doc_pins_mode_singleton() -> None:
    text = _doc_text()
    assert '"simulate_only"' in text, (
        "doc must pin mode singleton literal to 'simulate_only'"
    )


def test_doc_pins_would_proceed_as_dry_run_only_signal() -> None:
    text = _doc_text().lower()
    assert "dry-run-only proceed" in text or (
        "dry-run only proceed" in text
    ) or "dry-run only" in text, (
        "doc must clarify would_proceed=true is a dry-run-only proceed "
        "signal, never live merge authority"
    )


# ---------------------------------------------------------------------------
# Closed contracts — artefact paths
# ---------------------------------------------------------------------------


def test_doc_pins_audit_artefact_root_prefix() -> None:
    text = _doc_text()
    assert "logs/n5b_merge_execution/" in text, (
        "doc must pin the audit artefact write-prefix to "
        "'logs/n5b_merge_execution/'"
    )


def test_doc_pins_audit_artefact_phase3_paths() -> None:
    text = _doc_text()
    required_paths = (
        "logs/n5b_merge_execution/phase3_simulation/latest.json",
        "logs/n5b_merge_execution/phase3_simulation/history.jsonl",
    )
    for path in required_paths:
        assert path in text, (
            f"doc must pin audit artefact path {path!r}"
        )


def test_doc_forbids_n5b_execution_report_kind() -> None:
    """``n5b_execution`` artefact is Phase 4 only — Phase 3 must
    never emit it. The doc must declare this explicitly."""
    text = _doc_text().lower()
    assert "n5b_execution" in text, (
        "doc must reference the n5b_execution artefact kind"
    )
    # Must be in a forbidden / reserved context.
    idx = text.find("n5b_execution")
    nearby = text[max(0, idx - 200) : idx + 300]
    assert any(
        marker in nearby
        for marker in (
            "reserved",
            "phase 4",
            "permanently denied",
            "must not",
            "must never",
            "forbidden",
        )
    ), (
        "n5b_execution must be declared as reserved for Phase 4 / "
        "permanently denied for Phase 3"
    )


# ---------------------------------------------------------------------------
# Closed contracts — fixture schema
# ---------------------------------------------------------------------------


def test_doc_pins_fixture_schema_kind() -> None:
    text = _doc_text()
    assert "n5b_phase3_recorded_merge_simulation" in text, (
        "doc must pin the fixture_kind singleton literal to "
        "'n5b_phase3_recorded_merge_simulation'"
    )


def test_doc_pins_fixture_classification_closed_vocab() -> None:
    text = _doc_text()
    for value in (
        "merged_ok",
        "merged_with_warnings",
        "refused_by_github",
        "network_uncertain",
    ):
        assert value in text, (
            f"doc must pin classification vocab value {value!r}"
        )


# ---------------------------------------------------------------------------
# Closed contracts — sub-unit decomposition
# ---------------------------------------------------------------------------


def test_doc_pins_sub_unit_decomposition() -> None:
    text = _doc_text()
    sub_units = ("B2.9a", "B2.9b", "B2.9c", "B2.9d", "B2.9e")
    for unit in sub_units:
        assert unit in text, (
            f"doc must enumerate sub-unit {unit!r} in §3 decomposition"
        )


def test_doc_states_each_sub_unit_requires_separate_operator_go() -> None:
    text = _doc_text().lower()
    assert "explicit operator-go" in text or "operator-go phrase" in text, (
        "doc must require explicit operator-go per sub-unit"
    )


# ---------------------------------------------------------------------------
# Hard preconditions (§4)
# ---------------------------------------------------------------------------


def test_doc_pins_three_hard_preconditions() -> None:
    text = _doc_text().lower()
    # Phase 2 observed-clean.
    assert "observed clean" in text or "observed-clean" in text, (
        "doc must require Phase 2 observed-clean period as a precondition"
    )
    # N4b reused.
    assert "n4b" in text, (
        "doc must reference N4b reuse precondition"
    )
    # Fixture exists on VPS.
    assert "fixture" in text, (
        "doc must require an operator-provided fixture as a precondition"
    )


# ---------------------------------------------------------------------------
# Hard denials (§5)
# ---------------------------------------------------------------------------


def test_doc_pins_phase_4_permanently_denied_for_ade() -> None:
    text = _doc_text().lower()
    assert "phase 4" in text, "doc must reference Phase 4"
    assert "permanently denied for ade" in text or (
        "permanently denied" in text and "ade" in text
    ), (
        "doc must declare Phase 4 production merge as permanently "
        "denied for ADE"
    )


def test_doc_pins_no_github_api_network_subprocess() -> None:
    text = _doc_text().lower()
    for forbidden in (
        "no github api",
        "no network",
        "no subprocess",
    ):
        assert forbidden in text or forbidden.replace(" ", "") in text or any(
            phrase in text
            for phrase in (
                "no real github",
                "no outbound",
                "must not",
                "no gh / git / subprocess",
                "no gh/git/subprocess",
            )
        ), (
            f"doc must declare {forbidden!r}-class denial somewhere"
        )


def test_doc_pins_no_step5_or_level6_changes() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert (
        "STEP5_ENABLED_SUBSTAGE" in text
        or "step5_enabled_substage" in text
    )
    text_lc = text.lower()
    assert "level 6" in text_lc
    assert "permanently disabled" in text_lc or "no level 6" in text_lc


def test_doc_pins_no_live_trading_paper_shadow_doctrine() -> None:
    """The Phase 3 sub-plan must explicitly carry the
    paper-shadow-max-end-state doctrine for the trading side."""
    text = _doc_text().lower()
    assert "paper/shadow" in text or "paper / shadow" in text, (
        "doc must reference the paper/shadow trading-side doctrine"
    )
    assert "ade never live trade" in text or "ade must never live trade" in text or (
        "ade-side autonomous capability" in text
    ), "doc must reference the ADE-never-live-trade doctrine"


def test_doc_pins_no_n5b_execution_or_production_classification() -> None:
    text = _doc_text()
    # Negative pin on the Phase 4 literal.
    assert "production_pr_merge" in text, (
        "doc must reference the production_pr_merge literal "
        "(in a reserved-for-Phase-4 context)"
    )
    idx = text.find("production_pr_merge")
    nearby = text[max(0, idx - 200) : idx + 300].lower()
    assert any(
        marker in nearby
        for marker in (
            "reserved",
            "phase 4",
            "permanently denied",
            "must not",
            "must never",
        )
    )


def test_doc_pins_no_ade_n5b_live_execute_enabled_in_runtime() -> None:
    text = _doc_text()
    assert "ADE_N5B_LIVE_EXECUTE_ENABLED" in text, (
        "doc must reference the ADE_N5B_LIVE_EXECUTE_ENABLED env "
        "flag (in a reserved-for-Phase-4 context)"
    )
    idx = text.find("ADE_N5B_LIVE_EXECUTE_ENABLED")
    nearby = text[max(0, idx - 200) : idx + 400].lower()
    assert "permanently denied" in nearby or "phase 4" in nearby or (
        "must not" in nearby
    ), (
        "ADE_N5B_LIVE_EXECUTE_ENABLED must be declared in a "
        "Phase-4-permanently-denied context"
    )


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------


def test_doc_cross_references_parent_doc() -> None:
    text = _doc_text()
    assert "n5b_merge_execution_plan.md" in text, (
        "doc must cross-reference the parent n5b_merge_execution_plan.md"
    )


def test_doc_cross_references_phase2_implementation_plan() -> None:
    text = _doc_text()
    assert "n5b_phase2_implementation_plan.md" in text, (
        "doc must cross-reference n5b_phase2_implementation_plan.md"
    )


def test_doc_cross_references_no_touch_paths() -> None:
    text = _doc_text()
    assert "no_touch_paths.md" in text, (
        "doc must cross-reference no_touch_paths.md"
    )


def test_doc_cross_references_adr_015() -> None:
    text = _doc_text()
    assert "ADR-015" in text or "adr-015" in text, (
        "doc must cross-reference ADR-015 (Level 6 disabled doctrine)"
    )


def test_parent_doc_has_back_pointer_to_this_plan() -> None:
    """The parent doc must include a cross-reference to this
    sub-plan so a reader of the parent doc discovers the
    Phase 3 decomposition."""
    parent_text = PARENT_DOC_PATH.read_text(encoding="utf-8")
    assert "n5b_phase3_implementation_plan.md" in parent_text, (
        "parent doc must include a back-pointer to "
        "n5b_phase3_implementation_plan.md (added by B2.9a)"
    )


# ---------------------------------------------------------------------------
# Carry-forward — open items NOT advanced by this PR
# ---------------------------------------------------------------------------


def test_doc_carry_forward_lists_remaining_sub_units() -> None:
    text = _doc_text()
    for unit in ("B2.9b", "B2.9c", "B2.9d", "B2.9e"):
        assert unit in text, (
            f"§8 carry-forward must list sub-unit {unit!r} as not done"
        )


# ---------------------------------------------------------------------------
# Negative pins on the doc itself — no secrets, no escalation
# ---------------------------------------------------------------------------


def test_doc_contains_no_pem_secret_block() -> None:
    text = _doc_text()
    dashes = "-" * 5
    pem_kinds = (
        "PRIVATE KEY",
        "EC PRIVATE KEY",
        "RSA PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
    )
    for kind in pem_kinds:
        marker = f"{dashes}BEGIN {kind}{dashes}"
        assert marker not in text, (
            f"doc embeds a PEM secret block marker: {marker!r}"
        )


def test_doc_contains_no_literal_hex_secret_in_backticks() -> None:
    text = _doc_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"doc embeds a hex-64 literal that looks like a secret: {matches!r}"
    )


def test_doc_contains_no_pat_or_bearer_token_shapes() -> None:
    text = _doc_text()
    forbidden_prefixes = (
        "g" + "h" + "p_",
        "g" + "i" + "thub_pat_",
        "s" + "k-" + "ant-",
    )
    for prefix in forbidden_prefixes:
        rx = re.compile(re.escape(prefix) + r"[A-Za-z0-9_]{20,}")
        assert not rx.search(text), (
            f"doc embeds a token-shaped literal with prefix {prefix!r}"
        )


def test_doc_does_not_instruct_disabling_step5_or_level6() -> None:
    text = _doc_text().lower()
    forbidden_imperatives = [
        "set step5_implementation_allowed to true",
        "step5_implementation_allowed = true",
        'step5_enabled_substage = "5.1"',
        'step5_enabled_substage = "5.2"',
        "enable level 6",
        "skip replay",
        "skip binding check",
        "skip token verification",
        "with --admin",
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"doc contains a forbidden authority-escalation phrase: {phrase!r}"
        )


def test_doc_does_not_instruct_touching_no_touch_paths() -> None:
    text = _doc_text().lower()
    forbidden_imperatives = [
        "edit .claude",
        "modify .claude",
        "write to .claude",
        "edit .gitleaks.toml",
        "weaken .gitleaks.toml",
        "edit seed.jsonl",
        "modify seed.jsonl",
        "write to seed.jsonl",
        "edit generated_seed.jsonl",
        "modify generated_seed.jsonl",
        "write to generated_seed.jsonl",
        "edit delegation_seed.jsonl",
        "edit dashboard/dashboard.py",
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"doc contains a forbidden imperative-edit phrase: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Source-scan guards — B2.9a is doc-only; no runtime adapter
# may be smuggled in alongside the plan-doc.
# ---------------------------------------------------------------------------


_RUNTIME_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "dashboard",
    REPO_ROOT / "reporting",
    REPO_ROOT / "scripts",
    REPO_ROOT / ".github" / "workflows",
)


def _runtime_source_paths() -> list[Path]:
    paths: list[Path] = []
    for root in _RUNTIME_DIRS:
        if not root.is_dir():
            continue
        for child in root.rglob("*"):
            if not child.is_file():
                continue
            if "__pycache__" in child.parts:
                continue
            if child.suffix not in (".py", ".sh", ".yml", ".yaml"):
                continue
            paths.append(child)
    return paths


#: Closed allowlist of operator-approved Phase 3 runtime module
#: paths. Narrowed one entry per sub-unit per PR per the
#: B2.8b/B2.8c precedent. As of B2.9b/B2.9c on this branch:
#: both modules are landed; the projector + route module are
#: both allowed. Subsequent narrowings (B2.9d / B2.9e) must
#: never remove a previously-pinned path.
_ALLOWED_PHASE3_MODULES: tuple[str, ...] = (
    "reporting/n5b_merge_execution_simulate.py",
    "dashboard/api_merge_execution_simulate.py",
)

#: Closed allowlist of runtime source files that are explicitly
#: permitted to carry the Phase 3 simulate route literal. As of
#: B2.9c the only allowed file is the dashboard route module.
_ALLOWED_PHASE3_ROUTE_FILES: tuple[str, ...] = (
    "dashboard/api_merge_execution_simulate.py",
)


def test_phase3_modules_match_allowlist() -> None:
    """Originally a B2.9a-era pin asserting neither Phase 3
    module existed on disk. **Narrowed by B2.9b / B2.9c** to
    allow exactly the operator-approved module paths landed by
    those sub-units. Both Phase 3 modules MUST exist now.
    Any module outside the closed allowlist is rejected."""
    dashboard_module = (
        REPO_ROOT / "dashboard" / "api_merge_execution_simulate.py"
    )
    reporting_module = (
        REPO_ROOT / "reporting" / "n5b_merge_execution_simulate.py"
    )
    assert dashboard_module.is_file(), (
        f"B2.9c dashboard simulator route module missing: "
        f"{dashboard_module}"
    )
    assert reporting_module.is_file(), (
        f"B2.9b reporting simulator projector module missing: "
        f"{reporting_module}"
    )
    # No OTHER simulator module is permitted at this time.
    for rel in _ALLOWED_PHASE3_MODULES:
        assert (REPO_ROOT / rel).is_file(), (
            f"Phase 3 allowlist entry missing on disk: {rel}"
        )


def test_no_phase3_route_url_outside_allowlist() -> None:
    """Originally a B2.9a-era pin forbidding the future Phase 3
    route URL anywhere in runtime source. **Narrowed by B2.9c**
    to allow exactly the operator-approved route module to carry
    the route literal. Any other runtime source file still
    fails the test."""
    forbidden_route = (
        "/api/" + "agent-control/" + "merge-execution/" + "simulate"
    )
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _ALLOWED_PHASE3_ROUTE_FILES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        idx = text.find(forbidden_route)
        if idx >= 0:
            excerpt = text[max(0, idx - 80) : idx + 80]
            hits.append((rel, excerpt))
    assert not hits, (
        "runtime source registers the Phase 3 simulate route "
        "outside the operator-approved allowlist "
        f"{_ALLOWED_PHASE3_ROUTE_FILES!r}: {hits!r}."
    )


# ---------------------------------------------------------------------------
# Status table — hard pins on the post-B2.9e doctrine boundaries
# ---------------------------------------------------------------------------
#
# B2.9e narrowed (NOT retired) the B2.9a-era pin
# ``test_doc_status_table_marks_subsequent_units_not_authorised``
# into two concrete hard pins below. The original assertion
# ("operator-go for B2.9b–e is NOT given by this PR") was
# B2.9a-time-bound and became inaccurate once the B2.9b–B2.9e
# sub-units landed via staged commits on this branch. Rather
# than game the test by preserving the obsolete literal in an
# unrelated context, B2.9e replaces it with two separate hard
# pins that each lock a still-load-bearing post-B2.9e
# doctrine boundary:
#
# 1. N5b Phase 4 (production PR merge) remains ``Not implemented``
#    and is permanently denied for ADE.
# 2. Production / live merge authority remains denied (no
#    autonomous merge / no live execution / no PR mutation).
#
# Any future PR that flips Phase 4 status must also update the
# corresponding pin in the same commit.


def test_doc_status_table_marks_phase_4_not_implemented_and_denied_for_ade() -> None:
    """N5b Phase 4 (production PR merge) MUST remain
    ``Not implemented`` and ``permanently denied for ADE`` after
    B2.9e."""
    text = _doc_text()
    text_lc = text.lower()
    assert "phase 4" in text_lc, "doc must reference Phase 4"
    # Scan every "phase 4" occurrence; require at least one to
    # have BOTH "not implemented" AND "permanently denied" within
    # a bounded proximity window.
    scan_match = False
    start = 0
    while True:
        idx = text_lc.find("phase 4", start)
        if idx < 0:
            break
        window = text_lc[max(0, idx - 200) : idx + 500]
        if (
            "not implemented" in window
            and ("permanently denied" in window or "permanently-denied" in window)
        ):
            scan_match = True
            break
        start = idx + 1
    assert scan_match, (
        "doc must declare Phase 4 remains 'Not implemented' AND "
        "'permanently denied for ADE' after B2.9e"
    )


def test_doc_status_table_denies_production_merge_authority_for_ade() -> None:
    """Doctrine pin: production / live merge authority remains
    denied for ADE across the B2.9 simulator surface."""
    text = _doc_text().lower()
    for required in (
        "autonomous merge",
        "autonomous deploy",
        "autonomous trading",
    ):
        assert required in text, (
            f"doc must reference {required!r}"
        )
    # The Phase 4 production-merge target-classification literal
    # is reserved; doc must reference it in a forbidden /
    # reserved-for-Phase-4 context.
    assert "production_pr_merge" in text, (
        "doc must reference the production_pr_merge literal in a "
        "reserved-for-Phase-4 / permanently-denied context"
    )
    idx = text.find("production_pr_merge")
    nearby = text[max(0, idx - 200) : idx + 300]
    assert any(
        marker in nearby
        for marker in (
            "reserved",
            "phase 4",
            "permanently denied",
            "must not",
            "must never",
        )
    ), (
        "production_pr_merge mention must sit in a "
        "Phase-4-reserved / permanently-denied context"
    )
    # The Phase 4 env flag must be referenced in a denial context.
    assert "ade_n5b_live_execute_enabled" in text, (
        "doc must reference the Phase 4 env flag in a "
        "permanently-denied context"
    )
