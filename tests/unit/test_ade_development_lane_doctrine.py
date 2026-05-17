"""Structural pin tests for the ADE Development-Lane Doctrine doc (A16).

A16 ships a single subordinate doctrine doc plus this structural
pin test plus a canonical-roadmap anchor entry. These tests pin
that the doctrine doc exists on disk and carries the load-bearing
authority-distinction literals. The intent is that any future PR
which accidentally deletes or weakens the doctrine fails CI before
merging.

These tests are stdlib-only (``pathlib``). They do not import any
module under ``reporting/``, ``dashboard/``, ``frontend/``,
``automation/``, ``agent/``, ``broker/``, ``research/``. They do
not write to ``seed.jsonl`` / ``generated_seed.jsonl`` /
``delegation_seed.jsonl``. They do not call ``gh`` / ``git`` /
``subprocess`` / network.

Companion doc: ``docs/governance/ade_development_lane_doctrine.md``.
Canonical-roadmap anchor: ``docs/roadmap/autonomous_development.txt``
section A16.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DOCTRINE_PATH: Path = (
    REPO_ROOT / "docs" / "governance" / "ade_development_lane_doctrine.md"
)
ROADMAP_PATH: Path = (
    REPO_ROOT / "docs" / "roadmap" / "autonomous_development.txt"
)


def _read(p: Path) -> str:
    assert p.is_file(), f"required file missing: {p}"
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# File-existence pin
# ---------------------------------------------------------------------------


def test_doctrine_doc_exists() -> None:
    assert DOCTRINE_PATH.is_file(), (
        "ADE Development-Lane Doctrine doc must exist at "
        f"{DOCTRINE_PATH.relative_to(REPO_ROOT)}"
    )


# ---------------------------------------------------------------------------
# Authority-distinction literals (load-bearing)
# ---------------------------------------------------------------------------


def test_doctrine_doc_says_ade_is_development_workflow_automation_only() -> None:
    src = _read(DOCTRINE_PATH)
    assert (
        "ADE authority = development workflow automation only" in src
    ), "doctrine doc must pin ADE = development workflow automation only"


def test_doctrine_doc_says_qre_runtime_authority_is_separate() -> None:
    src = _read(DOCTRINE_PATH)
    assert "QRE runtime authority is separate" in src, (
        "doctrine doc must pin that QRE runtime authority is separate "
        "from ADE authority"
    )


def test_doctrine_doc_says_trading_execution_authority_permanently_outside_ade() -> None:
    src = _read(DOCTRINE_PATH)
    assert (
        "Trading execution authority is permanently outside ADE authority"
        in src
    ), (
        "doctrine doc must pin that trading execution authority is "
        "permanently outside ADE authority"
    )


def test_doctrine_doc_says_paper_shadow_are_future_qre_product_capabilities() -> None:
    src = _read(DOCTRINE_PATH)
    assert (
        "Paper/shadow are future QRE product capabilities, not ADE "
        "execution permission" in src
    ), (
        "doctrine doc must pin the paper/shadow framing: future QRE "
        "product capabilities, not ADE execution permission"
    )


def test_doctrine_doc_says_ade_must_never_place_enable_authorize_or_trigger_live_trades() -> None:
    src = _read(DOCTRINE_PATH)
    assert (
        "ADE must never place, enable, authorize, or trigger live trades"
        in src
    ), (
        "doctrine doc must pin the permanent live-trading denial "
        "(place / enable / authorize / trigger)"
    )


# ---------------------------------------------------------------------------
# ADE may / may-not pins
# ---------------------------------------------------------------------------


def test_doctrine_doc_pins_ade_does_not_run_strategies() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADE does not run strategies" in src


def test_doctrine_doc_pins_ade_does_not_place_orders() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADE does not place orders" in src


def test_doctrine_doc_pins_ade_does_not_allocate_capital() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADE does not allocate capital" in src


def test_doctrine_doc_pins_ade_does_not_activate_paper_shadow_live_runtime() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADE does not activate paper/shadow/live runtime" in src


def test_doctrine_doc_pins_ade_does_not_receive_trading_authority() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADE does not receive trading authority" in src


def test_doctrine_doc_pins_default_disabled_operator_gated_audited() -> None:
    src = _read(DOCTRINE_PATH)
    for literal in (
        "default-disabled",
        "operator-gated",
        "audited",
    ):
        assert literal in src, (
            f"doctrine doc must pin paper/shadow code development as "
            f"{literal!r}"
        )


# ---------------------------------------------------------------------------
# Step 5 + Level 6 pins
# ---------------------------------------------------------------------------


def test_doctrine_doc_pins_step5_runtime_blocked() -> None:
    src = _read(DOCTRINE_PATH)
    assert "Step 5 runtime remains blocked" in src, (
        "doctrine doc must pin Step 5 runtime as remaining blocked"
    )


def test_doctrine_doc_pins_level_6_permanently_disabled() -> None:
    src = _read(DOCTRINE_PATH)
    assert "Level 6 remains permanently disabled" in src, (
        "doctrine doc must pin Level 6 as remaining permanently disabled"
    )


# ---------------------------------------------------------------------------
# N5b simulator cap + Phase 4 denial pins
# ---------------------------------------------------------------------------


def test_doctrine_doc_pins_n5b_phase3_simulator_max_merge_like_surface() -> None:
    src = _read(DOCTRINE_PATH)
    assert (
        "N5b Phase 3 recorded-fixture simulator remains the maximum "
        "allowed merge-like ADE surface" in src
    )


def test_doctrine_doc_pins_n5b_phase4_permanently_denied_for_ade() -> None:
    src = _read(DOCTRINE_PATH)
    assert "N5b Phase 4 production merge remains permanently denied for ADE" in src


# ---------------------------------------------------------------------------
# Hard-invariant pins
# ---------------------------------------------------------------------------


def test_doctrine_doc_pins_no_admin_no_force_push_no_direct_main_no_hook_bypass() -> None:
    src = _read(DOCTRINE_PATH)
    for literal in (
        "No `--admin`",
        "No force push",
        "No direct main push",
        "No hook bypass",
    ):
        assert literal in src, (
            f"doctrine doc must reaffirm the hard invariant {literal!r}"
        )


# ---------------------------------------------------------------------------
# Canonical references
# ---------------------------------------------------------------------------


def test_doctrine_doc_references_adr_015() -> None:
    src = _read(DOCTRINE_PATH)
    assert "ADR-015-claude-agent-governance.md" in src, (
        "doctrine doc must cross-reference ADR-015"
    )


def test_doctrine_doc_references_execution_authority() -> None:
    src = _read(DOCTRINE_PATH)
    assert "execution_authority.md" in src, (
        "doctrine doc must cross-reference execution_authority.md"
    )


def test_doctrine_doc_references_no_touch_paths() -> None:
    src = _read(DOCTRINE_PATH)
    assert "no_touch_paths.md" in src


def test_doctrine_doc_references_autonomy_ladder() -> None:
    src = _read(DOCTRINE_PATH)
    assert "autonomy_ladder.md" in src


def test_doctrine_doc_references_step5_design() -> None:
    src = _read(DOCTRINE_PATH)
    assert "step5_design.md" in src


# ---------------------------------------------------------------------------
# Canonical-roadmap anchor pin (A16)
# ---------------------------------------------------------------------------


def test_roadmap_contains_a16_anchor_entry() -> None:
    src = _read(ROADMAP_PATH)
    assert "# A16 — ADE Development-Lane Doctrine" in src, (
        "canonical roadmap must contain the A16 anchor entry"
    )


def test_roadmap_a16_entry_cites_doctrine_doc() -> None:
    src = _read(ROADMAP_PATH)
    assert "ade_development_lane_doctrine.md" in src, (
        "A16 entry must cite the doctrine doc by filename"
    )


# ---------------------------------------------------------------------------
# Forbidden-token absence in the doctrine doc
# ---------------------------------------------------------------------------


def test_doctrine_doc_does_not_grant_ade_trading_authority() -> None:
    src = _read(DOCTRINE_PATH)
    forbidden = (
        "ADE may live trade",
        "ADE may place orders",
        "ADE may allocate capital",
        "ADE may activate paper",
        "ADE may activate shadow",
        "ADE may activate live",
        "step5_implementation_allowed = True",
        "step5_implementation_allowed=True",
        "Level 6 enabled",
        "Level 6 unlocked",
    )
    for token in forbidden:
        assert token not in src, (
            f"doctrine doc must not contain forbidden authority-grant "
            f"token {token!r}"
        )
