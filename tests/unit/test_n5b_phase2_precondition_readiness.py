"""Doc pin-tests for the B2.8c-pre N5b Phase 2 precondition
readiness report
(``docs/governance/n5b_phase2_precondition_readiness.md``).

The report is **governance + machine-checkable evidence only**.
It introduces no runtime code, no env-var read, no VPS
interaction, no token verification, no precondition walker, no
GitHub API call, no audit-artefact write, no `dashboard.py`
wiring change. These pin-tests lock the closed declaration
schema, the machine-confirmed §4.3 evidence, the operator-only
status of §4.1 / §4.2, and the non-goals.

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
    REPO_ROOT
    / "docs"
    / "governance"
    / "n5b_phase2_precondition_readiness.md"
)
PARENT_PLAN_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "n5b_phase2_implementation_plan.md"
)
N4B_RUNBOOK_PATH = (
    REPO_ROOT / "docs" / "governance" / "n4b_runtime_activation.md"
)
B2_8B_SKELETON_PATH = (
    REPO_ROOT / "dashboard" / "api_merge_execution_dry_run.py"
)
APPROVAL_TOKEN_RUNTIME_PATH = (
    REPO_ROOT / "reporting" / "approval_token_runtime.py"
)
N4C_COMPONENT_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "routes"
    / "AgentControl"
    / "ApprovalTokenDiagnostics.tsx"
)
APP_TSX_PATH = REPO_ROOT / "frontend" / "src" / "App.tsx"
N4C_ROUTE_LITERAL = "/agent-control/approval-token-diagnostics"


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Doc existence + size
# ---------------------------------------------------------------------------


def test_doc_file_exists() -> None:
    assert DOC_PATH.is_file(), (
        f"N5b Phase 2 precondition readiness report missing: {DOC_PATH}"
    )


def test_doc_is_non_trivial_in_size() -> None:
    text = _doc_text()
    # A meaningful readiness report enumerating §4.1 / §4.2 / §4.3
    # evidence + the closed declaration schema + non-goals is at
    # least ~6 KiB.
    assert len(text) > 6000, (
        f"readiness report too short ({len(text)} bytes); the doc "
        "must document the full §1-§10 governance surface."
    )


# ---------------------------------------------------------------------------
# Required doctrine language
# ---------------------------------------------------------------------------


def test_doc_states_governance_only_status() -> None:
    text = _doc_text().lower()
    assert "governance-only" in text or "governance only" in text, (
        "doc must declare 'Governance-only' status"
    )


def test_doc_states_no_runtime_activation() -> None:
    text = _doc_text().lower()
    assert "no runtime activation" in text, (
        "doc must declare 'No runtime activation' in this PR"
    )


def test_doc_states_no_runtime_authority_granted() -> None:
    text = _doc_text().lower()
    assert "no runtime authority" in text, (
        "doc must declare 'No runtime authority' is granted by this report"
    )


# ---------------------------------------------------------------------------
# Cited merge SHAs and PR numbers
# ---------------------------------------------------------------------------


def test_doc_cites_b2_8a_merge_sha() -> None:
    text = _doc_text()
    # B2.8a implementation-plan merge SHA on main.
    assert "8832f57" in text, (
        "doc must cite B2.8a merge SHA 8832f57"
    )


def test_doc_cites_b2_8b_merge_sha() -> None:
    text = _doc_text()
    # B2.8b skeleton-UNWIRED merge SHA on main.
    assert "03e228e" in text, (
        "doc must cite B2.8b merge SHA 03e228e"
    )


def test_doc_cites_n4c_merge_pr() -> None:
    text = _doc_text()
    # N4c approval-token diagnostics PWA surface merged in PR #203.
    assert "PR #203" in text or "pull/203" in text, (
        "doc must cite the N4c merge PR #203"
    )


def test_doc_cites_n5b_phase_1_merge_pr() -> None:
    text = _doc_text()
    # N5b Phase 1 preflight projector merged in PR #204.
    assert "PR #204" in text or "pull/204" in text, (
        "doc must cite the N5b Phase 1 merge PR #204"
    )


# ---------------------------------------------------------------------------
# §4.3 — machine-confirmed satisfaction
# ---------------------------------------------------------------------------


def test_doc_declares_phase_4_3_satisfied() -> None:
    text = _doc_text().lower()
    assert "machine-confirmed satisfied" in text or (
        "machine confirmed satisfied" in text
    ), (
        "doc must declare §4.3 as machine-confirmed satisfied"
    )


def test_doc_names_n4c_component_path() -> None:
    text = _doc_text()
    assert (
        "frontend/src/routes/AgentControl/ApprovalTokenDiagnostics.tsx"
        in text
    ), "doc must cite the exact N4c component path"


def test_doc_names_n4c_route_literal() -> None:
    text = _doc_text()
    assert N4C_ROUTE_LITERAL in text, (
        f"doc must cite the exact N4c route literal {N4C_ROUTE_LITERAL!r}"
    )


def test_n4c_component_file_exists_on_disk() -> None:
    assert N4C_COMPONENT_PATH.is_file(), (
        f"N4c component file missing: {N4C_COMPONENT_PATH}"
    )


def test_n4c_route_literal_appears_in_app_tsx() -> None:
    """The N4c route is registered in `frontend/src/App.tsx`. The
    pin asserts the literal route URL is present so a future PR
    that silently drops the route is caught."""
    assert APP_TSX_PATH.is_file(), (
        f"frontend App.tsx missing: {APP_TSX_PATH}"
    )
    src = APP_TSX_PATH.read_text(encoding="utf-8")
    assert N4C_ROUTE_LITERAL in src, (
        f"N4c route literal {N4C_ROUTE_LITERAL!r} not in App.tsx"
    )


# ---------------------------------------------------------------------------
# §4.1 + §4.2 — operator-only declaration
# ---------------------------------------------------------------------------


def test_doc_declares_phase_4_1_operator_only() -> None:
    text = _doc_text().lower()
    # Phase 1 observed-clean is operator-declarable, default
    # NOT_YET_DECLARED.
    assert "phase_1_observed_clean" in text.lower(), (
        "doc must declare the phase_1_observed_clean field"
    )
    assert "not_yet_declared" in text.lower(), (
        "doc must declare NOT_YET_DECLARED as the §4.1 default"
    )


def test_doc_declares_phase_4_2_operator_only() -> None:
    text = _doc_text()
    # N4b Phase B activation is operator-only, default UNKNOWN.
    assert "n4b_phase_b_activated_on_vps" in text, (
        "doc must declare the n4b_phase_b_activated_on_vps field"
    )
    assert "UNKNOWN" in text, (
        "doc must declare UNKNOWN as the §4.2 default"
    )


def test_doc_states_phase_4_2_not_machine_checkable_from_repo() -> None:
    text = _doc_text().lower()
    assert "not machine-checkable from repo" in text or (
        "not machine-checkable from the repo" in text
    ), "doc must explicitly state §4.2 is not machine-checkable from repo"


def test_doc_states_no_env_read() -> None:
    text = _doc_text().lower()
    assert "does **not** read any environment variable" in text or (
        "does not read any environment variable" in text
    ), "doc must declare it reads no environment variable"


def test_doc_states_no_vps_interaction() -> None:
    text = _doc_text().lower()
    assert "no vps interaction" in text or (
        "does **not** interact with the vps" in text
    ) or "does not interact with the vps" in text, (
        "doc must declare it does not interact with the VPS"
    )


# ---------------------------------------------------------------------------
# Closed declaration schema
# ---------------------------------------------------------------------------


def test_doc_carries_closed_declaration_schema() -> None:
    text = _doc_text()
    # The closed schema block keys must all be present verbatim.
    required_keys = (
        "n5b_phase2_precondition_declaration:",
        "phase_1_observed_clean:",
        "phase_1_observed_clean_comment:",
        "n4b_phase_b_activated_on_vps:",
        "n4b_phase_b_evidence_ref:",
        "n4c_or_equivalent_mint_verify_ui:",
        "n4c_ui_route:",
        "n4c_ui_component:",
    )
    for key in required_keys:
        assert key in text, (
            f"closed declaration schema missing required key: {key!r}"
        )


def test_doc_phase_4_3_field_is_yes_in_schema() -> None:
    """The §4.3 field is the one the schema may pre-fill as YES
    because §4.3 is machine-confirmed. The §4.1 / §4.2 fields
    are operator-only and must NOT be pre-filled as YES anywhere
    in the doc."""
    text = _doc_text()
    # The schema example must show §4.3 as YES.
    assert "n4c_or_equivalent_mint_verify_ui: YES" in text, (
        "schema example must show §4.3 as YES"
    )


def test_doc_does_not_declare_phase_4_1_yes() -> None:
    """The governance doc itself must NOT declare §4.1 as YES.
    The declaration is reserved for the B2.8c PR description.

    We accept a single explanatory occurrence inside the §5
    'what unlocks B2.8c' block (which shows the YES line as a
    target shape, not as a current declaration). The doc must
    not contain phase_1_observed_clean: YES outside that
    explanatory context."""
    text = _doc_text()
    # Count occurrences of "phase_1_observed_clean: YES" in the
    # doc — the §5 'what unlocks' block is allowed to show it as
    # an example. We assert at most ONE such occurrence so a
    # silent flip of the §6 schema default to YES is caught.
    occurrences = text.count("phase_1_observed_clean: YES")
    assert occurrences <= 1, (
        f"phase_1_observed_clean: YES appears {occurrences} times; "
        "the governance doc must not silently flip this declaration "
        "outside the §5 'what unlocks B2.8c' example"
    )


def test_doc_does_not_declare_phase_4_2_yes() -> None:
    """Same constraint as §4.1: at most one explanatory occurrence
    of the YES line is permitted, inside the §5 'what unlocks
    B2.8c' example."""
    text = _doc_text()
    occurrences = text.count("n4b_phase_b_activated_on_vps: YES")
    assert occurrences <= 1, (
        f"n4b_phase_b_activated_on_vps: YES appears {occurrences} times; "
        "the governance doc must not silently flip this declaration "
        "outside the §5 'what unlocks B2.8c' example"
    )


