"""Pin-tests for the A18b host-side write + remount operator runbook.

These tests do **not** activate any runtime gate. They pin that the
operator runbook at
``docs/governance/a18b_writer_host_side_write_runbook.md``:

* exists, is non-trivial, and is plain markdown;
* references the canonical host seed path
  ``/root/trading-agent/generated_seed.jsonl`` exactly;
* references the canonical container path
  ``/app/generated_seed.jsonl`` exactly;
* references the A18b writer env gate
  ``ADE_GENERATED_LANE_WRITER_ENABLED=true``;
* references the public writer API name
  ``append_generated_seed_record``;
* references ``os.replace`` (writer atomic-replace caveat);
* references ``EBUSY`` and the kernel message
  ``Device or resource busy``;
* references the dashboard recreate / remount command shape;
* re-asserts the Step 5 + Level 6 + dry-run / live-merge /
  deploy-coupled invariants explicitly;
* contains a Phase-2 verified state section;
* contains a §"What this runbook does NOT do" block;
* does NOT instruct an in-container append while the file-level
  bind mount remains in place (the fenced-code-block negative
  pins enforce this);
* does NOT enable Step 5, Level 6, N5b live execute, or any
  approval-token mint/verify CLI;
* does NOT reference the unsupported ``--status`` writer CLI
  flag;
* does NOT embed a PEM block, a hex-64 inline-code literal, or
  a bearer-token header;
* cross-references the canonical doctrine documents.

This is a documentation pin-test, not a runtime gate. The writer
module is not modified by this PR.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "a18b_writer_host_side_write_runbook.md"
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
        "A18b host-side write runbook missing: "
        f"{RUNBOOK_PATH}"
    )


def test_runbook_is_non_empty() -> None:
    text = _runbook_text()
    assert len(text) > 4000, (
        f"A18b host-side write runbook is too short ({len(text)} "
        "bytes); the runbook must document the full procedure."
    )


def test_runbook_is_markdown() -> None:
    text = _runbook_text()
    assert text.lstrip().startswith("# "), (
        "runbook must be a markdown file beginning with a top-level "
        "heading."
    )


# ---------------------------------------------------------------------------
# Canonical paths and constants the runbook must reference.
# ---------------------------------------------------------------------------


def test_runbook_references_canonical_host_seed_path() -> None:
    text = _runbook_text()
    assert "/root/trading-agent/generated_seed.jsonl" in text, (
        "runbook must reference the canonical host seed path "
        "'/root/trading-agent/generated_seed.jsonl' exactly."
    )


def test_runbook_references_canonical_container_seed_path() -> None:
    text = _runbook_text()
    assert "/app/generated_seed.jsonl" in text, (
        "runbook must reference the canonical container seed path "
        "'/app/generated_seed.jsonl' exactly."
    )


def test_runbook_references_env_gate_value_pair() -> None:
    text = _runbook_text()
    assert "ADE_GENERATED_LANE_WRITER_ENABLED=true" in text, (
        "runbook must reference the env-gate value pair "
        "'ADE_GENERATED_LANE_WRITER_ENABLED=true'."
    )


def test_runbook_references_public_api_function_name() -> None:
    text = _runbook_text()
    assert "append_generated_seed_record" in text, (
        "runbook must reference the public writer API name "
        "'append_generated_seed_record'."
    )


def test_runbook_references_os_replace_caveat() -> None:
    text = _runbook_text()
    assert "os.replace" in text, (
        "runbook must reference 'os.replace' (the atomic-replace "
        "site that triggers EBUSY across the file-level bind "
        "mount)."
    )


def test_runbook_references_ebusy_root_cause() -> None:
    text = _runbook_text()
    assert "EBUSY" in text, (
        "runbook must reference EBUSY (the kernel error code)."
    )
    assert "Device or resource busy" in text, (
        "runbook must reference 'Device or resource busy' (the "
        "human-readable kernel message)."
    )


def test_runbook_references_dashboard_remount_command_shape() -> None:
    text = _runbook_text()
    assert (
        "docker compose -p trading-agent up -d --force-recreate dashboard"
        in text
    ), (
        "runbook must reference the canonical dashboard "
        "recreate / remount command shape."
    )


def test_runbook_writer_constants_agree_with_module() -> None:
    """Defense in depth: when the writer module changes its env
    var name or seed path constant, this test fails until the
    runbook is re-aligned."""
    from reporting import (  # noqa: WPS433 — local import intentional
        development_generated_lane_writer as w,
    )

    assert w.ENV_WRITER_ENABLED == "ADE_GENERATED_LANE_WRITER_ENABLED"
    assert w.GENERATED_SEED_PATH.name == "generated_seed.jsonl"
    # The host-side absolute path documented in the runbook is the
    # canonical VPS path; on local checkouts the writer module's
    # constant is repo-root-relative. We assert the basename agrees;
    # the runbook's path is the operational VPS deployment path.
    text = _runbook_text()
    assert w.GENERATED_SEED_PATH.name in text


# ---------------------------------------------------------------------------
# Closed-vocab discipline invariants
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
        "runbook must restate the dry_run_only invariant."
    )
    idx = text.find("dry_run_only")
    nearby = text[idx : idx + 200].lower()
    assert "true" in nearby, (
        "dry_run_only must be stated as `true` explicitly."
    )


def test_runbook_states_live_merge_implemented_false() -> None:
    text = _runbook_text()
    assert "live_merge_implemented" in text, (
        "runbook must restate the live_merge_implemented invariant."
    )
    idx = text.find("live_merge_implemented")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "live_merge_implemented must be stated as `false`."
    )


def test_runbook_states_deploy_coupled_false() -> None:
    text = _runbook_text()
    assert "deploy_coupled" in text, (
        "runbook must restate the deploy_coupled invariant."
    )
    idx = text.find("deploy_coupled")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "deploy_coupled must be stated as `false`."
    )


def test_runbook_contains_combined_invariants_block() -> None:
    """The runbook must somewhere state the six core invariants in
    a single close block so the operator can read them together."""
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
        f"({needles!r}) within a single ~1.2 KiB window."
    )


# ---------------------------------------------------------------------------
# Phase-2 verified state + §"What this runbook does NOT do".
# ---------------------------------------------------------------------------


def test_runbook_documents_phase_2_verified_state() -> None:
    text = _runbook_text().lower()
    assert "phase 2" in text or "phase-2" in text, (
        "runbook must reference the Phase 2 verified state."
    )
    assert "verified" in text or "rest state" in text or "smoke" in text, (
        "runbook must state that Phase 2 closed in a verified rest "
        "state."
    )


def test_runbook_contains_what_this_runbook_does_not_do_section() -> None:
    text = _runbook_text().lower()
    assert "does not do" in text or "does **not** do" in text, (
        "runbook must contain a 'What this runbook does NOT do' "
        "section."
    )


# ---------------------------------------------------------------------------
# Negative pins — the runbook's executable surface (its fenced
# code blocks) must contain no in-container append, no Step 5 /
# Level 6 / N5b-live-execute flip, no GitHub mutation command,
# no token mint/verify CLI, no unsupported writer CLI flag.
# ---------------------------------------------------------------------------


def test_runbook_code_blocks_do_not_attempt_in_container_append() -> None:
    """The runbook is the operationally-pinned host-side procedure.
    Its executable surface must NOT contain any container-side
    append invocation while the file-level bind mount remains in
    place. The narrative §"Forbidden shape" section may discuss the
    forbidden command in prose; we scan only the executable surface
    via fenced code blocks."""
    code = _runbook_code_blocks()
    forbidden = (
        # Direct CLI write attempt (the CLI is status-only but the
        # negative pin defends against future drift).
        "docker compose -p trading-agent exec dashboard "
        "python3 -m reporting.development_generated_lane_writer "
        "--write",
        # Any in-container python heredoc that imports the writer
        # and calls append_generated_seed_record — verbatim shape.
        "docker compose -p trading-agent exec dashboard python3 - <<",
        "docker compose -p trading-agent exec -t dashboard python3 - <<",
        "docker compose exec dashboard python3 - <<",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "runbook code block contains a forbidden in-container "
            f"append shape: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_use_unsupported_status_flag() -> None:
    """The writer CLI has no '--status' flag. The runbook must
    never reference one in executable form."""
    code = _runbook_code_blocks()
    forbidden = (
        "development_generated_lane_writer --status",
        "python3 -m reporting.development_generated_lane_writer --status",
        "python -m reporting.development_generated_lane_writer --status",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "runbook code block contains the unsupported '--status' "
            f"flag: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_enable_n5b_live_execute() -> None:
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


def test_runbook_code_blocks_do_not_authorise_a18c_implementation() -> None:
    """A18c remains plan-only at this stage. The runbook may
    reference A18c (it does — to document that A18c is plan-only)
    but its executable surface must NOT contain an imperative
    that authorises A18c implementation or activation."""
    code = _runbook_code_blocks()
    forbidden = (
        "implement a18c",
        "build a18c",
        "ship a18c",
        "enable a18c",
        "a18c is implemented",
        "a18c is enabled",
        "ade_generated_lane_a18c_enabled=true",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            "runbook code block contains a phrase that would "
            f"authorise A18c implementation: {phrase!r}"
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
            "runbook contains a forbidden no-touch-path / "
            f"safety-bypass imperative: {phrase!r}"
        )


def test_runbook_does_not_instruct_deploy() -> None:
    text = _runbook_text().lower()
    forbidden = (
        "trigger the deploy workflow",
        "trigger deploy workflow",
        "force the deploy",
        "couple this to deploy",
    )
    for phrase in forbidden:
        assert phrase not in text, (
            "runbook contains a forbidden deploy-coupling "
            f"instruction: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — no secret material.
# ---------------------------------------------------------------------------


def test_runbook_contains_no_pem_secret_block() -> None:
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
    documents read-only procedure commands and a synthetic-marker
    SHA-256 example; the example is computed at runtime by the
    operator's shell, not embedded as a literal in the doc."""
    text = _runbook_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"runbook embeds a hex-64 literal that looks like a secret: "
        f"{matches!r}"
    )


def test_runbook_contains_no_bearer_token_header() -> None:
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


def test_runbook_cross_references_development_generated_lane_doc() -> None:
    text = _runbook_text()
    assert "development_generated_lane.md" in text, (
        "runbook must cross-reference the A18a/A18b governance doc."
    )


def test_runbook_cross_references_baseline_observation_runbook() -> None:
    text = _runbook_text()
    assert "autonomous_development_baseline_observation.md" in text, (
        "runbook must cross-reference the Phase-0 baseline "
        "observation runbook."
    )


def test_runbook_cross_references_adr_015() -> None:
    text = _runbook_text()
    assert "ADR-015" in text, (
        "runbook must cross-reference ADR-015 (Level 6 "
        "permanently-disabled doctrine)."
    )
