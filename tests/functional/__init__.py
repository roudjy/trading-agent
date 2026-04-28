"""v3.15.15.5 — Synthetic Artifact Contract Harness.

A read-only functional test suite that produces launcher-shaped
synthetic JSON/JSONL on disk under a sandboxed ``research/`` tree,
runs the v3.15.15.2 diagnostics CLI over those artifacts, and
asserts the v3.15.15.4 classifier output.

This package is opt-in. The default ``pytest -q`` invocation skips
every test under ``tests/functional/`` unless ``--run-functional`` is
passed. The skip is registered in ``tests/functional/conftest.py``.

Hard rules — enforced by ``test_static_import_surface.py``:

* No imports of any campaign / sprint / strategy / runtime / agent /
  execution / orchestration / automation / state / dashboard module.
* No imports of ``yfinance``, ``ccxt``, ``requests``, ``urllib*``,
  ``httpx``.
* No imports of pure-funnel modules
  (``research.campaign_registry``, ``research.discovery_sprint``,
  ``research.candidate_pipeline``, ``research.paper_readiness``,
  ``research.promotion``).

Allowed imports:
* Python stdlib
* ``pytest``
* ``research._sidecar_io`` (verified pure)
* ``research.diagnostics.*`` (verified pure by v3.15.15.2)
* Relative imports inside ``tests.functional``
"""

from __future__ import annotations

__all__: list[str] = []
