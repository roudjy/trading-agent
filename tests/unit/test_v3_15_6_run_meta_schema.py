"""v3.15.6 — run_meta schema bump 1.1 → 1.2 (additive screening_phase).

Pins:

- ``RUN_META_SCHEMA_VERSION == "1.2"``.
- ``RUN_META_PATH`` filename is unchanged
  (``research/run_meta_latest.v1.json``) — the ``v1`` is the
  major-schema generation, ``schema_version`` carries the minor.
- The payload contains ``screening_phase`` populated from the
  preset.
- ``screening_phase`` is null when no preset is bound.
- v1.0 / v1.1 payloads without the new field remain readable via
  ``read_run_meta_sidecar``.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.presets import get_preset
from research.run_meta import (
    RUN_META_PATH,
    RUN_META_SCHEMA_VERSION,
    build_run_meta_payload,
    read_run_meta_sidecar,
)


def _payload(preset=None) -> dict:
    return build_run_meta_payload(
        run_id="r1",
        preset=preset,
        started_at_utc="2026-04-26T00:00:00Z",
        completed_at_utc=None,
        git_revision=None,
        config_hash=None,
        candidate_summary=None,
        top_rejection_reasons=None,
        artifact_paths=None,
    )


def test_schema_version_is_12():
    assert RUN_META_SCHEMA_VERSION == "1.2"


def test_filename_remains_v1_json():
    """The ``v1`` in the filename is the major-schema generation; do
    not rename to ``v1.2.json`` or anything else.
    """
    assert RUN_META_PATH == Path("research/run_meta_latest.v1.json")


def test_payload_includes_screening_phase_field():
    payload = _payload(preset=get_preset("trend_pullback_crypto_1h"))
    assert "screening_phase" in payload
    assert payload["screening_phase"] == "exploratory"


def test_payload_screening_phase_null_when_no_preset():
    payload = _payload(preset=None)
    assert payload["screening_phase"] is None


def test_payload_for_baseline_is_promotion_grade():
    payload = _payload(preset=get_preset("trend_equities_4h_baseline"))
    assert payload["screening_phase"] == "promotion_grade"


def test_payload_schema_version_is_present_and_12():
    payload = _payload(preset=get_preset("crypto_diagnostic_1h"))
    assert payload["schema_version"] == "1.2"


def test_v11_payload_without_screening_phase_remains_readable(tmp_path: Path):
    """Backward compatibility: a v1.1 payload (pre-v3.15.6) must
    still be loadable. Readers must not assert on schema_version
    or on the presence of ``screening_phase``.
    """
    v11_payload = {
        "schema_version": "1.1",
        "run_id": "legacy",
        "preset_name": "trend_equities_4h_baseline",
        "preset_class": "baseline",
        "preset_hypothesis": "h",
        "preset_universe": ["NVDA"],
        "preset_bundle": ["sma_crossover"],
        "preset_optional_bundle": [],
        "preset_status": "stable",
        "preset_rationale": "r",
        "preset_expected_behavior": "e",
        "preset_falsification": ["f"],
        "preset_bundle_hypotheses": [],
        "diagnostic_only": False,
        "excluded_from_candidate_promotion": False,
        "screening_mode": "strict",
        "cost_mode": "realistic",
        "regime_filter": None,
        "regime_modes": [],
        "started_at_utc": "2026-03-01T00:00:00+00:00",
        "completed_at_utc": "2026-03-01T00:30:00+00:00",
        "git_revision": "deadbeef",
        "config_hash": "cafe",
        "candidate_summary": {
            "raw": 0, "screened": 0, "validated": 0,
            "rejected": 0, "promoted": 0,
        },
        "top_rejection_reasons": [],
        "artifact_paths": {},
    }
    path = tmp_path / "v11_legacy.v1.json"
    path.write_text(json.dumps(v11_payload), encoding="utf-8")
    restored = read_run_meta_sidecar(path)
    assert isinstance(restored, dict)
    assert restored["schema_version"] == "1.1"
    assert "screening_phase" not in restored  # absent on v1.1 payload
