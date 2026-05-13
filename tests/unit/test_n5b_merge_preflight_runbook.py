"""Pin-tests for the N5b Phase 1 merge-preflight upstream-refresh
operator runbook.

These tests do **not** activate any runtime gate. They pin that the
operator runbook at
``docs/governance/n5b_merge_preflight_runbook.md``:

* exists, is non-trivial, and is plain text;
* documents the canonical dry-run-only CLI sequence for steps
  1 → 5 of the read-only refresh chain;
* references each module by its repo-relative path;
* references each artefact by the exact ``ARTIFACT_RELATIVE_PATH``
  constant declared in the corresponding ``reporting/*`` module
  (so the runbook cannot silently drift away from the schema);
* re-asserts the Step 5 + Level 6 invariants explicitly;
* re-asserts the dry-run / no-live-merge / no-deploy-coupling
  invariants explicitly;
* does NOT instruct the operator to merge a PR, mint or verify an
  approval token, deploy anything, write a seed file, enable
  A18b's runtime writer flag, enable N5b's live-execute flag,
  flip a Step 5 flag, enable Level 6, edit ``.claude/**`` /
  ``.gitleaks.toml`` / no-touch paths, weaken tests, or bypass
  hooks;
* does NOT embed a PEM block, a hex-64 inline-code literal that
  looks like an exported secret, or a bearer-token-shaped
  string.

This is a documentation pin-test, not a runtime gate. The
projector code at
``reporting/development_merge_preflight.py`` already enforces
read-only behaviour at import / collect / write time and is
independently pinned by
``tests/unit/test_development_merge_preflight.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = (
    REPO_ROOT / "docs" / "governance" / "n5b_merge_preflight_runbook.md"
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
        f"N5b merge-preflight runbook missing: {RUNBOOK_PATH}"
    )


def test_runbook_is_non_empty() -> None:
    text = _runbook_text()
    # A meaningful runbook is at least a few KiB. Anything tiny
    # means the operator does not have enough material to refresh
    # the chain safely.
    assert len(text) > 4000, (
        f"N5b preflight runbook is too short ({len(text)} bytes); "
        f"the runbook must document the full dry-run refresh chain."
    )


def test_runbook_is_markdown() -> None:
    text = _runbook_text()
    assert text.lstrip().startswith("# "), (
        "runbook must be a markdown file beginning with a top-level "
        "heading."
    )


# ---------------------------------------------------------------------------
# Canonical CLI invocations (steps 1 → 5)
# ---------------------------------------------------------------------------

_REQUIRED_CLI_INVOCATIONS: tuple[str, ...] = (
    "python3 -m reporting.github_pr_lifecycle --mode dry-run",
    "python3 -m reporting.development_pr_lifecycle_observer",
    "python3 -m reporting.mobile_approval_inbox",
    "python3 -m reporting.development_merge_recommendation",
    "python3 -m reporting.development_merge_preflight",
)


def test_runbook_documents_every_required_cli_invocation() -> None:
    text = _runbook_text()
    for cmd in _REQUIRED_CLI_INVOCATIONS:
        assert cmd in text, (
            f"runbook must contain the canonical CLI invocation "
            f"verbatim: {cmd!r}"
        )


def test_runbook_documents_no_write_flag_on_preflight() -> None:
    """The preflight invocation must be shown with ``--no-write``
    at least once so the operator has a write-free smoke path."""
    text = _runbook_text()
    assert (
        "python3 -m reporting.development_merge_preflight --no-write"
        in text
        or "python -m reporting.development_merge_preflight --no-write"
        in text
    ), (
        "runbook must document the --no-write smoke path for the "
        "preflight projector."
    )


# ---------------------------------------------------------------------------
# Artefact paths must agree with the module constants
# ---------------------------------------------------------------------------


def _import_artifact_relative_paths() -> dict[str, str]:
    from reporting import (  # noqa: WPS433 — local import is intentional
        development_merge_preflight as n5b,
        development_merge_recommendation as a23,
        development_pr_lifecycle_observer as a22,
        mobile_approval_inbox as n3a,
    )

    return {
        "a22": a22.ARTIFACT_RELATIVE_PATH,
        "n3a": n3a.ARTIFACT_RELATIVE_PATH,
        "a23": a23.ARTIFACT_RELATIVE_PATH,
        "n5b": n5b.ARTIFACT_RELATIVE_PATH,
    }


def test_runbook_lists_every_artefact_relative_path() -> None:
    """The runbook must reference each upstream artefact by its
    canonical ``ARTIFACT_RELATIVE_PATH`` so path drift in the
    projector source fails this test before the runbook can
    silently disagree with the code."""
    paths = _import_artifact_relative_paths()
    text = _runbook_text()
    for label, rel in paths.items():
        assert rel in text, (
            f"runbook must reference the {label!r} artefact path "
            f"{rel!r} exactly."
        )


def test_runbook_references_upstream_github_pr_lifecycle_artefact() -> None:
    """Step 1 of the chain is the upstream-of-upstream gh digest.
    The runbook must call it out by its on-disk path so the
    operator knows where the network step writes."""
    text = _runbook_text()
    assert "logs/github_pr_lifecycle/latest.json" in text, (
        "runbook must reference the upstream gh-digest path "
        "logs/github_pr_lifecycle/latest.json."
    )


# ---------------------------------------------------------------------------
# Closed-vocab discipline invariants from the projector
# ---------------------------------------------------------------------------


def test_runbook_states_dry_run_only_invariant() -> None:
    text = _runbook_text()
    assert "dry_run_only" in text, (
        "runbook must restate the projector's dry_run_only invariant."
    )
    # ``dry_run_only`` and the literal ``true`` must appear in close
    # proximity at least once so the invariant is unambiguous.
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


# ---------------------------------------------------------------------------
# Closed verdict / stop-condition reminders
# ---------------------------------------------------------------------------


def test_runbook_documents_closed_dry_run_verdict_vocab() -> None:
    text = _runbook_text()
    for verdict in (
        "would_block",
        "would_require_operator",
        "would_be_live_candidate_if_authorized",
    ):
        assert verdict in text, (
            f"runbook must list the closed verdict {verdict!r} so "
            f"the operator can interpret the snapshot."
        )


def test_runbook_documents_informational_stop_conditions() -> None:
    """The projector emits these two informational stop conditions on
    every candidate row. The runbook must explain that so the
    operator does not interpret them as live blockers."""
    text = _runbook_text()
    for sc in ("token_required_for_live", "live_merge_not_implemented"):
        assert sc in text, (
            f"runbook must reference the informational stop "
            f"condition {sc!r}."
        )


# ---------------------------------------------------------------------------
# Negative pins — the runbook must NOT carry an authority escalation
# ---------------------------------------------------------------------------


def test_runbook_code_blocks_contain_no_real_merge_command() -> None:
    """The runbook's executable surface (its fenced code blocks)
    must contain no GitHub-mutation command. Narrative negative
    mentions in prose (``no ``--admin`` ...``) are legitimate and
    in fact required; they live outside the fenced blocks."""
    code = _runbook_code_blocks()
    forbidden_command_shapes = (
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
    for shape in forbidden_command_shapes:
        assert shape not in code, (
            f"runbook code block contains a forbidden "
            f"mutating-command shape: {shape!r}"
        )


def test_runbook_code_blocks_do_not_enable_a18b_runtime_writer() -> None:
    """A18b runtime writer activation is a separate operator-only
    step gated behind a separate operator-go. The runbook's
    executable surface must not contain an env-flag enable line
    for it."""
    code = _runbook_code_blocks()
    forbidden = (
        "ade_generated_lane_writer_enabled=true",
        'ade_generated_lane_writer_enabled="true"',
        "export ade_generated_lane_writer_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"runbook code block must NOT enable the A18b runtime "
            f"writer: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_enable_n5b_live_execute() -> None:
    """N5b Phase 4 live execute is permanently denied without a
    separate explicit operator-go. The runbook's executable
    surface must not contain an env-flag enable line."""
    code = _runbook_code_blocks()
    forbidden = (
        "ade_n5b_live_execute_enabled=true",
        'ade_n5b_live_execute_enabled="true"',
        "export ade_n5b_live_execute_enabled",
    )
    for phrase in forbidden:
        assert phrase not in code, (
            f"runbook code block must NOT enable N5b live execute: "
            f"{phrase!r}"
        )


def test_runbook_code_blocks_do_not_flip_step5_or_level6() -> None:
    """Imperative Step 5 / Level 6 flips would only ever appear as
    executable lines (env exports, assignments, set commands). The
    invariants block prints the literal lowercase strings (e.g.
    ``step5_implementation_allowed = false``) inside a fenced
    block, so we have to scan only for the *true*-shaped flips."""
    code = _runbook_code_blocks()
    forbidden_phrases = (
        "step5_implementation_allowed = true",
        'step5_implementation_allowed="true"',
        "step5_implementation_allowed=true",
        'step5_enabled_substage = "5.1"',
        'step5_enabled_substage = "5.2"',
        'step5_enabled_substage="5.1"',
        'step5_enabled_substage="5.2"',
        "level6_enabled = true",
        "level6_enabled=true",
    )
    for phrase in forbidden_phrases:
        assert phrase not in code, (
            f"runbook code block contains a forbidden "
            f"authority-escalation flip: {phrase!r}"
        )


def test_runbook_code_blocks_do_not_instruct_token_mint_or_verify() -> None:
    """Preflight is pre-token. The runbook's executable surface
    must not contain a token mint / verify invocation. Narrative
    mentions in the negative list (``does not mint an approval
    token``) are required and live outside fenced blocks."""
    code = _runbook_code_blocks()
    forbidden_phrases = (
        "approval_token_runtime.mint",
        "approval_token_runtime.verify",
        "mint_approval_token",
        "verify_approval_token",
        "--mint-token",
        "--verify-token",
    )
    for phrase in forbidden_phrases:
        assert phrase not in code, (
            f"runbook code block contains a forbidden token "
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
            f"runbook contains a forbidden no-touch-path / "
            f"safety-bypass imperative: {phrase!r}"
        )


def test_runbook_does_not_instruct_deploy() -> None:
    text = _runbook_text().lower()
    forbidden_phrases = (
        "trigger the deploy workflow",
        "trigger deploy workflow",
        "force the deploy",
        "run the deploy",
        "dispatch the deploy",
        "couple this to deploy",
    )
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"runbook contains a forbidden deploy-coupling "
            f"instruction: {phrase!r}"
        )


# ---------------------------------------------------------------------------
# Negative pins — the runbook must NOT embed secret material
# ---------------------------------------------------------------------------


def test_runbook_contains_no_pem_secret_block() -> None:
    """Defense-in-depth: the runbook must not contain a real PEM
    secret block. The PEM markers below are assembled at runtime
    so the test source itself does not embed a literal PEM header
    (which would otherwise trip gitleaks' ``private-key`` rule on
    the test file)."""
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
    documents read-only projector commands and has no business
    quoting an HMAC secret."""
    text = _runbook_text()
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"runbook embeds a hex-64 literal that looks like a "
        f"secret: {matches!r}"
    )


