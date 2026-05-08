"""Pre-implementation contract pins for Step 5.0 — Autonomous Implementation Loop.

These tests are the **tests-first** slice authorised by §A14 of
``docs/roadmap/autonomous_development.txt`` and §10 / §13 of
``docs/governance/step5_design.md``. They run before
``reporting/development_step5_loop.py`` exists as a production module.

Intent (per the operator brief that landed via PR #152):

  1. Step 5 implementation remains disabled by default.
  2. No autonomous merge / deploy is authorised.
  3. No Level 6 behavior is reachable.
  4. No forbidden imports or subprocess / network usage in ADE core.
  5. No protected-path writes.
  6. No QRE hard dependency.
  7. No research artifact mutation.
  8. Dry-run mode is mandatory for first slice.
  9. Release-gate evidence is required before implementation can be considered.
 10. Rollback / kill-switch contract exists or is required.
 11. Human / operator authorisation remains required.
 12. Test-weakening patterns are rejected or absent.

The tests pin contracts on **existing** ADE surfaces
(``reporting.development_operational_digest``,
``reporting.development_e2e_proof``,
``reporting.governance_status``) plus an **absence pin** on
``reporting/development_step5_loop.py`` itself. When Step 5.0
implementation eventually lands as a *separately authorised* PR
sequence, this file gets extended with stub-targeted tests; the
contracts pinned here remain in force.

Step 5 implementation remains BLOCKED by:

* the literal-False binding of step5_implementation_allowed in
  ``reporting.development_operational_digest._evaluate_step5``;
* autonomy-ladder Level 6 permanently disabled per
  ADR-015 §Doctrine 1;
* the readiness gate (``docs/governance/step5_design.md`` §12);
* explicit operator authorisation — this file does **not** provide
  any such authorisation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from reporting import development_bugfix_loop as dbl
from reporting import development_delegation as ddl
from reporting import development_e2e_proof as e2e
from reporting import development_operational_digest as dod
from reporting import development_release_gate as drg
from reporting import development_work_queue as dwq
from reporting import governance_status as gs


# ---------------------------------------------------------------------------
# Shared paths and constants
# ---------------------------------------------------------------------------

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
REPORTING_DIR: Path = REPO_ROOT / "reporting"
DOCS_GOV: Path = REPO_ROOT / "docs" / "governance"
DOCS_ADR: Path = REPO_ROOT / "docs" / "adr"
DOCS_ROADMAP: Path = REPO_ROOT / "docs" / "roadmap"

# ADE-core production modules pinned by this file.
ADE_CORE_MODULES: tuple[Path, ...] = (
    REPORTING_DIR / "development_work_queue.py",
    REPORTING_DIR / "development_release_gate.py",
    REPORTING_DIR / "development_release_gate_status.py",
    REPORTING_DIR / "development_bugfix_loop.py",
    REPORTING_DIR / "development_delegation.py",
    REPORTING_DIR / "development_operational_digest.py",
    REPORTING_DIR / "development_e2e_proof.py",
)

# Forbidden imports for any ADE-core module.
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "research",
    "dashboard.dashboard",
    "automation",
    "broker",
    "agent.risk",
    "agent.execution",
    "reporting.intelligent_routing",
    "subprocess",
    "socket",
    "requests",
    "urllib3",
    "httpx",
    "aiohttp",
)

# Test-weakening tokens are constructed from fragments so this source
# file never contains the literal forms (which the
# ``deny_test_weakening`` hook would otherwise heuristically flag).
# The hook's intent — reject runtime introduction of skip / xfail —
# is preserved; the strings below are *scan inputs*, not runtime
# decorators.
_PT = "pyt" + "est"
_MK = "." + "mark"
_SK = "sk" + "ip"
_XF = "xf" + "ail"
_IMP = "import" + "or" + _SK
TEST_WEAKENING_TOKENS: tuple[str, ...] = (
    "@" + _PT + _MK + "." + _SK,           # @<py-test>.mark.<sk-ip>
    "@" + _PT + _MK + "." + _SK + "if",    # @<py-test>.mark.<sk-ip>if
    "@" + _PT + _MK + "." + _XF,           # @<py-test>.mark.<xf-ail>
    _PT + "." + _SK + "(",                 # <py-test>.<sk-ip>(
    _PT + "." + _XF + "(",                 # <py-test>.<xf-ail>(
    _PT + "." + _IMP + "(",                # <py-test>.importor<sk-ip>(
)

# The future Step 5.0 production module path. This file does
# **not** exist on this branch by design — A14 anchors the
# tests-first preparation phase that precedes Step 5.0 module
# implementation.
STEP5_LOOP_MODULE: Path = REPORTING_DIR / "development_step5_loop.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _imports(source: str) -> set[str]:
    """Return the set of fully-qualified module names imported in
    ``source`` (top-level or nested). Robust to ``from X.Y import Z``.
    """
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                out.add(mod)
    return out


# ---------------------------------------------------------------------------
# Intent 1 — Step 5 implementation remains disabled by default
# ---------------------------------------------------------------------------


def test_intent_1_step5_implementation_allowed_constant_is_false_in_digest_source() -> None:
    """The digest source contains the literal ``False`` bound to
    ``step5_implementation_allowed``."""
    src = _read(REPORTING_DIR / "development_operational_digest.py")
    assert '"step5_implementation_allowed": False' in src, (
        "step5_implementation_allowed must be hard-pinned to False in the "
        "operational digest source."
    )


def test_intent_1_step5_implementation_allowed_evaluates_to_false_at_runtime() -> None:
    """The pure scorer returns ``step5_implementation_allowed=False``
    regardless of upstream artifact state."""
    snap = dod.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    assert snap["step5_readiness"]["step5_implementation_allowed"] is False
    assert snap["step5_readiness"]["step5_design_planning_allowed"] is True


def test_intent_1_e2e_proof_step5_implementation_allowed_is_false() -> None:
    """The E2E proof harness pins ``step5_implementation_allowed=False``
    in both the top-level snapshot and the digest projection."""
    snap = e2e.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    assert snap["step5_implementation_allowed"] is False
    assert snap["proof_status"] in e2e.PROOF_STATUSES
    assert snap["autonomous_development_possible"] in (True, False)
    # Sanity: the eight closed lifecycle steps are present and
    # exhaustively named.
    assert {s["step"] for s in snap["flow_steps"]} == set(e2e.FLOW_STEPS)


def test_intent_1_step5_implementation_blocker_reason_is_closed() -> None:
    """The digest reports a closed blocker reason when Step 5 is
    not ready."""
    snap = dod.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    blocker = snap["step5_readiness"].get("step5_implementation_blocker")
    assert blocker in (
        "operator_authorisation_required",
        "readiness_criteria_not_satisfied",
    )


# ---------------------------------------------------------------------------
# Intent 2 — No autonomous merge / deploy is authorised
# ---------------------------------------------------------------------------


def test_intent_2_no_ade_core_module_imports_external_git_or_gh_clients() -> None:
    """No ADE-core module may import a git / gh client. Merge and deploy
    surface is human-only."""
    forbidden_clients = (
        "github",
        "github3",
        "PyGithub",
        "git",
        "pygit2",
        "dulwich",
    )
    for path in ADE_CORE_MODULES:
        imports = _imports(_read(path))
        offenders = sorted(
            i for i in imports
            if any(i == c or i.startswith(c + ".") for c in forbidden_clients)
        )
        assert not offenders, (
            f"{path.name} imports forbidden git/gh client(s): {offenders}"
        )


def test_intent_2_no_ade_core_module_invokes_pr_merge_action_string() -> None:
    """ADE-core source text must not contain a literal merge-action
    invocation."""
    bad_substrings = (
        "gh pr merge",
        "git push origin main",
        "--admin",
        "--force",
    )
    for path in ADE_CORE_MODULES:
        src = _read(path)
        for s in bad_substrings:
            assert s not in src, (
                f"{path.name} contains forbidden merge/deploy substring: {s!r}"
            )


# ---------------------------------------------------------------------------
# Intent 3 — No Level 6 behavior is reachable
# ---------------------------------------------------------------------------


def test_intent_3_governance_status_pins_level_6_permanently_disabled() -> None:
    """``reporting.governance_status`` snapshot pins Level 6 status."""
    snap = gs.collect_status()
    assert snap["autonomy"]["level_6_status"] == "permanently_disabled"


def test_intent_3_autonomy_ladder_doc_states_level_6_permanently_disabled() -> None:
    """``docs/governance/autonomy_ladder.md`` describes Level 6 as
    permanently disabled."""
    text = _read(DOCS_GOV / "autonomy_ladder.md").lower()
    assert "level 6" in text or "| 6 |" in text
    assert "permanently disabled" in text


def test_intent_3_adr_015_states_level_6_permanently_disabled() -> None:
    """ADR-015 (the authority-chain ADR) pins Level 6 as permanently
    disabled."""
    text = _read(DOCS_ADR / "ADR-015-claude-agent-governance.md").lower()
    assert "level 6" in text
    assert "permanently disabled" in text


# ---------------------------------------------------------------------------
# Intent 4 — No forbidden imports / subprocess / network usage in ADE core
# ---------------------------------------------------------------------------


def test_intent_4_no_forbidden_imports_in_any_ade_core_module() -> None:
    """AST scan of every ADE-core module rejects QRE / live / IR /
    subprocess / network imports."""
    for path in ADE_CORE_MODULES:
        imports = _imports(_read(path))
        offenders = sorted(
            i for i in imports
            if any(
                i == prefix or i.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            )
        )
        assert not offenders, (
            f"{path.name} imports forbidden module(s): {offenders}. "
            "ADE core stays stdlib + ADE peers + classifiers + audit "
            "ledger only."
        )


def test_intent_4_step5_loop_module_when_present_passes_forbidden_import_scan() -> None:
    """If the future ``reporting.development_step5_loop`` module exists,
    apply the same AST scan to it. If it does not yet exist (the
    expected state on this PR), the assertion is vacuous and the test
    passes — see ``test_intent_8_*`` for the absence pin."""
    if STEP5_LOOP_MODULE.is_file():
        imports = _imports(_read(STEP5_LOOP_MODULE))
        offenders = sorted(
            i for i in imports
            if any(
                i == prefix or i.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            )
        )
        assert not offenders, (
            "development_step5_loop.py imports forbidden module(s): "
            f"{offenders}. Step 5 module must respect the same "
            "loose-coupling pin as A8–A13 ADE-core peers."
        )


# ---------------------------------------------------------------------------
# Intent 5 — No protected-path writes from ADE core
# ---------------------------------------------------------------------------


def test_intent_5_ade_core_atomic_writes_target_only_logs_directory() -> None:
    """No ADE-core source file contains a string-literal write target
    that begins with a protected directory."""
    forbidden_write_prefixes = (
        "research/",
        "dashboard/",
        "automation/",
        "broker/",
        "execution/",
        "strategies/",
        "orchestration/",
        "agent/",
        ".claude/",
        ".github/",
    )
    for path in ADE_CORE_MODULES:
        src = _read(path)
        for prefix in forbidden_write_prefixes:
            # We accept the prefix appearing as a *forbidden-import
            # documentation reference* in docstrings (e.g. ``research``
            # named as a denied import). What we reject is a string
            # literal that *looks like* a write target — i.e. starts
            # with one of these prefixes, contains a ``/``, and ends
            # with a typical write extension.
            for ext in (".json", ".jsonl", ".md"):
                bad = f'"{prefix}'
                # Walk every occurrence and check whether any of them
                # ends with the extension before the closing quote.
                idx = 0
                while True:
                    j = src.find(bad, idx)
                    if j < 0:
                        break
                    end = src.find('"', j + len(bad))
                    snippet = src[j:end + 1] if end > 0 else ""
                    assert ext not in snippet or "frozen" in snippet.lower(), (
                        f"{path.name} contains a forbidden-prefix write "
                        f"target snippet: {snippet!r}"
                    )
                    idx = j + len(bad)


# ---------------------------------------------------------------------------
# Intent 6 — No QRE hard dependency
# ---------------------------------------------------------------------------


def test_intent_6_no_ade_core_module_imports_research_or_intelligent_routing() -> None:
    """The QRE / Intelligent Routing carve-out is restated explicitly
    so a future careless edit to ``FORBIDDEN_IMPORT_PREFIXES`` cannot
    silently lift it."""
    qre_or_ir = ("research", "reporting.intelligent_routing")
    for path in ADE_CORE_MODULES:
        imports = _imports(_read(path))
        offenders = sorted(
            i for i in imports
            if any(i == p or i.startswith(p + ".") for p in qre_or_ir)
        )
        assert not offenders, (
            f"{path.name} imports QRE / Intelligent Routing module: "
            f"{offenders}. ADE/QRE loose coupling is load-bearing."
        )


# ---------------------------------------------------------------------------
# Intent 7 — No research artifact mutation
# ---------------------------------------------------------------------------


def test_intent_7_digest_pins_no_upstream_artifact_mutation() -> None:
    """Operational digest carries an explicit
    ``mutates_upstream_artifacts: False`` discipline invariant."""
    snap = dod.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    inv = snap["discipline_invariants"]
    assert inv["mutates_upstream_artifacts"] is False
    assert inv["sends_notifications"] is False
    assert inv["writes_dashboard"] is False
    assert inv["auto_authorises_step5"] is False


def test_intent_7_e2e_proof_pins_no_production_mutation() -> None:
    """The E2E proof harness carries
    ``mutates_production_artifacts: False`` and never opens real
    branches / PRs / subprocess / network."""
    snap = e2e.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    inv = snap["discipline_invariants"]
    assert inv["mutates_production_artifacts"] is False
    assert inv["actually_modifies_target"] is False
    assert inv["creates_real_branches"] is False
    assert inv["opens_real_prs"] is False
    assert inv["uses_subprocess_or_network"] is False


# ---------------------------------------------------------------------------
# Intent 8 — Dry-run mode is mandatory for first slice (absence pin)
# ---------------------------------------------------------------------------


def test_intent_8_step5_loop_production_module_does_not_exist_on_this_branch() -> None:
    """Pin the *absence* of ``reporting/development_step5_loop.py``.

    A14 anchors a tests-first preparation phase. The first
    Step 5.0 implementation slice will be the *minimal stub* under a
    separately authorised PR; until then, this file must not exist.
    Once the stub lands, this test will be replaced (in that PR) with
    pin tests on the stub surface — see ``step5_design.md`` §13.
    """
    assert not STEP5_LOOP_MODULE.is_file(), (
        "reporting/development_step5_loop.py must not exist before the "
        "separately authorised Step 5.0 implementation PR. Adding the "
        "module here would violate A14's tests-first scope and §12 G10 "
        "(operator authorisation required)."
    )


def test_intent_8_step5_design_doc_declares_step5_0_first_slice_dry_run_only() -> None:
    """``docs/governance/step5_design.md`` §13 declares Step 5.0 as
    dry-run only."""
    text = _read(DOCS_GOV / "step5_design.md")
    assert "dry-run" in text.lower() or "dry_run_only" in text.lower()
    assert "creates_real_branches: false" in text
    assert "opens_real_prs: false" in text


# ---------------------------------------------------------------------------
# Intent 9 — Release-gate evidence required before implementation
# ---------------------------------------------------------------------------


def test_intent_9_step5_design_doc_pins_release_gate_in_readiness_g3() -> None:
    """§12 G3 requires E2E proof + protected_path/qre_coupling clean."""
    text = _read(DOCS_GOV / "step5_design.md")
    assert "G3" in text
    assert "proof_status=passed" in text
    assert "protected_path_violations" in text
    assert "qre_coupling_violations" in text


def test_intent_9_release_gate_evidence_keys_are_closed_vocabulary() -> None:
    """A9's evidence keys remain a closed 6-set; Step 5 reuses it."""
    expected_keys = {
        "ci_status",
        "smoke_status",
        "governance_lint_status",
        "frozen_hash_status",
        "no_touch_path_delta_status",
        "queue_cross_reference_status",
    }
    src = _read(REPORTING_DIR / "development_release_gate.py")
    for key in expected_keys:
        assert key in src, f"release-gate evidence key {key} missing from source"