# ---------------------------------------------------------------------------
# What unlocks B2.8c
# ---------------------------------------------------------------------------


def test_doc_states_what_unlocks_b2_8c() -> None:
    text = _doc_text().lower()
    assert "what unlocks b2.8c" in text or (
        "may not start until all three" in text.lower()
    ) or "may **not** start until all three" in text.lower(), (
        "doc must enumerate what unlocks B2.8c"
    )


def test_doc_states_b2_8c_not_authorised_by_this_pr() -> None:
    text = _doc_text()
    assert "NOT given by this PR" in text or (
        "not given by this pr" in text.lower()
    ) or "does not provide an operator-go phrase" in text.lower(), (
        "doc must explicitly say it does not authorise B2.8c"
    )


# ---------------------------------------------------------------------------
# Invariants — Step 5 / Level 6 / etc.
# ---------------------------------------------------------------------------


def test_doc_pins_step5_implementation_allowed_false() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text, (
        "doc must reference step5_implementation_allowed invariant"
    )
    idx = text.find("step5_implementation_allowed")
    nearby = text[idx : idx + 400].lower()
    assert "false" in nearby, (
        "step5_implementation_allowed must be stated as false in the doc"
    )


def test_doc_pins_step5_enabled_substage_none() -> None:
    text = _doc_text()
    assert (
        "STEP5_ENABLED_SUBSTAGE" in text
        or "step5_enabled_substage" in text
    ), "doc must reference STEP5_ENABLED_SUBSTAGE invariant"
    assert '"none"' in text or " none" in text.lower(), (
        "STEP5_ENABLED_SUBSTAGE must be stated as 'none' in the doc"
    )


