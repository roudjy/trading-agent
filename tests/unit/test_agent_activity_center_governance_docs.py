"""Structural pin tests for the Agent Activity Center governance docs (B2.0).

B2.0 of Revised Batch 2 ships five governance docs + one
canonical-roadmap entry. These tests pin that the five docs
exist on disk and carry the load-bearing doctrinal literals. The
intent is that any future PR which accidentally deletes or
weakens one of these docs fails CI before merging.

These tests are stdlib-only (``pathlib`` + ``re``). They do not
import any module under ``reporting/``, ``dashboard/``,
``frontend/``, ``automation/``, ``agent/``, ``broker/``,
``research/``. They do not write to ``seed.jsonl`` /
``generated_seed.jsonl`` / ``delegation_seed.jsonl``. They do
not call ``gh`` / ``git`` / ``subprocess`` / network.

The companion design doc is
``docs/governance/agent_activity_center_design.md``. The
canonical-roadmap anchor is ``docs/roadmap/autonomous_development.txt``
section A15.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DOCS_GOV: Path = REPO_ROOT / "docs" / "governance"
ROADMAP_PATH: Path = (
    REPO_ROOT / "docs" / "roadmap" / "autonomous_development.txt"
)


# ---------------------------------------------------------------------------
# File-existence pins (one per doc)
# ---------------------------------------------------------------------------


def _read_text(p: Path) -> str:
    assert p.is_file(), f"required AAC governance doc missing: {p}"
    return p.read_text(encoding="utf-8")


def test_design_doc_exists() -> None:
    assert (DOCS_GOV / "agent_activity_center_design.md").is_file()


def test_aggregator_schema_doc_exists() -> None:
    assert (
        DOCS_GOV / "agent_activity_center_aggregator_schema.md"
    ).is_file()


def test_api_contract_doc_exists() -> None:
    assert (DOCS_GOV / "agent_activity_center_api_contract.md").is_file()


def test_no_mutation_doctrine_doc_exists() -> None:
    assert (
        DOCS_GOV / "agent_activity_center_no_mutation_doctrine.md"
    ).is_file()


def test_push_notification_safety_doc_exists() -> None:
    assert (
        DOCS_GOV / "agent_activity_center_push_notification_safety.md"
    ).is_file()


# ---------------------------------------------------------------------------
# Design doc — load-bearing literals
# ---------------------------------------------------------------------------


def test_design_doc_states_read_only_by_construction() -> None:
    src = _read_text(DOCS_GOV / "agent_activity_center_design.md")
    assert "Read-only by construction" in src, (
        "design doc must declare the read-only-by-construction "
        "principle in §2"
    )


def test_design_doc_lists_eight_screens() -> None:
    src = _read_text(DOCS_GOV / "agent_activity_center_design.md")
    expected = [
        "Today",
        "Approval Inbox",
        "Pipeline Board",
        "WorkItem Trace",
        "Agents",
        "Artefact Explorer",
        "System Safety",
        "Design Spec",
    ]
    for screen in expected:
        assert screen in src, (
            f"design doc must list the screen {screen!r} in §3.4"
        )


def test_design_doc_lists_three_concepts() -> None:
    src = _read_text(DOCS_GOV / "agent_activity_center_design.md")
    for concept in ("WorkItem", "AgentEvent", "HumanAction"):
        assert concept in src, (
            f"design doc must define the concept {concept!r} in §3"
        )


def test_design_doc_pins_no_autonomous_execution() -> None:
    src = _read_text(DOCS_GOV / "agent_activity_center_design.md")
    assert "No autonomous execution" in src, (
        "design doc §17 non-goals must include the "
        '"No autonomous execution" literal'
    )


def test_design_doc_pins_level_6_permanently_disabled() -> None:
    src = _read_text(DOCS_GOV / "agent_activity_center_design.md")
    # Look for both halves of the doctrine reference in the design doc.
    assert "Level 6" in src, (
        "design doc must reference Level 6"
    )
    assert "permanently disabled" in src.lower(), (
        "design doc must state Level 6 is permanently disabled"
    )
    assert "ADR-015" in src, (
        "design doc must cross-reference ADR-015 for the "
        "Level 6 doctrine"
    )


# ---------------------------------------------------------------------------
# Aggregator schema doc — load-bearing literals
# ---------------------------------------------------------------------------


def test_aggregator_schema_pins_artefact_path() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_aggregator_schema.md"
    )
    assert (
        "logs/development_agent_activity_timeline/latest.json" in src
    ), (
        "aggregator schema must pin the canonical artefact path "
        "logs/development_agent_activity_timeline/latest.json"
    )


def test_aggregator_schema_pins_read_only_invariant() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_aggregator_schema.md"
    )
    # The schema must explicitly forbid writes to all three seed
    # JSONL paths.
    for path in (
        "seed.jsonl",
        "generated_seed.jsonl",
        "delegation_seed.jsonl",
    ):
        assert path in src, (
            f"aggregator schema must reference {path!r} (in a "
            f'"never writes to" context)'
        )
    # And the literal "never writes" pin must be present.
    assert (
        "Never writes to seed files" in src
        or "never writes to seed files" in src
        or "never writes" in src.lower()
    ), (
        "aggregator schema must state the aggregator never writes "
        "to seed JSONL files"
    )


# ---------------------------------------------------------------------------
# API contract doc — load-bearing literals
# ---------------------------------------------------------------------------


def test_api_contract_lists_six_get_endpoints() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_api_contract.md"
    )
    expected_endpoints = (
        "/api/agent-control/activity/today",
        "/api/agent-control/activity/items",
        "/api/agent-control/activity/items/<item_id>",
        "/api/agent-control/activity/agents",
        "/api/agent-control/activity/artifacts",
        "/api/agent-control/activity/invariants",
    )
    for endpoint in expected_endpoints:
        assert endpoint in src, (
            f"API contract must list the endpoint {endpoint!r}"
        )


def test_api_contract_pins_no_post_put_patch_delete() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_api_contract.md"
    )
    # The doctrine must explicitly close the verb set.
    assert "No mutation endpoint" in src, (
        "API contract must contain the no-mutation-endpoint pin"
    )
    # And the four forbidden verbs must each be referenced (as
    # "no" entries in the closed-verb table).
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert verb in src, (
            f"API contract must reference {verb!r} (in a "
            f'"forbidden" context)'
        )


# ---------------------------------------------------------------------------
# No-mutation doctrine doc — load-bearing literals
# ---------------------------------------------------------------------------


def test_no_mutation_doctrine_forbids_post_route_methods() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_no_mutation_doctrine.md"
    )
    # The doctrine must reject the Flask methods=[...] pattern with
    # each non-GET verb literal.
    for token in (
        'methods=["POST"',
        'methods=["PUT"',
        'methods=["PATCH"',
        'methods=["DELETE"',
    ):
        assert token in src, (
            f"no-mutation doctrine must forbid the literal {token!r}"
        )
    assert "/api/agent-control/" in src, (
        "no-mutation doctrine must scope the forbidden routes to "
        "the /api/agent-control/ prefix"
    )


def test_no_mutation_doctrine_pins_clipboard_only_copy_button() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_no_mutation_doctrine.md"
    )
    assert "CopyOperatorPhraseButton" in src, (
        "no-mutation doctrine must pin the clipboard-only "
        "CopyOperatorPhraseButton component"
    )
    assert "navigator.clipboard.writeText" in src, (
        "no-mutation doctrine must require navigator.clipboard."
        "writeText for the copy-phrase component"
    )


# ---------------------------------------------------------------------------
# Push-notification safety doc — load-bearing literals
# ---------------------------------------------------------------------------


def test_push_notification_safety_forbids_required_phrase_in_body() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_push_notification_safety.md"
    )
    assert "required_phrase" in src, (
        "push-notification safety doc must reference the "
        "required_phrase field"
    )
    # The doctrine sentence must explicitly forbid required_phrase
    # from appearing in push bodies.
    assert (
        "never contain `required_phrase`" in src
        or "never contain required_phrase" in src
        or "must NEVER include" in src
    ), (
        "push-notification safety doc must explicitly forbid "
        "required_phrase from push notification bodies"
    )


def test_push_notification_safety_canonical_body_shape_present() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_push_notification_safety.md"
    )
    # The canonical example body is "1 new item needs your review …".
    assert (
        "1 new item needs your review" in src
    ), (
        "push-notification safety doc must include the canonical "
        'body example "1 new item needs your review …"'
    )


def test_push_notification_safety_forbids_secret_tokens_in_body() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_push_notification_safety.md"
    )
    # Each forbidden token category must be enumerated.
    for token in (
        "api_key",
        "secret",
        "token",
        "bearer",
        "password",
    ):
        assert token in src, (
            f"push-notification safety doc must forbid {token!r} "
            "in push bodies"
        )


def test_push_notification_safety_tap_is_read_only() -> None:
    src = _read_text(
        DOCS_GOV / "agent_activity_center_push_notification_safety.md"
    )
    assert (
        "Notification tap" in src
        or "notification tap" in src
        or "tap" in src
    )
    assert (
        "never approves" in src.lower()
        or "no tap approves" in src.lower()
    ), (
        "push-notification safety doc must pin that notification "
        "taps never approve"
    )


# ---------------------------------------------------------------------------
# Canonical roadmap §A15 entry — load-bearing literals
# ---------------------------------------------------------------------------


def test_roadmap_a15_entry_present() -> None:
    src = _read_text(ROADMAP_PATH)
    assert (
        "# A15 — Agent Activity Center" in src
    ), (
        "canonical roadmap must contain the §A15 header for the "
        "Agent Activity Center"
    )


def test_roadmap_a15_status_phrasing() -> None:
    """The status line must use the operator-required wording:
    'Proposed until this PR is merged; accepted by the merge commit.'
    """
    src = _read_text(ROADMAP_PATH)
    assert (
        "Proposed until this PR is merged; accepted by the merge commit"
        in src
    ), (
        "§A15 status line must use the operator-required wording "
        '"Proposed until this PR is merged; accepted by the merge '
        'commit."'
    )


def test_roadmap_a15_preserves_step5_invariants() -> None:
    src = _read_text(ROADMAP_PATH)
    # The A15 section must re-assert both Step 5 invariants.
    # Use a single regex to scope to the A15 section + its body
    # (terminated by the next "\n\\---\n" or EOF).
    m = re.search(
        r"# A15 — Agent Activity Center.*?(?=\n\\---\n|\Z)",
        src,
        flags=re.DOTALL,
    )
    assert m is not None, "§A15 section not found in roadmap"
    a15 = m.group(0)
    assert "step5_implementation_allowed = False" in a15, (
        "§A15 must re-assert step5_implementation_allowed = False"
    )
    assert 'STEP5_ENABLED_SUBSTAGE = "none"' in a15, (
        '§A15 must re-assert STEP5_ENABLED_SUBSTAGE = "none"'
    )
    assert "Level 6" in a15 and "permanently disabled" in a15.lower(), (
        "§A15 must re-assert that Level 6 is permanently disabled"
    )


def test_roadmap_a15_lists_future_units() -> None:
    src = _read_text(ROADMAP_PATH)
    m = re.search(
        r"# A15 — Agent Activity Center.*?(?=\n\\---\n|\Z)",
        src,
        flags=re.DOTALL,
    )
    assert m is not None
    a15 = m.group(0)
    for unit in ("B2.0b", "B2.0c", "B2.0d", "B2.0e"):
        assert unit in a15, (
            f"§A15 must enumerate the future implementation unit "
            f"{unit!r} (out of A15 scope)"
        )


def test_roadmap_a15_scope_excludes_runtime_code() -> None:
    src = _read_text(ROADMAP_PATH)
    m = re.search(
        r"# A15 — Agent Activity Center.*?(?=\n\\---\n|\Z)",
        src,
        flags=re.DOTALL,
    )
    assert m is not None
    a15 = m.group(0)
    # The scope-NOT-allowed block must enumerate the no-runtime
    # discipline.
    assert "No module under reporting/" in a15, (
        "§A15 scope-not-allowed must exclude new modules under "
        "reporting/"
    )
    assert "No Flask blueprint" in a15, (
        "§A15 scope-not-allowed must exclude Flask blueprint code"
    )
    assert "No PWA frontend code" in a15, (
        "§A15 scope-not-allowed must exclude PWA frontend code"
    )
    assert "No recurring-maintenance entry" in a15, (
        "§A15 scope-not-allowed must exclude recurring-maintenance "
        "entries"
    )
