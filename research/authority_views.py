"""Compatibility path for the canonical QRE policy authority views.

The canonical implementation lives in ``packages.qre_policy.authority_views``.
This module preserves the historical ``research.authority_views`` public API.
"""

from __future__ import annotations

from packages.qre_policy.authority_views import (
    active_discovery,
    bundle_active,
    live_eligible,
    render_authority_summary,
)

__all__ = [
    "bundle_active",
    "active_discovery",
    "live_eligible",
    "render_authority_summary",
]