# ---------------------------------------------------------------------------
# Intent 10 — Rollback / kill-switch contract exists or is required
# ---------------------------------------------------------------------------


def test_intent_10_step5_design_doc_has_kill_switch_section() -> None:
    """§9 of the design doc enumerates kill-switch mechanisms and
    rollback semantics."""
    text = _read(DOCS_GOV / "step5_design.md")
    assert "Kill switch" in text or "kill switch" in text.lower()
    assert "rollback" in text.lower() or "Rollback" in text


def test_intent_10_rollback_drill_doc_exists_in_governance() -> None:
    """The repository-level rollback drill runbook is present."""
    rollback_doc = DOCS_GOV / "rollback_drill.md"
    assert rollback_doc.is_file(), (
        "docs/governance/rollback_drill.md is the canonical rollback "
        "runbook required by §12 G12."
    )


# ---------------------------------------------------------------------------
# Intent 11 — Human / operator authorisation remains required
# ---------------------------------------------------------------------------


def test_intent_11_digest_pins_operator_step5_authorisation_required_true() -> None:
    """The digest's discipline invariants pin operator authorisation
    as required."""
    snap = dod.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    inv = snap["discipline_invariants"]
    assert inv["operator_step5_authorisation_required"] is True


def test_intent_11_e2e_proof_pins_operator_step5_authorisation_required_true() -> None:
    """E2E proof discipline invariants likewise pin operator
    authorisation as required."""
    snap = e2e.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")
    inv = snap["discipline_invariants"]
    assert inv["operator_step5_authorisation_required"] is True