def test_doc_states_level_6_permanently_disabled() -> None:
    text = _doc_text().lower()
    assert "level 6" in text, "doc must reference Level 6 doctrine"
    assert "permanently disabled" in text or "no level 6" in text, (
        "doc must state Level 6 is permanently disabled / denied"
    )


# ---------------------------------------------------------------------------
# Non-goals — binding negative pins
# ---------------------------------------------------------------------------


def test_doc_states_no_token_verification() -> None:
    text = _doc_text().lower()
    assert "no token verification" in text, (
        "doc must declare it performs no token verification"
    )


def test_doc_states_no_precondition_walker() -> None:
    text = _doc_text().lower()
    assert "no precondition walker" in text, (
        "doc must declare it ships no precondition walker"
    )


def test_doc_states_no_github_api_call() -> None:
    text = _doc_text().lower()
    assert "no github api call" in text, (
        "doc must declare it makes no GitHub API call"
    )


def test_doc_states_no_subprocess() -> None:
    text = _doc_text().lower()
    assert "no subprocess" in text, (
        "doc must declare it spawns no subprocess"
    )


def test_doc_states_no_logs_n5b_merge_execution_write() -> None:
    text = _doc_text()
    # Must declare no writes to logs/n5b_merge_execution/.
    assert "logs/n5b_merge_execution/" in text, (
        "doc must reference the logs/n5b_merge_execution/ write path "
        "(to declare it untouched)"
    )


