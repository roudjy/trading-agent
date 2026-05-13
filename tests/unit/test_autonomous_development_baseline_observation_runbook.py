"""Pin-tests for the Phase 0 autonomous-development-lane baseline
observation runbook.

These tests do **not** activate any runtime gate. They pin that the
operator runbook at
``docs/governance/autonomous_development_baseline_observation.md``:

* exists, is non-trivial, and is plain text;
* documents the canonical dry-run-only CLI sequence for the eight
  observation steps;
* uses only the confirmed-existing A18b writer CLI shape
  (``python3 -m reporting.development_generated_lane_writer
  --no-write`` plus the bare invocation without flags);
* does NOT reference any non-existent ``--status`` flag on the
  writer CLI;
* references the canonical seed path exactly
  (``/root/trading-agent/generated_seed.jsonl``);
* does NOT reference a non-canonical
  ``logs/development_generated_lane/`` seed path;
* re-asserts the Step 5 + Level 6 + dry-run / live-merge /
  deploy-coupled invariants explicitly;
* does NOT instruct the operator to enable the A18b writer env
  flag, the N5b live execute env flag, flip a Step 5 flag, raise
  Level 6, merge / push / force-push, mint or verify approval
  tokens, weaken tests, or bypass hooks;
* does NOT embed a PEM block, a hex-64 inline-code literal, or a
  bearer-token-shaped string;
* cross-references the canonical doctrine documents.

This is a documentation pin-test, not a runtime gate. The
projector / writer / scheduler modules referenced by the runbook
each have their own independent pin-tests.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "autonomous_development_baseline_observation.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# A markdown fenced code block opens with a line starting with ```
# and closes with a matching line. The negative pin-tests below
# scan only the *contents* of these blocks, because the runbook
# necessarily quotes every forbidden imperative in its narrative
# negative list and those mentions are legitimate. Operators only
# copy commands out of fenced blocks, so the relevant safety
# concern is "do not let a fenced block contain a mutating shape".
_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def _runbook_code_blocks() -> str:
    """Concatenated text of every fenced code block in the runbook.

    Lower-cased so the imperative-shape pins can be written in
    lowercase without per-phrase ``.lower()`` calls."""
    text = _runbook_text()
    return "\n".join(m.group(1) for m in _FENCE_RE.finditer(text)).lower()


# ---------------------------------------------------------------------------
# Existence + shape
# ---------------------------------------------------------------------------


def test_runbook_file_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        "autonomous-development baseline observation runbook missing: "
        f"{RUNBOOK_PATH}"
    )


def test_runbook_is_non_empty() -> None:
    text = _runbook_text()
    assert len(text) > 4000, (
        f"baseline observation runbook is too short ({len(text)} "
        "bytes); the runbook must document the full eight-step "
        "observation chain."
    )


def test_runbook_is_markdown() -> None:
    text = _runbook_text()
    assert text.lstrip().startswith("# "), (
        "runbook must be a markdown file beginning with a top-level "
        "heading."
    )


# ---------------------------------------------------------------------------
# Canonical CLI invocations (Correction 2 — only the confirmed shape).
# ---------------------------------------------------------------------------


_REQUIRED_CLI_INVOCATIONS: tuple[str, ...] = (
    # The confirmed A18b writer status invocation. The CLI never
    # writes; this is the canonical status-snapshot shape per
    # reporting/development_generated_lane_writer.py:_build_parser.
    "python3 -m reporting.development_generated_lane_writer --no-write",
    "python3 -m reporting.development_merge_preflight --no-write",
    "python3 -m reporting.development_step5_loop --no-write",
    "python3 -m reporting.development_operational_digest --no-write",
    "python3 -m reporting.recurring_maintenance --list-jobs",
)


def test_runbook_documents_every_required_cli_invocation() -> None:
    text = _runbook_text()
    for cmd in _REQUIRED_CLI_INVOCATIONS:
        assert cmd in text, (
            "runbook must contain the canonical CLI invocation "
            f"verbatim: {cmd!r}"
        )


def test_runbook_does_not_use_unsupported_status_flag() -> None:
    """Correction 2 enforcement: the A18b writer CLI has no
    ``--status`` flag. The runbook must never reference one."""
    text = _runbook_text()
    forbidden = (
        "python3 -m reporting.development_generated_lane_writer --status",
        "python -m reporting.development_generated_lane_writer --status",
        "development_generated_lane_writer --status",
    )
    for needle in forbidden:
        assert needle not in text, (
            "runbook must not reference the unsupported "
            f"--status CLI shape: {needle!r}"
        )


def test_runbook_documents_writer_bare_invocation_or_no_write() -> None:
    """The A18b writer's status snapshot is what the bare CLI emits.
    The runbook must document at least the ``--no-write`` shape
    (confirmed parity flag) and the local-dry-run section may also
    document the bare ``python -m`` shape."""
    text = _runbook_text()
    assert (
        "python3 -m reporting.development_generated_lane_writer --no-write"
        in text
    ) or (
        "python -m reporting.development_generated_lane_writer --no-write"
        in text
    ), (
        "runbook must document the --no-write A18b writer CLI shape."
    )


# ---------------------------------------------------------------------------
# Canonical seed path (Correction 1 — repo-root, not logs/).
# ---------------------------------------------------------------------------


def test_runbook_references_canonical_seed_path_exactly() -> None:
    text = _runbook_text()
    assert "/root/trading-agent/generated_seed.jsonl" in text, (
        "runbook must reference the canonical seed path "
        "'/root/trading-agent/generated_seed.jsonl' exactly."
    )


def test_runbook_does_not_reference_non_canonical_seed_path() -> None:
    """Correction 1 enforcement: the canonical seed path is at the
    repo root, not under ``logs/development_generated_lane/``."""
    text = _runbook_text()
    forbidden = (
        "logs/development_generated_lane/generated_seed.jsonl",
        "logs/development_generated_lane/",
    )
    for needle in forbidden:
        assert needle not in text, (
            "runbook must not reference the non-canonical seed path "
            f"{needle!r}; the canonical path lives at the repo root "
            "per reporting.development_generated_lane_writer.GENERATED_SEED_PATH."
        )


def test_runbook_seed_path_agrees_with_writer_module() -> None:
    """Defense in depth — when the writer module changes its
    GENERATED_SEED_PATH constant, this test fails until the runbook
    is re-aligned."""
    from reporting import (  # noqa: WPS433 — local import intentional
        development_generated_lane_writer as a18b_writer,
    )

    # The module constant is repo-relative; the runbook uses the VPS
    # absolute path. The basename must match exactly, and the path
    # must be at the repo root (not inside logs/).
    assert a18b_writer.GENERATED_SEED_PATH.name == "generated_seed.jsonl"
    parent_rel = a18b_writer.GENERATED_SEED_PATH.parent
    repo_root = a18b_writer.REPO_ROOT
    assert parent_rel == repo_root, (
        f"writer's GENERATED_SEED_PATH parent must be repo root; got "
        f"{parent_rel} vs {repo_root}"
    )


# ---------------------------------------------------------------------------
# Closed-vocab discipline invariants (Correction 3 — Step 5 stays off).
# ---------------------------------------------------------------------------


def test_runbook_states_step5_implementation_allowed_false() -> None:
    text = _runbook_text()
    assert "step5_implementation_allowed" in text, (
        "runbook must reaffirm step5_implementation_allowed = false."
    )
    idx = text.find("step5_implementation_allowed")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "step5_implementation_allowed must be stated as `false` "
        "explicitly in the runbook."
    )


def test_runbook_states_step5_enabled_substage_none() -> None:
    text = _runbook_text()
    assert (
        "STEP5_ENABLED_SUBSTAGE" in text
        or "step5_enabled_substage" in text
    ), "runbook must reaffirm the STEP5_ENABLED_SUBSTAGE invariant."
    lowered = text.lower()
    assert '"none"' in text or " none" in lowered, (
        "STEP5_ENABLED_SUBSTAGE must be stated as 'none'."
    )


def test_runbook_states_level_6_permanently_disabled() -> None:
    text = _runbook_text().lower()
    assert "level 6" in text, "runbook must reaffirm Level 6 doctrine."
    assert "permanently disabled" in text, (
        "runbook must state Level 6 remains permanently disabled."
    )


def test_runbook_states_dry_run_only_invariant() -> None:
    text = _runbook_text()
    assert "dry_run_only" in text, (
        "runbook must restate the projector's dry_run_only invariant."
    )
    idx = text.find("dry_run_only")
    nearby = text[idx : idx + 200].lower()
    assert "true" in nearby, (
        "dry_run_only must be stated as `true` explicitly in the "
        "runbook."
    )


def test_runbook_states_live_merge_implemented_false() -> None:
    text = _runbook_text()
    assert "live_merge_implemented" in text, (
        "runbook must restate the live_merge_implemented invariant."
    )
    idx = text.find("live_merge_implemented")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "live_merge_implemented must be stated as `false` explicitly."
    )


def test_runbook_states_deploy_coupled_false() -> None:
    text = _runbook_text()
    assert "deploy_coupled" in text, (
        "runbook must restate the deploy_coupled invariant."
    )
    idx = text.find("deploy_coupled")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "deploy_coupled must be stated as `false` explicitly."
    )


def test_runbook_contains_combined_invariants_block() -> None:
    """The runbook must somewhere state the six core invariants in
    a single close block so the operator can read them together
    without ambiguity. We require all six lowercased substrings to
    appear within the same 1200-character window."""
    text = _runbook_text().lower()
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
        "runbook must state all six invariants "
        f"({needles!r}) within a single ~1.2 KiB window so the "
        "operator can read them together."
    )


# ---------------------------------------------------------------------------
# Negative pins — the runbook's executable surface (its fenced
# code blocks) must contain no authority-escalating shape.
# ---------------------------------------------------------------------------


def test_runbook_code_blocks_do_not_enable_a18b_writer() -> None:
    """The runbook is the Phase 0 observation step. It must NOT
    contain an export of the A18b writer env flag. Activation is a
    separate Phase 1 operator-go (``GO enable A18b writer on VPS``)."""
    code = _runbook_code_blocks()
    forbidden = (
        "ade_generated_lane_writer_enabled=true",
        'ade_generated_lane_writer_enabled="true"',
        "export ade_generated_lane_writer_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "runbook code block must NOT enable the A18b writer: "
            f"{phrase!r}"
        )


def test_runbook_code_blocks_do_not_enable_n5b_live_execute() -> None:
    """N5b Phase 4 live execute is permanently denied without a
    separate distinct operator-go. The runbook's executable surface
    must not contain an env-flag enable line."""
    code = _runbook_code_blocks()
    forbidden = (
        "ade_n5b_live_execute_enabled=true",
        'ade_n5b_live_execute_enabled="true"',
        "export ade_n5b_live_execute_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "runbook code block must NOT enable N5b live execute: "
            f"{phrase!r}"
        )


def test_runbook_code_blocks_contain_no_real_merge_command() -> None:
    """The runbook's executable surface must contain no GitHub
    mutation command."""
    code = _runbook_code_blocks()
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
            "runbook code block contains a forbidden "
            f"mutating-command shape: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_flip_step5_or_level6() -> None:
    """Imperative Step 5 / Level 6 flips would only ever appear as
    executable lines. The invariants block prints the literal
    ``step5_implementation_allowed = false`` etc. so we scan only
    for the *true*-shaped flips."""
    code = _runbook_code_blocks()
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
            "runbook code block contains a forbidden "
            f"authority-escalation flip: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_instruct_token_mint_or_verify() -> None:
    """Phase 0 is pre-token in the sense that it does not invoke
    the N4b mint/verify CLI. The runbook's executable surface must
    not contain such an invocation."""
    code = _runbook_code_blocks()
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
            "runbook code block contains a forbidden token "
            f"mint/verify invocation: {phrase!r}"
        )


def test_runbook_does_not_instruct_touching_no_touch_paths() -> None:
    text = _runbook_text().lower()
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
        "edit generated_seed.jsonl",
        "modify generated_seed.jsonl",
        "write to generated_seed.jsonl",
        "append to generated_seed.jsonl",
        "weaken the test",
        "weaken the tests",
        "skip the gate",
        "bypass the hook",
        "bypass hooks",
    )
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            "runbook contains a forbidden no-touch-path / "
            f"safety-bypass imperative: {phrase!r}"
        )


def test_runbook_does_not_instruct_deploy() -> None:
    text = _runbook_text().lower()
    forbidden = (
        "trigger the deploy workflow",
        "trigger deploy workflow",
        "force the deploy",
        "run the deploy",
        "dispatch the deploy",
        "couple this to deploy",
    )
    for phrase in forbidden:
        assert phrase not in text, (
            "runbook contains a forbidden deploy-coupling "
            f"instruction: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_authorise_a18c_implementation() -> None:
    """A18c remains plan-only at Phase 0. The runbook may reference
    A18c in its narrative negative-list (it does — to document that
    A18c is plan-only). The pin therefore scans only the runbook's
    executable surface (fenced code blocks). Narrative negative
    mentions in prose (``does not plan or implement A18c``) are
    required and live outside fenced blocks."""
    code = _runbook_code_blocks()
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
            "runbook code block contains a phrase that would "
            f"authorise A18c implementation: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — no secret material.
# ---------------------------------------------------------------------------


def test_runbook_contains_no_pem_secret_block() -> None:
    """Defense-in-depth: the runbook must not contain a real PEM
    secret block. The PEM markers are assembled at runtime so the
    test source itself does not embed a literal PEM header."""
    text = _runbook_text()
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
            f"runbook contains a PEM-style secret block: {marker!r}"
        )


def test_runbook_contains_no_inline_hex_64_secret() -> None:
    """A 64-character hex run inside backticks would look like a
    copy-pasted ``openssl rand -hex 32`` output. The runbook
    documents read-only inspection commands and has no business
    quoting an HMAC secret."""
    text = _runbook_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"runbook embeds a hex-64 literal that looks like a secret: "
        f"{matches!r}"
    )


def test_runbook_contains_no_bearer_token_header() -> None:
    """No literal ``Authorization: Bearer <token>`` line; the
    Phase 0 chain is unauthenticated stdlib projection plus VPS
    inspection."""
    text = _runbook_text().lower()
    forbidden = (
        "authorization: bearer ",
        "x-api-key: ",
        "ghp_",
        "github_pat_",
        "sk-ant-",
    )
    for pat in forbidden:
        assert pat not in text, (
            f"runbook contains a credential-shaped string: {pat!r}"
        )


# ---------------------------------------------------------------------------
# Cross-reference pins — the runbook must link back to the doctrine.
# ---------------------------------------------------------------------------


def test_runbook_cross_references_n5b_plan_doc() -> None:
    text = _runbook_text()
    assert "n5b_merge_execution_plan.md" in text, (
        "runbook must cross-reference the N5b plan / governance doc."
    )


def test_runbook_cross_references_n5b_preflight_runbook() -> None:
    text = _runbook_text()
    assert "n5b_merge_preflight_runbook.md" in text, (
        "runbook must cross-reference the N5b Phase 1 preflight "
        "upstream-refresh runbook."
    )


def test_runbook_cross_references_recurring_maintenance() -> None:
    text = _runbook_text()
    assert "recurring_maintenance" in text, (
        "runbook must mention recurring_maintenance (step 7 of the "
        "observation chain)."
    )


def test_runbook_cross_references_adr_015() -> None:
    text = _runbook_text()
    assert "ADR-015" in text, (
        "runbook must cross-reference ADR-015 (Level 6 "
        "permanently-disabled doctrine)."
    )


def test_runbook_cross_references_development_generated_lane_doc() -> None:
    text = _runbook_text()
    assert "development_generated_lane.md" in text, (
        "runbook must cross-reference the A18a/A18b governance doc."
    )