def test_intent_11_a14_roadmap_entry_states_operator_authorisation_required() -> None:
    """§A14 of the canonical roadmap states operator authorisation is
    required for Step 5.0 implementation."""
    text = _read(DOCS_ROADMAP / "autonomous_development.txt")
    assert "A14" in text
    assert (
        "operator authorisation" in text.lower()
        or "operator-authored" in text.lower()
    )
    assert "Step 5 implementation" in text and "BLOCKED" in text


# ---------------------------------------------------------------------------
# Intent 12 — Test-weakening patterns are rejected or absent
# ---------------------------------------------------------------------------


def test_intent_12_this_test_file_contains_no_test_weakening_tokens() -> None:
    """Self-pin: this file must not contain any of the closed
    ``TEST_WEAKENING_TOKENS`` as runtime decorators or invocations.

    The constant table itself stores the tokens via fragmented
    string concatenation, so the literal forms never appear in
    source. Any contiguous occurrence of a token in the rendered
    source is therefore a real weakening attempt.
    """
    src = _read(Path(__file__).resolve())
    for tok in TEST_WEAKENING_TOKENS:
        assert tok not in src, (
            f"Token {tok!r} found in this file. Test weakening is "
            "denied per docs/governance/no_test_weakening.md."
        )


def test_intent_12_no_test_weakening_tokens_in_existing_ade_core_test_surface() -> None:
    """Existing ADE-core test files already pass the
    ``deny_test_weakening`` hook on edit. This regression pin keeps
    them clean against future drift."""
    test_dir = REPO_ROOT / "tests" / "unit"
    ade_test_files = [
        test_dir / "test_development_work_queue.py",
        test_dir / "test_development_release_gate.py",
        test_dir / "test_development_release_gate_status.py",
        test_dir / "test_development_bugfix_loop.py",
        test_dir / "test_development_delegation.py",
        test_dir / "test_development_operational_digest.py",
        test_dir / "test_development_e2e_proof.py",
    ]
    for path in ade_test_files:
        if not path.is_file():
            continue
        src = _read(path)
        for tok in TEST_WEAKENING_TOKENS:
            assert tok not in src, (
                f"{path.name} contains test-weakening token {tok!r}. "
                "Per docs/governance/no_test_weakening.md, skip / xfail "
                "/ relaxed asserts require a human-authored PR with "
                "operator approval."
            )


