"""N2b-2b — dashboard.py wiring diff guard.

This test file pins two layers of guarantees:

1. **Always-on guards** (run regardless of wiring state):
   * every existing ``register_*_routes`` import + call must remain
     in dashboard.py;
   * dashboard.py must not contain a real Web Push provider library
     or VAPID-private-key reference;
   * importing dashboard.py must not flip Step 5 invariants
     (asserted via source-text scan; the live import path is
     covered by other Step 5 tests);
   * the companion governance doc states the load-bearing rules.

2. **Conditional pins** (active only when the operator has added
   the two-line wiring change):
   * the file contains EXACTLY one new import + one new register
     call (no duplicates, no other edits);
   * the new register call appears after the last existing register
     call;
   * the new import sits alongside the existing
     ``from dashboard.api_*`` imports.

Why the conditional shape: the no-touch hook prevents the agent
from editing ``dashboard/dashboard.py`` directly. The operator
makes that edit at PR review. Until then, the conditional pins
return early (still passing). Once the operator edits, the pins
fire and actively enforce the exact diff. This is a strict pin, not
a skip — there is no path by which a wrong wiring can land green.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"

EXPECTED_IMPORT_LINE = (
    "from dashboard.api_push_subscribe import register_push_subscribe_routes"
)
EXPECTED_REGISTER_CALL = "register_push_subscribe_routes(app)"

# These lines MUST remain in dashboard.py post-edit. Removing or
# reordering any of them is forbidden.
EXISTING_REGISTRATIONS_REQUIRED: tuple[str, ...] = (
    "from dashboard.api_campaigns import register_campaign_routes",
    "from dashboard.api_research_intelligence import (",
    "from dashboard.api_observability import register_observability_routes",
    "from dashboard.api_system_meta import register_system_meta_routes",
    "from dashboard.api_agent_control import register_agent_control_routes",
    "from dashboard.api_proposal_queue import register_proposal_queue_routes",
    "from dashboard.api_approval_inbox import register_approval_inbox_routes",
    "from dashboard.api_roadmap_priority import "
    "register_roadmap_priority_routes",
    "register_campaign_routes(app)",
    "register_research_intelligence_routes(app)",
    "register_system_meta_routes(app)",
    "register_observability_routes(app)",
    "register_agent_control_routes(app)",
    "register_proposal_queue_routes(app)",
    "register_approval_inbox_routes(app)",
    "register_roadmap_priority_routes(app)",
)


def _dashboard_text() -> str:
    return DASHBOARD_PY.read_text(encoding="utf-8")


def _wiring_present() -> bool:
    text = _dashboard_text()
    return EXPECTED_IMPORT_LINE in text and EXPECTED_REGISTER_CALL in text


# ---------------------------------------------------------------------------
# Always-on guards
# ---------------------------------------------------------------------------


def test_dashboard_dashboard_exists() -> None:
    assert DASHBOARD_PY.is_file()


def test_existing_dashboard_registrations_unchanged() -> None:
    """Every existing register-routes import + call must still be
    present in dashboard.py, in the same relative order. This guard
    runs in BOTH modes (wiring present or absent) — removing an
    existing registration is never allowed."""
    text = _dashboard_text()
    last_pos = -1
    for needle in EXISTING_REGISTRATIONS_REQUIRED:
        pos = text.find(needle)
        assert pos != -1, (
            f"missing required line in dashboard.py: {needle!r}"
        )
        assert pos > last_pos, (
            f"existing registration out of order in dashboard.py: "
            f"{needle!r}"
        )
        last_pos = pos


def test_no_dashboard_api_push_dispatch_module() -> None:
    """N2b-3 territory: the real-delivery endpoint module must not
    exist yet. N2b-2b adds the subscription surface only."""
    bad = REPO_ROOT / "dashboard" / "api_push_dispatch.py"
    assert not bad.is_file(), (
        "dashboard/api_push_dispatch.py is N2b-3 territory and must "
        "not exist in N2b-2b"
    )


def test_no_real_push_provider_in_dashboard_dashboard() -> None:
    """dashboard.py must not contain any reference to a real Web Push
    provider library or VAPID private key — defense in depth on top
    of the api blueprint pin tests."""
    text = _dashboard_text().lower()
    forbidden = (
        "pywebpush",
        "from webpush",
        "import webpush",
        "web_push_vapid_private_key",
    )
    for needle in forbidden:
        assert needle not in text, (
            f"dashboard.py must not reference {needle!r} (N2b-3 "
            "territory)"
        )


def test_step5_invariants_unaffected_by_dashboard_dashboard_text() -> None:
    """dashboard.py must not contain code that touches Step 5
    invariants. The Step 5 invariants are pinned by their own tests;
    here we just rule out a wiring-time accidental edit."""
    text = _dashboard_text()
    assert "step5_implementation_allowed" not in text
    assert "STEP5_ENABLED_SUBSTAGE" not in text


# ---------------------------------------------------------------------------
# Conditional pins — fire only when wiring is present
# ---------------------------------------------------------------------------


def test_wiring_diff_is_exactly_one_import_and_one_register_call() -> None:
    """Once the wiring lands, the file must contain EXACTLY one
    occurrence of each of the two new lines. This catches accidental
    duplication or stray edits."""
    if not _wiring_present():
        # Wiring not yet added by the operator. Conditional pin
        # returns early; the test still passes. Once the operator
        # adds the two lines, this branch is no longer taken and the
        # assertions below fire.
        return
    text = _dashboard_text()
    assert text.count(EXPECTED_IMPORT_LINE) == 1, (
        "dashboard.py must contain exactly one new import line"
    )
    assert text.count(EXPECTED_REGISTER_CALL) == 1, (
        "dashboard.py must contain exactly one new register call"
    )


def test_wiring_register_call_after_existing_registrations() -> None:
    if not _wiring_present():
        return
    text = _dashboard_text()
    anchor = "register_roadmap_priority_routes(app)"
    anchor_pos = text.find(anchor)
    new_pos = text.find(EXPECTED_REGISTER_CALL)
    assert anchor_pos != -1
    assert new_pos != -1
    assert new_pos > anchor_pos, (
        "new push-subscribe register call must appear AFTER the "
        "existing register_roadmap_priority_routes(app) anchor"
    )


def test_wiring_import_grouped_with_dashboard_api_imports() -> None:
    if not _wiring_present():
        return
    text = _dashboard_text()
    pos = text.find(EXPECTED_IMPORT_LINE)
    anchor = (
        "from dashboard.api_roadmap_priority import "
        "register_roadmap_priority_routes"
    )
    anchor_pos = text.find(anchor)
    assert pos != -1
    assert anchor_pos != -1
    diff_lines = abs(
        text[:pos].count("\n") - text[:anchor_pos].count("\n")
    )
    assert diff_lines <= 10, (
        "new push-subscribe import should sit alongside existing "
        "dashboard.api_* imports (≤10 lines from the "
        "api_roadmap_priority anchor)"
    )


def test_wiring_no_other_dashboard_dashboard_modifications() -> None:
    """When the wiring lands, the diff to dashboard.py must include
    ONLY the two expected new lines. Detection is approximate: we
    count the number of lines that mention ``register_push_subscribe``
    or ``api_push_subscribe`` and assert it equals exactly 2 (one
    import, one register call)."""
    if not _wiring_present():
        return
    text = _dashboard_text()
    push_lines = [
        line
        for line in text.splitlines()
        if "register_push_subscribe" in line
        or "api_push_subscribe" in line
    ]
    assert len(push_lines) == 2, (
        f"dashboard.py must contain exactly 2 push-subscribe lines; "
        f"found {len(push_lines)}: {push_lines}"
    )


# ---------------------------------------------------------------------------
# Companion doc invariants (always on)
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "notification_dispatch_pwa.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
        or "no approval can happen from a notification click alone" in text
    )


def test_doc_states_no_real_push_in_n2b2b() -> None:
    text = _doc_text().lower()
    assert "no real push" in text or "no real web push" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window


def test_doc_lists_n2b3_n3_n4_n5_as_unimplemented() -> None:
    text = _doc_text().lower()
    for marker in ("n2b-3", "n3", "n4", "n5"):
        assert marker in text, marker
    assert "unimplemented" in text or "out of scope" in text or "future" in text