def test_runbook_contains_no_bearer_token_header() -> None:
    """No literal ``Authorization: Bearer <token>`` line — the
    refresh chain is unauthenticated stdlib projection."""
    text = _runbook_text().lower()
    forbidden_patterns = (
        "authorization: bearer ",
        "x-api-key: ",
        "ghp_",
        "github_pat_",
        "sk-ant-",
    )
    for pat in forbidden_patterns:
        assert pat not in text, (
            f"runbook contains a credential-shaped string: {pat!r}"
        )


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants must be stated in a single explicit block
# ---------------------------------------------------------------------------


def test_runbook_contains_combined_invariants_block() -> None:
    """The runbook must somewhere state the six core invariants in
    a single close block so the operator can read them together
    without ambiguity. We require all six lowercased substrings
    to appear within the same 1200-character window."""
    text = _runbook_text().lower()
    needles = (
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
    )
    # Find the earliest window in which all six needles co-occur.
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
# Cross-reference pins — the runbook must link back to the doctrine
# ---------------------------------------------------------------------------


def test_runbook_cross_references_n5b_plan_doc() -> None:
    text = _runbook_text()
    assert "n5b_merge_execution_plan.md" in text, (
        "runbook must cross-reference the N5b plan / governance doc."
    )


def test_runbook_cross_references_adr_015() -> None:
    text = _runbook_text()
    assert "ADR-015" in text, (
        "runbook must cross-reference ADR-015 (Level 6 "
        "permanently-disabled doctrine)."
    )


def test_runbook_cross_references_recurring_maintenance() -> None:
    text = _runbook_text()
    assert "recurring_maintenance" in text, (
        "runbook must mention recurring_maintenance so the operator "
        "knows which subsystem (does NOT yet) schedule the "
        "downstream chain."
    )