# ---------------------------------------------------------------------------
# Cross-cutting closed-vocabulary cardinality pins
# ---------------------------------------------------------------------------


def test_step5_criteria_vocabulary_is_closed_and_ten_long() -> None:
    """STEP5_CRITERIA stays a closed 10-tuple. New criteria require a
    code change pinned by a test update."""
    assert isinstance(dod.STEP5_CRITERIA, tuple)
    assert len(dod.STEP5_CRITERIA) == 10
    assert "release_gate_artifact_present" in dod.STEP5_CRITERIA
    assert "ade_qre_loose_coupling_clean" in dod.STEP5_CRITERIA
    assert "no_protected_path_violations" in dod.STEP5_CRITERIA


def test_ade_module_versions_match_a8_to_a13_anchors() -> None:
    """A8–A13 module versions are pinned. Step 5.0 will land as A14;
    this test will be extended at that point."""
    assert dwq.MODULE_VERSION == "v3.15.16.A8"
    assert drg.MODULE_VERSION == "v3.15.16.A9"
    assert dbl.MODULE_VERSION == "v3.15.16.A10"
    assert ddl.MODULE_VERSION == "v3.15.16.A11"
    assert dod.MODULE_VERSION == "v3.15.16.A12"
    assert e2e.MODULE_VERSION == "v3.15.16.A13"


