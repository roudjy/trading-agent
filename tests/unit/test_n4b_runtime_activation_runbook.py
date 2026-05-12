"""Pin-tests for the N4b runtime activation operator runbook.

These tests do **not** activate the runtime gate. They pin that the
operator runbook at ``docs/governance/n4b_runtime_activation.md``:

* exists;
* documents the canonical safe activation steps the operator must
  perform on the VPS;
* contains the closed-vocab assertions the operator must observe
  (``is_configured``, ``replay_detected``, ``binding_mismatch``);
* states the Step 5 + Level 6 invariants explicitly so the runbook
  cannot drift away from the doctrine;
* contains a rollback step;
* does NOT embed a live secret value, env file fragment, or any
  decision-verb call pattern (``approve_(`` / ``reject_(`` /
  ``merge_(`` / ``deploy_(``);
* does NOT instruct the operator to disable any safety control
  (e.g. unset Step 5 flags, edit ``.gitleaks.toml``, touch
  ``.claude/**``).

This is a documentation pin-test, not a runtime gate. Phase B
(actually exporting ``ADE_APPROVAL_TOKEN_HMAC_SECRET`` on the VPS)
is operator-only and is NEVER performed by this test or any other
code path in the repo.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = (
    REPO_ROOT / "docs" / "governance" / "n4b_runtime_activation.md"
)


def _runbook_text() -> str:
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Existence
# ---------------------------------------------------------------------------


def test_runbook_file_exists() -> None:
    assert RUNBOOK_PATH.is_file(), (
        f"N4b runtime activation runbook missing: {RUNBOOK_PATH}"
    )


def test_runbook_is_non_empty() -> None:
    text = _runbook_text()
    # A meaningful runbook is at least a few KiB. Anything tiny means
    # the operator does not have enough material to act safely.
    assert len(text) > 2000, (
        f"N4b runbook is too short ({len(text)} bytes); "
        f"the runbook must document the full Phase B activation."
    )


# ---------------------------------------------------------------------------
# Canonical phrases the operator must observe
# ---------------------------------------------------------------------------


def test_runbook_documents_is_configured_check() -> None:
    """The operator must verify ``is_configured: true`` after export."""
    text = _runbook_text()
    assert "is_configured" in text, (
        "runbook must instruct the operator to verify "
        "'is_configured' before issuing a mint."
    )


def test_runbook_documents_replay_detected_outcome() -> None:
    """The operator must run a replay test that returns
    ``replay_detected``."""
    text = _runbook_text()
    assert "replay_detected" in text, (
        "runbook must instruct the operator to confirm "
        "replay protection via 'replay_detected'."
    )


def test_runbook_documents_binding_mismatch_outcome() -> None:
    """The operator must run a binding-drift test that returns
    ``binding_mismatch``."""
    text = _runbook_text()
    assert "binding_mismatch" in text, (
        "runbook must instruct the operator to confirm "
        "binding drift detection via 'binding_mismatch'."
    )


def test_runbook_documents_configuration_missing_envelope() -> None:
    text = _runbook_text()
    assert "configuration_missing" in text, (
        "runbook must mention the 'configuration_missing' envelope "
        "so the operator can recognise the unactivated state."
    )


def test_runbook_warns_verify_is_claim_only() -> None:
    """The operator must understand that verify performs NO underlying
    action. The runbook makes that explicit."""
    text = _runbook_text().lower()
    assert "claim verification only" in text or "claim-only" in text or (
        "no underlying action" in text
    ), (
        "runbook must state explicitly that verify is claim "
        "verification only and performs no underlying action."
    )


def test_runbook_documents_secret_generation_command() -> None:
    text = _runbook_text()
    assert "openssl rand -hex 32" in text, (
        "runbook must include the canonical secret-generation "
        "command 'openssl rand -hex 32'."
    )


def test_runbook_documents_rollback_step() -> None:
    text = _runbook_text().lower()
    # A rollback step exists and instructs the operator how to revert.
    assert "rollback" in text, "runbook must contain a rollback section."
    # The rollback path involves restarting the dashboard container.
    assert "force-recreate" in text or "docker compose up" in text, (
        "rollback step must show the container restart command."
    )


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants must be stated
# ---------------------------------------------------------------------------


def test_runbook_states_step5_implementation_allowed_false() -> None:
    text = _runbook_text()
    assert "step5_implementation_allowed" in text, (
        "runbook must reaffirm step5_implementation_allowed = false."
    )
    # The literal "false" must appear nearby (within 200 chars of the
    # first mention) to make the invariant explicit.
    idx = text.find("step5_implementation_allowed")
    nearby = text[idx : idx + 200].lower()
    assert "false" in nearby, (
        "step5_implementation_allowed must be stated as `false` "
        "explicitly in the runbook."
    )


def test_runbook_states_step5_enabled_substage_none() -> None:
    text = _runbook_text()
    assert "STEP5_ENABLED_SUBSTAGE" in text or "step5_enabled_substage" in text, (
        "runbook must reaffirm STEP5_ENABLED_SUBSTAGE invariant."
    )
    assert '"none"' in text or " none" in text.lower(), (
        "STEP5_ENABLED_SUBSTAGE must be stated as 'none'."
    )


def test_runbook_states_level_6_permanently_disabled() -> None:
    text = _runbook_text().lower()
    assert "level 6" in text, "runbook must reaffirm Level 6 doctrine."
    assert "permanently disabled" in text or "disabled" in text, (
        "runbook must state Level 6 remains disabled."
    )


# ---------------------------------------------------------------------------
# Negative pins — the runbook must NOT carry a secret or escalate authority
# ---------------------------------------------------------------------------


def test_runbook_contains_no_pem_secret_block() -> None:
    """Defense-in-depth: the runbook must not contain a real PEM
    secret block.  The runbook *may* mention the bare phrase
    ``BEGIN PRIVATE KEY`` because the operator is instructed to grep
    log output for it as a guardrail (= negative pattern); the
    forbidden shape here is the full PEM block with the canonical
    five-dash delimiters.

    The PEM markers below are assembled from runtime parts so the
    test file itself does not embed a literal PEM header — that
    would trip gitleaks' ``private-key`` rule on the test source.
    """
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


def test_runbook_contains_no_literal_hex_secret() -> None:
    """Defense-in-depth: a 64-character hex run inside backticks would
    look like a copy-pasted ``openssl rand -hex 32`` output. The runbook
    must show the command, not a sample value."""
    text = _runbook_text()
    # Inline-code 64-hex blocks (the canonical secret length).
    pattern = re.compile(r"`[0-9a-fA-F]{64}`")
    matches = pattern.findall(text)
    assert not matches, (
        f"runbook embeds a hex-64 literal that looks like a secret: "
        f"{matches!r}"
    )


def test_runbook_does_not_instruct_disabling_step5_or_level6() -> None:
    """Negative pin — the runbook must never tell the operator to flip
    a Step 5 flag or Level 6 ceiling."""
    text = _runbook_text().lower()
    forbidden_phrases = [
        "set step5_implementation_allowed to true",
        "step5_implementation_allowed = true",
        'step5_enabled_substage = "5.1"',
        'step5_enabled_substage = "5.2"',
        "enable level 6",
        "disable replay protection",
        "skip replay",
        "skip binding check",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in text, (
            f"runbook contains a forbidden authority-escalation phrase: "
            f"{phrase!r}"
        )


def test_runbook_does_not_instruct_touching_no_touch_paths() -> None:
    """The runbook must not instruct the operator to *edit* no-touch
    governance surfaces. Negative mentions (an authority-chain row
    saying ``.claude / .gitleaks.toml | forbidden | unchanged``) are
    fine and in fact required; the imperative *edit / modify / add /
    write to* shapes are what would be dangerous."""
    text = _runbook_text().lower()
    forbidden_imperatives = [
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
        "edit generated_seed.jsonl",
        "modify generated_seed.jsonl",
        "write to generated_seed.jsonl",
        "edit delegation_seed.jsonl",
        "modify delegation_seed.jsonl",
        "write to delegation_seed.jsonl",
    ]
    for phrase in forbidden_imperatives:
        assert phrase not in text, (
            f"runbook contains a forbidden imperative-edit phrase: "
            f"{phrase!r}"
        )


def test_runbook_contains_no_decision_verb_call_pattern() -> None:
    """The closed N4b doctrine forbids any call-shaped decision verb
    (``approve_(``, ``reject_(``, ``merge_(``, ``deploy_(``). The
    runbook must not introduce one either."""
    text = _runbook_text().lower()
    forbidden_call_shapes = [
        "approve_(",
        "reject_(",
        "merge_(",
        "deploy_(",
        "execute_merge(",
        "execute_approve(",
    ]
    for shape in forbidden_call_shapes:
        assert shape not in text, (
            f"runbook contains a forbidden decision-verb call shape: "
            f"{shape!r}"
        )


# ---------------------------------------------------------------------------
# Operational guarantees — the runbook tells the operator to verify
# audit-clean state after the smoke test
# ---------------------------------------------------------------------------


def test_runbook_documents_audit_checklist() -> None:
    """After the smoke test the operator must confirm no merge / push
    / inbox-row mutation happened. The runbook makes this explicit."""
    text = _runbook_text().lower()
    # We assert the runbook references each of these audit lines so a
    # future doc-edit cannot silently drop one of them.
    audit_phrases = [
        "approval_token_seen_nonces",
        "git status",
        "seed.jsonl",
        "no new row",
    ]
    for phrase in audit_phrases:
        assert phrase in text, (
            f"runbook missing audit-checklist phrase: {phrase!r}"
        )


def test_runbook_points_at_existing_pin_tests() -> None:
    """The runbook closes the loop by pointing at the existing N4b /
    N4a pin-tests so the operator can confirm the implementation
    matches the doctrine."""
    text = _runbook_text()
    refs = [
        "tests/unit/test_api_approval_token_gate.py",
        "tests/unit/test_approval_token_runtime.py",
        "tests/unit/test_approval_token_gate.py",
    ]
    for ref in refs:
        assert ref in text, (
            f"runbook must reference the pin-test file: {ref}"
        )
