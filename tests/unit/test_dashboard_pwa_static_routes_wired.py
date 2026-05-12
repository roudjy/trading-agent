"""Skip-or-enforce wiring consistency pin for dashboard.api_pwa_static.

The bugfix PR that ships ``dashboard/api_pwa_static.py`` does NOT
modify ``dashboard/dashboard.py`` itself (per the operator-owned
no-touch policy on that file). Wiring is the operator's two-line
diff:

::

    from dashboard.api_pwa_static import register_pwa_static_routes
    register_pwa_static_routes(app)

This test enforces the "both present or both absent" invariant so
that a partial wiring (only the import, or only the register call)
cannot land. The pattern matches the existing pins for
``api_approval_token_gate`` and ``api_merge_recommendation``.

When the operator applies the two-line wiring diff post-merge,
this test continues to pass (both lines now present). If a future
edit removes one of the two lines without removing the other, this
test fails loudly.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"

WIRING_IMPORT_LINE = (
    "from dashboard.api_pwa_static import register_pwa_static_routes"
)
WIRING_REGISTER_LINE = "register_pwa_static_routes(app)"


def test_dashboard_py_exists() -> None:
    assert DASHBOARD_PY.is_file(), (
        f"missing dashboard.py at {DASHBOARD_PY}; the wiring test "
        "cannot verify consistency"
    )


def test_blueprint_wiring_is_consistent_in_dashboard_dashboard() -> None:
    """Both the import and the register call must be present
    together, or both must be absent. A partial wiring is an
    unsafe intermediate state."""
    text = DASHBOARD_PY.read_text(encoding="utf-8")
    import_present = WIRING_IMPORT_LINE in text
    register_present = WIRING_REGISTER_LINE in text
    assert import_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_pwa_static, or NEITHER. Current state — "
        f"import_present={import_present}, "
        f"register_present={register_present}."
    )


def test_blueprint_module_imports_without_side_effects() -> None:
    """Importing api_pwa_static must not register anything globally
    or read any env. We import it here to assert the import is
    safe; the blueprint test file covers behavior."""
    from dashboard import api_pwa_static as pwa  # noqa: F401

    # Sanity: the module exposes the canonical register helper.
    assert hasattr(pwa, "register_pwa_static_routes"), (
        "api_pwa_static must expose register_pwa_static_routes"
    )
    # Step 5 invariants are not flipped by import.
    assert pwa.step5_implementation_allowed is False
    assert pwa.STEP5_ENABLED_SUBSTAGE == "none"
