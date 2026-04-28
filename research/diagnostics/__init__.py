"""v3.15.15.2 — Discovery Observability & Instrumentation.

Read-only observability layer. The Python package lives under
``research.diagnostics`` to avoid colliding with the pre-existing
``research.observability`` module (``ProgressTracker``), which is
left untouched for runtime backward compatibility. The OUTPUT
artifacts still land under ``research/observability/`` (a data
directory, not a Python package) per the v3.15.15.2 brief.

Every module under this package:

* reads existing artifacts via passive filesystem operations only;
* writes only to ``research/observability/`` via the atomic sidecar
  helper (``research._sidecar_io.write_sidecar_atomic``);
* never imports the campaign launcher, campaign policy, screening
  runtime, sprint orchestrator, strategy code, or any other
  behavior-affecting module — verified by
  ``tests/unit/test_diagnostics_static_import_surface.py``;
* never starts, stops, mutates, classifies, or decides anything.

Public API:

>>> from research.diagnostics.aggregator import build_observability_summary
>>> summary = build_observability_summary(now_utc=...)

The corresponding CLI is ``python -m research.diagnostics build``.
"""

from __future__ import annotations

__all__: list[str] = []
