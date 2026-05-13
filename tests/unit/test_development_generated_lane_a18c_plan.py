"""Pin-tests for the A18c admission-integration plan-only doc.

These tests do **not** activate any runtime gate. They pin that
the plan doc at
``docs/governance/development_generated_lane_a18c_plan.md``:

* exists, is non-trivial, and is plain markdown;
* states explicitly that A18c is plan-only / not implemented;
* identifies the future operator-go phrases verbatim
  (``GO A18c admission integration`` and
  ``GO enable A18c on VPS``);
* documents the proposed env-gate name
  ``ADE_GENERATED_LANE_A18C_ENABLED`` with the exact enabled
  value ``"true"``;
* documents the per-tick (8) and per-day (32) caps verbatim;
* documents the Phase-2 diagnostic row protection (the row
  with ``generated_candidate_id = a18b-phase2-smoke-2026-05-13-001``
  and ``would_require_operator_go=True`` must remain
  diagnostic / blocked / needs_human until a future
  operator-approved promotion rule explicitly authorises it);
* documents the A18b topology caveat (Option α host-side write
  + remount currently operationally pinned; Option β2
  directory-mount migration is a future decision and is NOT
  implemented by this plan PR);
* re-asserts the Step 5 + Level 6 + dry-run / live-merge /
  deploy-coupled invariants explicitly;
* cross-references A18a/A18b doc, the A18b host-side write
  runbook, the Phase 0 baseline observation runbook, the A17
  queue-admission policy doc and module, and ADR-015.

In addition, the test suite verifies:

* **No A18c module exists on disk** —
  ``reporting/development_generated_lane_a18c.py`` (and any
  ``a18c``-suffixed sibling) must not exist.
* **A17 admission module contains no active code path that reads
  ``generated_seed.jsonl``** — narrative docstring references and
  the discipline-invariant flag ``writes_to_generated_seed_jsonl=False``
  are legitimate and required; the test forbids only an active
  read code path.

This is a documentation pin-test, not a runtime gate. The plan
doc grants ADE zero new authority.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "development_generated_lane_a18c_plan.md"
)


def _plan_text() -> str:
    return PLAN_PATH.read_text(encoding="utf-8")


# A markdown fenced code block opens with a line starting with ```
# and closes with a matching line. The negative pin-tests below
# scan only the *contents* of these blocks, because the plan doc
# necessarily quotes every forbidden imperative in its narrative
# negative list and those mentions are legitimate. Operators only
# copy commands out of fenced blocks, so the relevant safety
# concern is "do not let a fenced block contain a mutating shape".
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _plan_code_blocks() -> str:
    """Concatenated text of every fenced code block in the plan
    doc. Lower-cased so the imperative-shape pins can be written
    in lowercase without per-phrase ``.lower()`` calls."""
    text = _plan_text()
    return "\n".join(m.group(1) for m in _FENCE_RE.finditer(text)).lower()


# ---------------------------------------------------------------------------
# Existence + shape
# ---------------------------------------------------------------------------


def test_plan_file_exists() -> None:
    assert PLAN_PATH.is_file(), (
        f"A18c plan-only doc missing: {PLAN_PATH}"
    )


def test_plan_is_non_empty() -> None:
    text = _plan_text()
    assert len(text) > 6000, (
        f"A18c plan doc is too short ({len(text)} bytes); "
        "the plan must document the full admission-integration design."
    )


def test_plan_is_markdown() -> None:
    text = _plan_text()
    assert text.lstrip().startswith("# "), (
        "plan must be a markdown file beginning with a top-level "
        "heading."
    )


# ---------------------------------------------------------------------------
# Plan-only / not-implemented language.
# ---------------------------------------------------------------------------


def test_plan_states_plan_only() -> None:
    text = _plan_text().lower()
    assert "plan only" in text or "plan-only" in text, (
        "plan must explicitly state it is plan-only."
    )


def test_plan_states_not_implemented() -> None:
    text = _plan_text().lower()
    assert "not implemented" in text, (
        "plan must explicitly state A18c is not implemented."
    )


# ---------------------------------------------------------------------------
# Operator-go phrases verbatim.
# ---------------------------------------------------------------------------


def test_plan_documents_phase4_implementation_go_phrase() -> None:
    text = _plan_text()
    assert "GO A18c admission integration" in text, (
        "plan must document the exact Phase 4 implementation "
        "operator-go phrase 'GO A18c admission integration'."
    )


def test_plan_documents_runtime_activation_go_phrase() -> None:
    text = _plan_text()
    assert "GO enable A18c on VPS" in text, (
        "plan must document the exact runtime activation "
        "operator-go phrase 'GO enable A18c on VPS'."
    )


# ---------------------------------------------------------------------------
# Env gate proposal.
# ---------------------------------------------------------------------------


def test_plan_documents_env_gate_name() -> None:
    text = _plan_text()
    assert "ADE_GENERATED_LANE_A18C_ENABLED" in text, (
        "plan must document the proposed env-gate name "
        "'ADE_GENERATED_LANE_A18C_ENABLED' verbatim."
    )


def test_plan_documents_env_gate_enabled_value() -> None:
    """The plan documents that the env-gate enabled value is the
    exact literal string ``"true"``. The value must appear in
    quoted form near the env-gate-name discussion."""
    text = _plan_text()
    idx = text.find("ADE_GENERATED_LANE_A18C_ENABLED")
    assert idx != -1
    nearby = text[idx : idx + 600]
    assert '`true`' in nearby or '"true"' in nearby, (
        "plan must document the env-gate enabled value as the "
        "exact literal string 'true' near the env-gate name."
    )


# ---------------------------------------------------------------------------
# Caps verbatim.
# ---------------------------------------------------------------------------


def test_plan_documents_per_tick_cap_of_eight() -> None:
    text = _plan_text()
    # The integer 8 should appear with the per-tick description.
    # Allow either the bare integer in a code fence (`8`) or a
    # backtick form, plus the explicit "per-tick" phrasing.
    assert "per-tick" in text.lower() or "per tick" in text.lower(), (
        "plan must document a per-tick cap with the phrase 'per-tick'."
    )
    assert "`8`" in text, (
        "plan must document the per-tick cap as the exact integer 8."
    )


def test_plan_documents_per_day_cap_of_thirtytwo() -> None:
    text = _plan_text()
    assert "per-day" in text.lower() or "per day" in text.lower(), (
        "plan must document a per-day cap with the phrase 'per-day'."
    )
    assert "`32`" in text, (
        "plan must document the per-day cap as the exact integer 32."
    )


# ---------------------------------------------------------------------------
# Phase-2 diagnostic row protection.
# ---------------------------------------------------------------------------


def test_plan_references_phase2_diagnostic_candidate_id() -> None:
    """The plan must reference the exact Phase-2 diagnostic
    ``generated_candidate_id`` so it cannot be silently relaxed
    in a future drift."""
    text = _plan_text()
    assert "a18b-phase2-smoke-2026-05-13-001" in text, (
        "plan must reference the Phase-2 diagnostic "
        "generated_candidate_id 'a18b-phase2-smoke-2026-05-13-001' "
        "verbatim."
    )


def test_plan_pins_would_require_operator_go_true_maps_to_needs_human() -> None:
    text = _plan_text()
    assert "would_require_operator_go" in text, (
        "plan must reference would_require_operator_go."
    )
    # The doc must document that True maps to needs_human (never
    # admissible).
    lowered = text.lower()
    assert "would_require_operator_go = true" in lowered or (
        "would_require_operator_go` = true" in lowered
    ) or "would_require_operator_go = `true`" in lowered or (
        "would_require_operator_go=true" in lowered
    ) or "would_require_operator_go = `true`" in lowered or (
        "would_require_operator_go` = `true`" in lowered
    ) or "would_require_operator_go=true" in lowered, (
        "plan must contain a 'would_require_operator_go = True' "
        "shape in the decision-mapping table."
    )
    # The mapping must explicitly include needs_human.
    assert "needs_human" in lowered, (
        "plan must document the 'needs_human' admission decision "
        "for would_require_operator_go=True rows."
    )


def test_plan_pins_phase2_row_never_admissible() -> None:
    text = _plan_text().lower()
    # The doc must state that the diagnostic row never becomes
    # admissible / executable without a separate operator-approved
    # promotion rule.
    assert "never become" in text or "must remain diagnostic" in text or (
        "remain diagnostic" in text
    ) or "remains diagnostic" in text, (
        "plan must state explicitly that the Phase-2 diagnostic "
        "row remains diagnostic / never becomes admissible."
    )
    assert "executable" in text, (
        "plan must mention 'executable' so its negation is explicit."
    )


# ---------------------------------------------------------------------------
# Topology caveat (Option α / Option β2).
# ---------------------------------------------------------------------------


def test_plan_documents_option_alpha_currently_pinned() -> None:
    text = _plan_text().lower()
    assert "option α" in text or "option alpha" in text, (
        "plan must reference Option α (host-side write + remount)."
    )
    # "currently" / "operationally pinned" / similar phrasing.
    assert "operationally pinned" in text or "currently" in text, (
        "plan must state Option α is currently / operationally pinned."
    )


def test_plan_documents_option_beta2_not_implemented_here() -> None:
    text = _plan_text().lower()
    assert "option β2" in text or "option beta2" in text or "option b2" in text, (
        "plan must reference Option β2 (directory-mount migration)."
    )
    # The plan must say β2 is not implemented in this PR.
    assert "does not implement option β2" in text or (
        "does not implement option beta2" in text
    ) or "not implemented by this plan" in text or (
        "does not implement" in text
    ), (
        "plan must state explicitly that Option β2 is not "
        "implemented by this plan-only PR."
    )


# ---------------------------------------------------------------------------
# Closed-vocab discipline invariants.
# ---------------------------------------------------------------------------


def test_plan_states_step5_implementation_allowed_false() -> None:
    text = _plan_text()
    assert "step5_implementation_allowed" in text
    idx = text.find("step5_implementation_allowed")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "step5_implementation_allowed must be stated as `false` "
        "explicitly in the plan."
    )


def test_plan_states_step5_enabled_substage_none() -> None:
    text = _plan_text()
    assert (
        "STEP5_ENABLED_SUBSTAGE" in text
        or "step5_enabled_substage" in text
    )
    lowered = text.lower()
    assert '"none"' in text or " none" in lowered, (
        "STEP5_ENABLED_SUBSTAGE must be stated as 'none'."
    )


def test_plan_states_level_6_permanently_disabled() -> None:
    text = _plan_text().lower()
    assert "level 6" in text
    assert "permanently disabled" in text, (
        "plan must state Level 6 remains permanently disabled."
    )


def test_plan_states_dry_run_only_invariant() -> None:
    text = _plan_text()
    assert "dry_run_only" in text
    idx = text.find("dry_run_only")
    nearby = text[idx : idx + 200].lower()
    assert "true" in nearby, (
        "dry_run_only must be stated as `true` explicitly."
    )


def test_plan_states_live_merge_implemented_false() -> None:
    text = _plan_text()
    assert "live_merge_implemented" in text
    idx = text.find("live_merge_implemented")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "live_merge_implemented must be stated as `false`."
    )


def test_plan_states_deploy_coupled_false() -> None:
    text = _plan_text()
    assert "deploy_coupled" in text
    idx = text.find("deploy_coupled")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "deploy_coupled must be stated as `false`."
    )


def test_plan_contains_combined_invariants_block() -> None:
    """The plan must state the six core invariants in a single
    ~1.2 KiB window."""
    text = _plan_text().lower()
    needles = (
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
    )
    first_idx = text.find(needles[0])
    while first_idx != -1:
        window = text[first_idx : first_idx + 1200]
        if all(n in window for n in needles):
            return
        first_idx = text.find(needles[0], first_idx + 1)
    raise AssertionError(
        "plan must state all six invariants "
        f"({needles!r}) within a single ~1.2 KiB window."
    )


# ---------------------------------------------------------------------------
# No-existence pins: A18c module must NOT exist on disk; A17
# admission module must NOT contain an active read code path for
# generated_seed.jsonl.
# ---------------------------------------------------------------------------


_FORBIDDEN_A18C_MODULES: tuple[str, ...] = (
    "reporting/development_generated_lane_a18c.py",
    "reporting/development_generated_lane_a18c_status.py",
    "reporting/development_generated_lane_a18c_writer.py",
    "reporting/development_generated_lane_a18c_admission.py",
)


def test_no_a18c_module_exists() -> None:
    """A18c is plan-only. No production module may exist on disk."""
    for rel in _FORBIDDEN_A18C_MODULES:
        path = REPO_ROOT / rel
        assert not path.exists(), (
            f"A18c module must not exist (plan-only): {rel}"
        )


def test_a17_admission_module_has_no_active_generated_seed_read() -> None:
    """A17's admission module must not actively read
    generated_seed.jsonl. Narrative docstring references and the
    discipline-invariant flag ``writes_to_generated_seed_jsonl=False``
    are legitimate and required; the test forbids only an active
    read code path (read_text / open / Path() with
    'generated_seed' in the call-site source-text).

    The strategy: parse the A17 admission module's AST; flag any
    Call node whose argument literal contains the string
    'generated_seed'. (Narrative mentions in module docstrings and
    constant-dict values like
    ``"writes_to_generated_seed_jsonl": False`` are Str literals
    not inside Call expressions, so they are not flagged.)"""
    a17_path = (
        REPO_ROOT
        / "reporting"
        / "development_queue_admission_policy.py"
    )
    src = a17_path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if "generated_seed" in arg.value.lower():
                    offenders.append(
                        f"line {node.lineno}: Call with string "
                        f"arg containing 'generated_seed': "
                        f"{arg.value!r}"
                    )
    assert not offenders, (
        "A17 admission module must not contain a Call expression "
        "whose argument references 'generated_seed' (no active "
        f"read code path). Offenders: {offenders}"
    )


def test_a18b_writer_constants_agree() -> None:
    """Defense-in-depth: when the writer module changes its env
    var name, this plan doc would silently disagree. We re-validate
    the writer constants at test time."""
    from reporting import (  # noqa: WPS433 — local import intentional
        development_generated_lane_writer as w,
    )

    assert w.ENV_WRITER_ENABLED == "ADE_GENERATED_LANE_WRITER_ENABLED"
    assert w.GENERATED_SEED_PATH.name == "generated_seed.jsonl"


def test_a17_module_version_constant_agrees() -> None:
    """The plan documents A17's MODULE_VERSION as v3.15.16.A17.
    Test re-validates at import time."""
    from reporting import (  # noqa: WPS433 — local import intentional
        development_queue_admission_policy as a17,
    )

    assert a17.MODULE_VERSION == "v3.15.16.A17"


# ---------------------------------------------------------------------------
# Negative pins — plan's executable surface (fenced code blocks)
# must contain no env enable, no Step 5 / Level 6 flip, no
# GitHub-mutation command, no token mint/verify CLI, no A18c
# implementation imperative.
# ---------------------------------------------------------------------------


def test_plan_code_blocks_do_not_enable_a18c_env_flag() -> None:
    """The plan documents the proposed env-gate value but must NOT
    actually export the flag in any executable block."""
    code = _plan_code_blocks()
    forbidden = (
        "ade_generated_lane_a18c_enabled=true",
        'ade_generated_lane_a18c_enabled="true"',
        "export ade_generated_lane_a18c_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block must NOT enable the A18c env flag: "
            f"{phrase!r}"
        )


def test_plan_code_blocks_do_not_enable_a18b_writer() -> None:
    code = _plan_code_blocks()
    forbidden = (
        "ade_generated_lane_writer_enabled=true",
        'ade_generated_lane_writer_enabled="true"',
        "export ade_generated_lane_writer_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block must NOT enable the A18b writer: "
            f"{phrase!r}"
        )


def test_plan_code_blocks_do_not_enable_n5b_live_execute() -> None:
    code = _plan_code_blocks()
    forbidden = (
        "ade_n5b_live_execute_enabled=true",
        'ade_n5b_live_execute_enabled="true"',
        "export ade_n5b_live_execute_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block must NOT enable N5b live execute: "
            f"{phrase!r}"
        )


def test_plan_code_blocks_contain_no_real_merge_command() -> None:
    code = _plan_code_blocks()
    forbidden = (
        "gh pr merge --squash",
        "gh pr merge --rebase",
        "gh pr merge --merge",
        "gh pr review --approve",
        "gh pr review --request-changes",
        "git merge --no-ff",
        "git push --force",
        "git push -f ",
        "git push origin main",
        "--admin",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block contains a forbidden mutating-command "
            f"shape: {phrase!r}"
        )


def test_plan_code_blocks_do_not_flip_step5_or_level6() -> None:
    code = _plan_code_blocks()
    forbidden = (
        "step5_implementation_allowed = true",
        'step5_implementation_allowed="true"',
        "step5_implementation_allowed=true",
        'step5_enabled_substage = "5.0"',
        'step5_enabled_substage = "5.1"',
        'step5_enabled_substage = "5.2"',
        'step5_enabled_substage="5.0"',
        'step5_enabled_substage="5.1"',
        'step5_enabled_substage="5.2"',
        "level6_enabled = true",
        "level6_enabled=true",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "plan code block contains a forbidden "
            f"authority-escalation flip: {phrase!r}"
        )


def test_plan_code_blocks_do_not_instruct_token_mint_or_verify() -> None:
    code = _plan_code_blocks()
    forbidden = (
        "approval_token_runtime.mint",
        "approval_token_runtime.verify",
        "mint_approval_token",
        "verify_approval_token",
        "--mint-token",
        "--verify-token",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block contains a forbidden token "
            f"mint/verify invocation: {phrase!r}"
        )


def test_plan_code_blocks_do_not_use_unsupported_writer_status_flag() -> None:
    """The A18b writer CLI has no '--status' flag; the plan must
    not reference one in executable form."""
    code = _plan_code_blocks()
    forbidden = (
        "development_generated_lane_writer --status",
        "python3 -m reporting.development_generated_lane_writer --status",
        "python -m reporting.development_generated_lane_writer --status",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block contains the unsupported writer "
            f"'--status' flag: {phrase!r}"
        )


def test_plan_code_blocks_do_not_authorise_a18c_implementation() -> None:
    """Narrative negative mentions ('A18c is not implemented')
    are required and legitimate. The plan's executable surface
    must NOT contain an imperative that authorises implementation."""
    code = _plan_code_blocks()
    forbidden = (
        "implement a18c",
        "build a18c",
        "ship a18c",
        "enable a18c",
        "a18c is implemented",
        "a18c is enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"plan code block contains a phrase that would "
            f"authorise A18c implementation: {phrase!r}"
        )


def test_plan_does_not_instruct_touching_no_touch_paths() -> None:
    text = _plan_text().lower()
    forbidden_imperatives = (
        "edit .claude",
        "modify .claude",
        "write to .claude",
        "edit .gitleaks.toml",
        "modify .gitleaks.toml",
        "disable .gitleaks.toml",
        "weaken .gitleaks.toml",
        "edit seed.jsonl",
        "modify seed.jsonl",
        "write to seed.jsonl",
        "append to seed.jsonl",
        "edit delegation_seed.jsonl",
        "modify delegation_seed.jsonl",
        "write to delegation_seed.jsonl",
        "append to delegation_seed.jsonl",
        "weaken the test",
        "weaken the tests",
        "skip the gate",
        "bypass the hook",
        "bypass hooks",
    )
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"plan contains a forbidden no-touch-path / "
            f"safety-bypass imperative: {phrase!r}"
        )


def test_plan_does_not_instruct_deploy() -> None:
    text = _plan_text().lower()
    forbidden = (
        "trigger the deploy workflow",
        "trigger deploy workflow",
        "force the deploy",
        "couple this to deploy",
    )
    for phrase in forbidden:
        assert phrase not in text, (
            f"plan contains a forbidden deploy-coupling "
            f"instruction: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — no secret material.
# ---------------------------------------------------------------------------


def test_plan_contains_no_pem_secret_block() -> None:
    text = _plan_text()
    dashes = "-" * 5
    pem_kinds = (
        "PRIVATE KEY",
        "EC PRIVATE KEY",
        "RSA PRIVATE KEY",
        "OPENSSH PRIVATE KEY",
    )
    forbidden = [f"{dashes}BEGIN {kind}{dashes}" for kind in pem_kinds]
    for marker in forbidden:
        assert marker not in text, (
            f"plan contains a PEM-style secret block: {marker!r}"
        )


def test_plan_contains_no_inline_hex_64_secret() -> None:
    text = _plan_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"plan embeds a hex-64 literal that looks like a secret: "
        f"{matches!r}"
    )


def test_plan_contains_no_bearer_token_header() -> None:
    text = _plan_text().lower()
    forbidden = (
        "authorization: bearer ",
        "x-api-key: ",
        "ghp_",
        "github_pat_",
        "sk-ant-",
    )
    for pat in forbidden:
        assert pat not in text, (
            f"plan contains a credential-shaped string: {pat!r}"
        )


# ---------------------------------------------------------------------------
# Cross-reference pins.
# ---------------------------------------------------------------------------


def test_plan_cross_references_development_generated_lane_doc() -> None:
    text = _plan_text()
    assert "development_generated_lane.md" in text, (
        "plan must cross-reference the A18a/A18b governance doc."
    )


def test_plan_cross_references_a18b_host_side_runbook() -> None:
    text = _plan_text()
    assert "a18b_writer_host_side_write_runbook.md" in text, (
        "plan must cross-reference the A18b host-side write runbook."
    )


def test_plan_cross_references_baseline_observation_runbook() -> None:
    text = _plan_text()
    assert "autonomous_development_baseline_observation.md" in text, (
        "plan must cross-reference the Phase 0 baseline "
        "observation runbook."
    )


def test_plan_cross_references_a17_doctrine_doc() -> None:
    text = _plan_text()
    assert "queue_admission_policy.md" in text, (
        "plan must cross-reference the A17 queue-admission policy "
        "doctrine doc."
    )


def test_plan_cross_references_a17_module() -> None:
    text = _plan_text()
    assert "reporting/development_queue_admission_policy.py" in text, (
        "plan must cross-reference the A17 admission module path."
    )


def test_plan_cross_references_adr_015() -> None:
    text = _plan_text()
    assert "ADR-015" in text, (
        "plan must cross-reference ADR-015 (Level 6 "
        "permanently-disabled doctrine)."
    )