def test_doc_states_no_dashboard_py_wiring() -> None:
    text = _doc_text().lower()
    assert "does **not** wire" in text or "does not wire" in text, (
        "doc must declare it does not wire dashboard.py"
    )


def test_doc_states_no_b2_8b_skeleton_modification() -> None:
    text = _doc_text()
    assert "api_merge_execution_dry_run.py" in text, (
        "doc must reference the B2.8b skeleton path (to declare it untouched)"
    )


# ---------------------------------------------------------------------------
# Cross-references
# ---------------------------------------------------------------------------


def test_doc_cross_references_b2_8a_plan() -> None:
    text = _doc_text()
    assert "n5b_phase2_implementation_plan.md" in text, (
        "doc must cross-reference the B2.8a implementation plan"
    )


def test_doc_cross_references_parent_n5b_plan() -> None:
    text = _doc_text()
    assert "n5b_merge_execution_plan.md" in text, (
        "doc must cross-reference the canonical N5b parent plan"
    )


def test_doc_cross_references_n4b_runbook() -> None:
    text = _doc_text()
    assert "n4b_runtime_activation.md" in text, (
        "doc must cross-reference the N4b operator runbook"
    )


def test_doc_cross_references_adr_015() -> None:
    text = _doc_text()
    assert "ADR-015" in text or "adr-015" in text, (
        "doc must cross-reference ADR-015 (Level 6 disabled doctrine)"
    )


# ---------------------------------------------------------------------------
# Parent plan-doc back-pointer (§11 cross-reference)
# ---------------------------------------------------------------------------


def test_parent_plan_has_backpointer_to_readiness_report() -> None:
    """The B2.8a plan-doc must include a small §11 back-pointer
    to this readiness report so a reader of the plan discovers
    the readiness ledger without spelunking."""
    parent = PARENT_PLAN_PATH.read_text(encoding="utf-8")
    assert "n5b_phase2_precondition_readiness.md" in parent, (
        "parent plan must include a §11 back-pointer to "
        "n5b_phase2_precondition_readiness.md"
    )


# ---------------------------------------------------------------------------
# Source-level invariants — untouched surfaces
# ---------------------------------------------------------------------------


#: Closed allowlist of ``MODULE_VERSION`` literals the
#: ``dashboard/api_merge_execution_dry_run.py`` module is permitted
#: to carry. Grows one entry per operator-approved sub-unit:
#:
#: * ``v3.15.16.N5b.phase2.skeleton`` — B2.8b (initial UNWIRED skeleton)
#: * ``v3.15.16.N5b.phase2.walker_1_7`` — B2.8c (walker for §3 preconditions 1–7)
#: * ``v3.15.16.N5b.phase2.walker_1_17`` — B2.8d (walker for §3 preconditions 1–17)
#:
#: Subsequent sub-units (B2.8e) may extend this allowlist by
#: appending one further operator-approved literal per PR. They
#: must never remove a previously-pinned literal or widen the
#: per-PR exactly-one-match assertion.
_ALLOWED_SKELETON_MODULE_VERSION_LITERALS: tuple[str, ...] = (
    'MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.skeleton"',
    'MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.walker_1_7"',
    'MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.walker_1_17"',
)


def test_b2_8b_skeleton_module_carries_an_allowlisted_version() -> None:
    """Originally a B2.8c-pre pin asserting the B2.8b skeleton's
    ``MODULE_VERSION`` literal was unchanged. **Narrowed by B2.8c**
    to allow exactly the operator-approved walker version
    introduced by that sub-unit. The narrowing follows the same
    one-version-at-a-time pattern the adapter-module allowlists
    in ``test_n5b_merge_execution_plan.py`` /
    ``test_n5b_phase2_implementation_plan.py`` use. No previously
    pinned literal is removed; the change only permits the
    operator-approved walker version literal in addition."""
    assert B2_8B_SKELETON_PATH.is_file(), (
        f"B2.8b/B2.8c dashboard module missing: {B2_8B_SKELETON_PATH}"
    )
    src = B2_8B_SKELETON_PATH.read_text(encoding="utf-8")
    hits = [
        literal
        for literal in _ALLOWED_SKELETON_MODULE_VERSION_LITERALS
        if literal in src
    ]
    assert len(hits) == 1, (
        "dashboard/api_merge_execution_dry_run.py must carry exactly "
        f"one MODULE_VERSION literal from the closed allowlist "
        f"{_ALLOWED_SKELETON_MODULE_VERSION_LITERALS!r}; found: {hits!r}"
    )


