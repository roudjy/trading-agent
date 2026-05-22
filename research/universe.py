"""Compatibility path for the canonical QRE research universe boundary.

The canonical implementation lives in ``packages.qre_research.universe``.
This module preserves the historical ``research.universe`` import path.
"""

from __future__ import annotations

from packages.qre_research.universe import *  # noqa: F403
