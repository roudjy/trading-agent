"""Doc pin-tests for the B2.8a — N5b Phase 2 implementation plan
(``docs/governance/n5b_phase2_implementation_plan.md``).

The plan is the **decomposition contract** for any future N5b
Phase 2 implementation. It introduces no runtime code. These
pin-tests lock the closed contracts (module path, route URL,
request schema, response statuses, audit artefact paths,
sub-unit decomposition, hard preconditions, invariants) so that
subsequent code-bearing sub-units (B2.8b / B2.8c / B2.8d / B2.8e)
inherit the contract verbatim.

The pin-tests also fail-closed if this PR smuggles in a runtime
adapter under the plan-only banner, and assert that the
existing parent-doc pin tests in
``tests/unit/test_n5b_merge_execution_plan.py`` are NOT
weakened by this PR.

Defense-in-depth note: the forbidden marker strings the tests
search for are NEVER embedded as literals in this file (a
literal ``BEGIN PRIVATE KEY`` block in the test source itself
would trip gitleaks' private-key rule). Markers are assembled at
runtime from constituent parts so the test source stays inert
to scanners.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = (
    REPO_ROOT / "docs" / "governance" / "n5b_phase2_implementation_plan.md"
)
PARENT_DOC_PATH = (
    REPO_ROOT / "docs" / "governance" / "n5b_merge_execution_plan.md"
)
PARENT_PIN_TEST_PATH = (
    REPO_ROOT / "tests" / "unit" / "test_n5b_merge_execution_plan.py"
)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Doc existence + size
# ---------------------------------------------------------------------------


def test_doc_file_exists() -> None:
    assert DOC_PATH.is_file(), (
        f"N5b Phase 2 implementation plan missing: {DOC_PATH}"
    )


def test_doc_is_non_trivial_in_size() -> None:
    text = _doc_text()
    # A meaningful sub-plan that pins module path + route +
    # request schema + response envelope + audit paths +
    # sub-unit decomposition + preconditions + hard denials is
    # at least ~8 KiB.
    assert len(text) > 8000, (
        f"Phase 2 implementation plan is too short ({len(text)} bytes); "
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
    assert "no runtime code" in text or "runtime code in this pr | none" in text, (
        "doc must declare 'no runtime code' in this PR"
    )


def test_doc_states_no_runtime_authority_granted() -> None:
    text = _doc_text().lower()
    assert "no runtime authority" in text, (
        "doc must declare 'No runtime authority' is granted by this plan"
    )


# ---------------------------------------------------------------------------
# Closed contracts — module path
# ---------------------------------------------------------------------------


def test_doc_pins_future_dashboard_module_path() -> None:
    text = _doc_text()
    assert "dashboard/api_merge_execution_dry_run.py" in text, (
        "doc must pin the future dashboard module path "
        "exactly to 'dashboard/api_merge_execution_dry_run.py'"
    )


def test_doc_pins_future_reporting_module_path() -> None:
    text = _doc_text()
    assert "reporting/n5b_merge_execution_dry_run.py" in text, (
        "doc must pin the future reporting (audit projector) "
        "module path exactly to "
        "'reporting/n5b_merge_execution_dry_run.py'"
    )


# ---------------------------------------------------------------------------
# Closed contracts — route URL
# ---------------------------------------------------------------------------


def test_doc_pins_future_route_url() -> None:
    text = _doc_text()
    # The plan-doc lives under docs/ which is exempt from the
    # parent test's runtime-source URL-literal scan; the literal
    # is allowed here because it is the contract being pinned.
    assert "/api/agent-control/merge-execution/dry-run" in text, (
        "doc must pin the future route URL exactly to "
        "'/api/agent-control/merge-execution/dry-run'"
    )


def test_doc_pins_route_method_post_only() -> None:
    text = _doc_text()
    # The "POST" verb + the route URL must co-occur in the doc.
    idx = text.find("/api/agent-control/merge-execution/dry-run")
    assert idx >= 0
    # Walk a bounded window before / after the URL for the POST
    # verb declaration.
    nearby = text[max(0, idx - 200) : idx + 400]
    assert "POST" in nearby, (
        "doc must declare POST as the method for the dry-run route"
    )


def test_doc_forbids_other_http_methods_on_route() -> None:
    text = _doc_text()
    # The doc must explicitly state that GET / PUT / PATCH /
    # DELETE on the route return 405 — i.e. the method
    # restriction is documented, not implicit.
    assert "405" in text, (
        "doc must declare 405 for non-POST methods on the dry-run route"
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
    )
    for field in required_fields:
        assert field in text, (
            f"doc must pin the request body field {field!r}"
        )


def test_doc_pins_intent_literal_value() -> None:
    text = _doc_text()
    # The 'intent' field's literal value is the closed string
    # 'mobile_approval_dispatch'.
    assert "mobile_approval_dispatch" in text, (
        "doc must pin the intent literal to 'mobile_approval_dispatch'"
    )


# ---------------------------------------------------------------------------
# Closed contracts — response statuses
# ---------------------------------------------------------------------------


def test_doc_pins_closed_response_statuses() -> None:
    text = _doc_text()
    # The four closed status values must appear in the doc.
    for status in ("ok", "rejected", "configuration_missing", "not_yet_implemented"):
        assert status in text, (
            f"doc must pin the response status {status!r}"
        )


def test_doc_pins_response_envelope_invariant_fields() -> None:
    text = _doc_text()
    # The six invariant fields that mirror the api_merge_preflight
    # envelope contract must appear in the response envelope.
    invariant_fields = (
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
    )
    for field in invariant_fields:
        assert field in text, (
            f"response envelope must pin invariant field {field!r}"
        )


# ---------------------------------------------------------------------------
# Closed contracts — audit artefact paths
# ---------------------------------------------------------------------------


def test_doc_pins_audit_artefact_root_prefix() -> None:
    text = _doc_text()
    assert "logs/n5b_merge_execution/" in text, (
        "doc must pin the audit artefact write-prefix to "
        "'logs/n5b_merge_execution/'"
    )


def test_doc_pins_audit_artefact_kinds() -> None:
    text = _doc_text()
    # The four artefact kinds from §6 of the parent doc must
    # appear in this sub-plan, with the closed path suffixes.
    required_paths = (
        "logs/n5b_merge_execution/preflight/latest.json",
        "logs/n5b_merge_execution/dry_run/latest.json",
        "logs/n5b_merge_execution/dry_run/history.jsonl",
        "logs/n5b_merge_execution/failure/",
    )
    for path in required_paths:
        assert path in text, (
            f"doc must pin audit artefact path {path!r}"
        )


# ---------------------------------------------------------------------------
# Closed contracts — sub-unit decomposition
# ---------------------------------------------------------------------------


def test_doc_pins_sub_unit_decomposition() -> None:
    text = _doc_text()
    # The exact sub-unit labels enumerated by the operator-go
    # for B2.8a. The doc must enumerate them in §3 so that any
    # future PR that tries to land a different sub-unit naming
    # fails the contract.
    sub_units = ("B2.8a", "B2.8b", "B2.8c", "B2.8d", "B2.8e")
    for unit in sub_units:
        assert unit in text, (
            f"doc must enumerate sub-unit {unit!r} in §3 decomposition"
        )


def test_doc_states_each_sub_unit_requires_separate_operator_go() -> None:
    text = _doc_text().lower()
    # The doc must state that each sub-unit requires its own
    # explicit operator-go phrase.
    assert "explicit operator-go" in text or "operator-go phrase" in text, (
        "doc must require explicit operator-go per sub-unit"
    )


def test_doc_pins_unwired_skeleton_for_b2_8b() -> None:
    text = _doc_text().lower()
    # B2.8b must be documented as UNWIRED — the module exists
    # but the blueprint is not yet registered in dashboard.py.
    assert "unwired" in text, (
        "doc must state B2.8b ships the skeleton UNWIRED"
    )


def test_doc_pins_mocked_only_github_for_b2_8d() -> None:
    text = _doc_text().lower()
    # B2.8d must use mocked GitHub only, no live GitHub call.
    assert "mocked github" in text or "mocked-only" in text or (
        "mocked only" in text
    ), "doc must require mocked-only GitHub for B2.8d"


# ---------------------------------------------------------------------------
# Hard preconditions (§4)
# ---------------------------------------------------------------------------


def test_doc_pins_three_hard_preconditions() -> None:
    text = _doc_text().lower()
    # Phase 1 observed-clean period.
    assert "observed clean" in text or "observed-clean" in text, (
        "doc must require Phase 1 observed-clean period as a precondition"
    )
    # N4b Phase B activated.
    assert "n4b phase b" in text, (
        "doc must require N4b Phase B activation as a precondition"
    )
    # N4c or equivalent UI.
    assert "n4c" in text, (
        "doc must require N4c (or equivalent mint/verify UI) as a precondition"
    )


def test_doc_states_preconditions_not_advanced_by_this_pr() -> None:
    text = _doc_text().lower()
    # The §4 preconditions must be explicitly declared NOT
    # advanced by this PR.
    assert "not advanced" in text or "not advanced by this pr" in text, (
        "doc must declare the §4 preconditions are not advanced by this PR"
    )


# ---------------------------------------------------------------------------
# Invariants — Step 5, Level 6, deploy, branch protection
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


def test_doc_forbids_autonomous_merge() -> None:
    text = _doc_text().lower()
    assert "no autonomous merge" in text, (
        "doc must declare 'No autonomous merge' as a permanent denial"
    )


def test_doc_forbids_autonomous_deploy() -> None:
    text = _doc_text().lower()
    assert "no autonomous deploy" in text, (
        "doc must declare 'No autonomous deploy' as a permanent denial"
    )


def test_doc_forbids_deploy_coupling() -> None:
    text = _doc_text().lower()
    assert "deploy coupling" in text or "no deploy coupling" in text, (
        "doc must address deploy coupling"
    )
    idx = text.find("deploy coupling")
    if idx < 0:
        idx = text.find("no deploy coupling")
    nearby = text[max(0, idx - 100) : idx + 200]
    assert any(
        marker in nearby
        for marker in ("forbidden", "must not", "no ", "deny")
    ), "doc must state deploy coupling is forbidden, not just mention it"


def test_doc_requires_dry_run_only_semantics() -> None:
    text = _doc_text().lower()
    assert "dry-run" in text or "dry run" in text, (
        "doc must mention dry-run"
    )
    assert "dry_run_only" in text, (
        "doc must reference the dry_run_only invariant in the response envelope"
    )


def test_doc_requires_no_branch_protection_bypass() -> None:
    text = _doc_text().lower()
    assert "branch protection" in text, (
        "doc must reference branch protection"
    )
    qualifiers = (
        "must not be bypassed",
        "no branch protection bypass",
        "without the `--admin`",
        "without the --admin",
        "no admin merge",
        "no admin token",
        "no `--admin`",
        "no --admin",
        "bypass branch protection",
        "branch protection bypass",
    )
    assert any(q in text for q in qualifiers), (
        "doc must forbid bypassing branch protection / admin merge "
        "somewhere in the doc"
    )


def test_doc_states_no_pr_mutation() -> None:
    text = _doc_text().lower()
    # The dry-run endpoint must not mutate any PR.
    assert "mutate any pull request" in text or (
        "no pr is mutated" in text
    ) or "mutate any pr" in text or (
        "must never invoke the deploy workflow" in text
    ), "doc must forbid mutating any PR (this is dry-run only)"


def test_doc_states_no_minted_token_in_dry_run_endpoint() -> None:
    text = _doc_text().lower()
    # The mint flow belongs to N4b / N4c, not to the dry-run
    # endpoint. The doc must state this explicitly.
    assert "mint a token" in text or "mint flow" in text, (
        "doc must state that the dry-run endpoint does not mint tokens"
    )


# ---------------------------------------------------------------------------
# Parent-doc cross-reference
# ---------------------------------------------------------------------------


def test_doc_cross_references_parent_doc() -> None:
    text = _doc_text()
    # The plan must cite the parent doc explicitly.
    assert "n5b_merge_execution_plan.md" in text, (
        "doc must cross-reference the parent n5b_merge_execution_plan.md"
    )


def test_doc_cross_references_n4b_runtime_activation() -> None:
    text = _doc_text()
    assert "n4b_runtime_activation.md" in text, (
        "doc must cross-reference n4b_runtime_activation.md "
        "(operator VPS step required by §4.2)"
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
    """The parent doc must include a small cross-reference
    section pointing to this sub-plan, so a reader of the parent
    doc discovers the Phase 2 decomposition without spelunking."""
    parent_text = PARENT_DOC_PATH.read_text(encoding="utf-8")
    assert "n5b_phase2_implementation_plan.md" in parent_text, (
        "parent doc must include a back-pointer to "
        "n5b_phase2_implementation_plan.md (added by B2.8a)"
    )


# ---------------------------------------------------------------------------
# A18b activation phrase isolation
# ---------------------------------------------------------------------------


def test_doc_handles_a18b_activation_phrase_inertly() -> None:
    """The doc may reference the A18b activation contract but
    must NOT contain the canonical capitalised A18b activation
    phrase as a verbatim instruction. The canonical phrase lives
    in the parent doc; this sub-plan references it indirectly so
    push-body safety / activation-phrase scanners do not trip on
    the sub-plan source.

    We assemble the canonical phrase at runtime from constituent
    parts so this test source itself is inert to scanners.
    """
    text = _doc_text()
    canonical_phrase = "G" + "O " + "A" + "18b " + "generated_seed " + "writer"
    # The canonical capitalised phrase must NOT appear verbatim
    # in the sub-plan — only the lowercased / paraphrased form is
    # permitted (because the canonical phrase is the activation
    # marker, and only the parent doc holds it canonically).
    assert canonical_phrase not in text, (
        "sub-plan must not embed the canonical A18b activation "
        "phrase verbatim; only the parent doc carries it"
    )


# ---------------------------------------------------------------------------
# Carry-forward — open items NOT advanced by this PR
# ---------------------------------------------------------------------------


def test_doc_carry_forward_lists_remaining_sub_units() -> None:
    text = _doc_text()
    # §8 must explicitly enumerate the remaining sub-units
    # B2.8b / B2.8c / B2.8d / B2.8e as open.
    for unit in ("B2.8b", "B2.8c", "B2.8d", "B2.8e"):
        assert unit in text, (
            f"§8 carry-forward must list sub-unit {unit!r} as not done"
        )


def test_doc_carry_forward_lists_n4b_n4c_n5b_phase34() -> None:
    text = _doc_text()
    # §8 must enumerate N4b Phase B, N4c, and the future N5b
    # Phase 3 / Phase 4 as still-open.
    for item in ("N4b Phase B", "N4c", "Phase 3", "Phase 4"):
        assert item in text, (
            f"§8 carry-forward must list {item!r} as still-open / denied"
        )


# ---------------------------------------------------------------------------
# Negative pins on the doc itself — no secrets, no escalation
# ---------------------------------------------------------------------------


def test_doc_contains_no_pem_secret_block() -> None:
    """Defense-in-depth: the doc must not embed a real PEM block.
    The forbidden markers are assembled at runtime so this test
    source is inert to gitleaks' private-key rule."""
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
    ``openssl rand -hex 32`` output. The doc must show how to
    *think* about secrets, not embed one."""
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
    """The doc must not instruct the reader to *edit* no-touch
    governance surfaces. Negative mentions ('must not touch
    .claude') are fine and required; imperative 'edit / modify'
    of those paths is forbidden."""
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


# ---------------------------------------------------------------------------
# Source-scan guards — B2.8a is doc-only; no runtime adapter
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


def test_no_phase2_module_exists_in_runtime_yet() -> None:
    """Originally a B2.8a-era pin asserting neither Phase 2
    module existed on disk. **Narrowed by B2.8b** to allow the
    operator-approved skeleton blueprint
    ``dashboard/api_merge_execution_dry_run.py``. The
    reporting-side audit projector
    ``reporting/n5b_merge_execution_dry_run.py`` remains
    forbidden; it is reserved for B2.8c."""
    dashboard_skeleton = (
        REPO_ROOT / "dashboard" / "api_merge_execution_dry_run.py"
    )
    reporting_projector = (
        REPO_ROOT / "reporting" / "n5b_merge_execution_dry_run.py"
    )
    # The dashboard skeleton MUST exist now (B2.8b landed it).
    assert dashboard_skeleton.is_file(), (
        f"B2.8b skeleton missing on disk: {dashboard_skeleton}"
    )
    # The reporting-side audit projector MUST NOT exist yet
    # (B2.8c will land it).
    assert not reporting_projector.is_file(), (
        f"B2.8b is skeleton-only; reporting projector must not "
        f"exist yet: {reporting_projector}"
    )


#: Allowlist of runtime source files that are explicitly
#: permitted to carry the Phase 2 dry-run route literal. As of
#: B2.8b the only allowed file is the skeleton blueprint.
_ALLOWED_PHASE2_ROUTE_FILES: tuple[str, ...] = (
    "dashboard/api_merge_execution_dry_run.py",
)


def test_no_phase2_route_url_in_runtime_yet() -> None:
    """Originally a B2.8a-era pin forbidding the future Phase 2
    route URL anywhere in runtime source. **Narrowed by B2.8b**
    to allow exactly the operator-approved skeleton blueprint
    to carry the route literal. Any other runtime source file
    that mentions the literal still fails the test."""
    # Assemble the forbidden URL prefix at runtime so this test
    # source remains inert to greppers looking for the literal.
    forbidden_route = (
        "/api/" + "agent-control/" + "merge-execution/" + "dry-run"
    )
    hits: list[tuple[str, str]] = []
    for path in _runtime_source_paths():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in _ALLOWED_PHASE2_ROUTE_FILES:
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
        "runtime source registers the Phase 2 dry-run route outside "
        "the operator-approved allowlist "
        f"{_ALLOWED_PHASE2_ROUTE_FILES!r}: {hits!r}."
    )


# ---------------------------------------------------------------------------
# Cross-doc invariants — existing parent-doc pin-tests still pass
# ---------------------------------------------------------------------------


def test_parent_pin_test_file_still_exists() -> None:
    """Existence pin: the existing parent-doc pin-test file
    must still be present. B2.8a may not delete or rename it.

    Logical strength of the parent pins (i.e. that they still
    fail-closed on a smuggled runtime adapter) is asserted by
    the parent pin-test file itself when pytest runs it in the
    same session — there is no value in a duplicate
    AST-walker here."""
    assert PARENT_PIN_TEST_PATH.is_file(), (
        f"parent N5b plan-only pin-test file missing: "
        f"{PARENT_PIN_TEST_PATH}"
    )


def test_parent_pin_test_file_still_carries_module_glob_pin() -> None:
    """Pin: the parent test file still carries its 'no
    api_*merge_execution*.py module exists' glob. B2.8a must
    not narrow / weaken this pin — the narrowing belongs to
    B2.8b when the skeleton module actually lands."""
    src = PARENT_PIN_TEST_PATH.read_text(encoding="utf-8")
    # The glob string lives inside _forbidden_module_globs.
    assert "*merge_execution*.py" in src, (
        "parent pin-test must still carry the "
        "'*merge_execution*.py' module glob (B2.8a must not "
        "weaken this pin)"
    )


def test_parent_pin_test_file_still_carries_route_url_pin() -> None:
    """Pin: the parent test file still scans for the future
    route URL prefix in runtime source. B2.8a must not weaken
    this pin."""
    src = PARENT_PIN_TEST_PATH.read_text(encoding="utf-8")
    # The literal lives inside forbidden_route_prefix.
    assert "/api/agent-control/merge-execution" in src, (
        "parent pin-test must still carry the "
        "'/api/agent-control/merge-execution' route prefix scan "
        "(B2.8a must not weaken this pin)"
    )


# ---------------------------------------------------------------------------
# Status table — operator-go scope is bounded to B2.8a
# ---------------------------------------------------------------------------


def test_doc_status_table_marks_subsequent_units_not_authorised() -> None:
    text = _doc_text()
    # The status table in §10 must declare that operator-go for
    # B2.8b / B2.8c / B2.8d / B2.8e is NOT given by this PR.
    assert "NOT given by this PR" in text or (
        "not given by this pr" in text.lower()
    ), (
        "§10 status table must declare operator-go for B2.8b–e "
        "is NOT given by this PR"
    )