def test_approval_token_runtime_default_is_configured_remains_env_gated() -> None:
    """`is_configured()` must remain a thin wrapper that returns
    True iff `_read_env_secret()` returns non-None. This pin
    catches any silent change that would short-circuit the gate
    (e.g. hard-coding a True return).

    The pin reads the source text of the function rather than
    importing the module — importing is unnecessary for a
    governance-only PR."""
    src = APPROVAL_TOKEN_RUNTIME_PATH.read_text(encoding="utf-8")
    # Find the function body.
    marker = "def is_configured() -> bool:"
    idx = src.find(marker)
    assert idx >= 0, "is_configured() not found in approval_token_runtime.py"
    # Read up to the next top-level def.
    tail = src[idx : idx + 600]
    assert "_read_env_secret() is not None" in tail, (
        "is_configured() body must remain the thin env-gated check; "
        f"current body excerpt: {tail!r}"
    )


def test_n4b_runbook_still_describes_operator_only_vps_step() -> None:
    """The N4b runbook must still describe the operator-only VPS
    activation step. This readiness PR does not change the
    runbook; the pin asserts the runbook remains the canonical
    operator-only path."""
    text = N4B_RUNBOOK_PATH.read_text(encoding="utf-8")
    assert "operator-only VPS step" in text, (
        "N4b runbook must still describe the operator-only VPS step"
    )
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" in text, (
        "N4b runbook must still name the env-secret variable"
    )


def test_existing_b2_8a_pin_test_file_still_exists() -> None:
    """B2.8a's plan-doc pin-test file must still be on disk and
    carry its closed-contract pins so the readiness PR has not
    silently weakened the contract surface."""
    b2_8a_pin_test = (
        REPO_ROOT
        / "tests"
        / "unit"
        / "test_n5b_phase2_implementation_plan.py"
    )
    assert b2_8a_pin_test.is_file(), (
        f"B2.8a pin-test file missing: {b2_8a_pin_test}"
    )
    src = b2_8a_pin_test.read_text(encoding="utf-8")
    # Spot-check two load-bearing literals introduced by B2.8a.
    assert "dashboard/api_merge_execution_dry_run.py" in src, (
        "B2.8a pin-test no longer carries the closed module-path literal"
    )
    assert (
        "/api/" + "agent-control/" + "merge-execution/" + "dry-run"
    ) in src, (
        "B2.8a pin-test no longer carries the closed route-URL literal"
    )


def test_existing_b2_8b_skeleton_test_file_still_exists() -> None:
    """B2.8b skeleton pin-test file must still be on disk and
    carry the UNWIRED-contract pin so this readiness PR has not
    weakened the skeleton's invariants."""
    b2_8b_pin_test = (
        REPO_ROOT
        / "tests"
        / "unit"
        / "test_api_merge_execution_dry_run.py"
    )
    assert b2_8b_pin_test.is_file(), (
        f"B2.8b skeleton pin-test file missing: {b2_8b_pin_test}"
    )
    src = b2_8b_pin_test.read_text(encoding="utf-8")
    assert "test_blueprint_not_registered_in_dashboard_py" in src, (
        "B2.8b skeleton pin-test no longer carries the UNWIRED contract pin"
    )


# ---------------------------------------------------------------------------
# Negative pins on the doc itself — no secrets, no escalation
# ---------------------------------------------------------------------------


def test_doc_contains_no_pem_secret_block() -> None:
    """The doc must not embed a real PEM block. Markers are
    assembled at runtime so this test source is inert to
    gitleaks' private-key rule."""
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
    """A 64-char hex run inside backticks looks like a sample
    HMAC secret. The doc must show how to *think* about the
    secret, not embed one."""
    text = _doc_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"doc embeds a hex-64 literal that looks like a secret: {matches!r}"
    )


def test_doc_contains_no_pat_or_bearer_token_shapes() -> None:
    """The doc must not embed a GitHub PAT prefix, an
    Anthropic-shaped key, or a long-form Bearer header value."""
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
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"doc contains a forbidden imperative-edit phrase: {phrase!r}"
        )