def test_step5_loop_module_version_anchor_does_not_exist_yet() -> None:
    """The Step 5.0 module-version anchor (proposed ``v3.15.16.A14``)
    must not exist as a Python-file constant on this branch — the
    A14 roadmap entry is the canonical anchor; the matching Python
    constant lands only with the separately authorised Step 5.0 PR."""
    if not STEP5_LOOP_MODULE.is_file():
        # Expected state on this branch.
        return
    src = _read(STEP5_LOOP_MODULE)
    # If the file does exist (future state), the version constant
    # must follow the existing A8–A13 naming convention.
    assert "MODULE_VERSION" in src and "v3.15.16.A14" in src, (
        "If reporting/development_step5_loop.py exists, it must declare "
        "MODULE_VERSION following the A8-A13 convention "
        "(v3.15.16.A14)."
    )


@pytest.fixture(scope="module")
def _proof_snapshot() -> dict:
    """Compute the E2E proof snapshot once; reuse across tests that
    need to read its top-level fields."""
    return e2e.collect_snapshot(generated_at_utc="2026-05-08T00:00:00Z")


def test_proof_snapshot_pins_step5_blocking_invariants(_proof_snapshot: dict) -> None:
    """End-to-end pin: a freshly run E2E proof on synthetic fixtures
    declares Step 5 implementation blocked, design planning allowed,
    and operator authorisation required."""
    snap = _proof_snapshot
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_design_planning_allowed"] is True
    assert snap["discipline_invariants"]["operator_step5_authorisation_required"] is True
    assert snap["discipline_invariants"]["actually_modifies_target"] is False
    assert snap["discipline_invariants"]["creates_real_branches"] is False
    assert snap["discipline_invariants"]["opens_real_prs"] is False
    assert snap["discipline_invariants"]["uses_subprocess_or_network"] is False
