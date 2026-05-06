"""PR-E (v3.15.16 metadata-mapping fix) — registry shape + preset
catalog fallback tests.

Pins the Stage-4 fix to the metadata-gap diagnostic:

* ``_index_registry`` accepts BOTH the production dict shape
  (``{campaigns: {campaign_id: {<record>}}}`` per
  ``research.campaign_registry.write_registry``) AND the legacy
  list shape used by older fixtures.
* ``_coords_for_campaign`` populates ``timeframe`` from
  ``research.presets.PRESETS`` when the registry record does not
  carry a ``timeframe`` field directly.
* ``BehaviorCoordinates.derivation_source`` records which source
  (``registry`` / ``preset_catalog`` / ``missing``) supplied the
  coordinates.
* Reading the production-shape fixture closes the metadata-gap on
  every campaign whose ``preset_name`` is in the in-memory catalog.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir
from research.presets import PRESETS as _PRODUCTION_PRESETS


# ---------------------------------------------------------------------------
# Closed-vocabulary pin for derivation labels
# ---------------------------------------------------------------------------


def test_derivation_constants_pinned() -> None:
    assert ir.DERIVATION_REGISTRY == "registry"
    assert ir.DERIVATION_PRESET_CATALOG == "preset_catalog"
    assert ir.DERIVATION_PRESET_NAME_FALLBACK == "preset_name_fallback"
    assert ir.DERIVATION_MISSING == "missing"
    assert ir.UNKNOWN_COORDINATE in ir.DERIVATION_SOURCES
    assert set(ir.DERIVATION_SOURCES) == {
        "registry", "preset_catalog", "preset_name_fallback",
        "missing", "unknown",
    }


# ---------------------------------------------------------------------------
# _index_registry — both shapes accepted
# ---------------------------------------------------------------------------


_RECORD_KEY = "col-20260503T100002576157Z-trend_equities_4h_baseline-43b53a7d29"
_RECORD_PAYLOAD = {
    "campaign_id": _RECORD_KEY,
    "preset_name": "trend_equities_4h_baseline",
    "asset_class": "equity",
    "strategy_family": None,
    "input_artifact_fingerprint": (
        "ce4e87ebd0072f6d6491704b6eff2dea430ff050de498c288336a7396e67b5d9"
    ),
    "extra": {},
    "spawned_at_utc": "2026-05-03T10:00:02.576157Z",
}


def test_index_registry_accepts_production_dict_shape() -> None:
    """Production writer (research.campaign_registry.write_registry)
    stores ``campaigns`` as a dict keyed by campaign_id."""
    payload = {
        "schema_version": "1.0",
        "campaigns": {_RECORD_KEY: _RECORD_PAYLOAD},
    }
    out = ir._index_registry(payload)
    assert _RECORD_KEY in out
    assert out[_RECORD_KEY] == _RECORD_PAYLOAD


def test_index_registry_accepts_legacy_list_shape() -> None:
    """Legacy fixture form: campaigns as a list of records."""
    payload = {
        "schema_version": "1.0",
        "campaigns": [_RECORD_PAYLOAD],
    }
    out = ir._index_registry(payload)
    assert _RECORD_KEY in out
    assert out[_RECORD_KEY] == _RECORD_PAYLOAD


def test_index_registry_dict_with_mismatched_inner_id_uses_index_key() -> None:
    """When the index key disagrees with the record's own
    campaign_id field, the index key is canonical."""
    rec = dict(_RECORD_PAYLOAD)
    rec["campaign_id"] = "col-WHATEVER"  # mismatched
    payload = {"campaigns": {_RECORD_KEY: rec}}
    out = ir._index_registry(payload)
    assert _RECORD_KEY in out
    assert "col-WHATEVER" not in out


def test_index_registry_legacy_top_level_registry_key_dict() -> None:
    payload = {"registry": {_RECORD_KEY: _RECORD_PAYLOAD}}
    out = ir._index_registry(payload)
    assert _RECORD_KEY in out


def test_index_registry_legacy_top_level_registry_key_list() -> None:
    payload = {"registry": [_RECORD_PAYLOAD]}
    out = ir._index_registry(payload)
    assert _RECORD_KEY in out


def test_index_registry_skips_non_dict_records() -> None:
    payload = {"campaigns": {_RECORD_KEY: "oops not a dict"}}
    out = ir._index_registry(payload)
    assert out == {}


def test_index_registry_skips_empty_or_non_string_keys() -> None:
    payload = {"campaigns": {"": _RECORD_PAYLOAD, 42: _RECORD_PAYLOAD}}
    out = ir._index_registry(payload)
    assert out == {}


def test_index_registry_handles_neither_key() -> None:
    payload = {"schema_version": "1.0"}
    out = ir._index_registry(payload)
    assert out == {}


# ---------------------------------------------------------------------------
# _preset_lookup — populated from research.presets.PRESETS
# ---------------------------------------------------------------------------


def test_preset_lookup_populated_from_real_catalog() -> None:
    """The lookup returns ``{name: {"timeframe": str}}`` for every
    preset in the canonical PRESETS catalog."""
    ir._reset_preset_lookup_cache_for_tests()
    out = ir._preset_lookup()
    expected_names = {str(p.name) for p in _PRODUCTION_PRESETS}
    actual_names = set(out)
    # All real preset names are present; any extra catalog-internal
    # presets are tolerated.
    assert expected_names.issubset(actual_names), (
        f"missing presets: {expected_names - actual_names!r}"
    )
    # Every entry carries a non-empty timeframe.
    for name, entry in out.items():
        assert "timeframe" in entry, name
        assert entry["timeframe"], name


def test_preset_lookup_is_cached() -> None:
    """Two consecutive calls return the same dict object."""
    ir._reset_preset_lookup_cache_for_tests()
    a = ir._preset_lookup()
    b = ir._preset_lookup()
    assert a is b


# ---------------------------------------------------------------------------
# AST source-parse fallback
# ---------------------------------------------------------------------------


def test_ast_source_parse_yields_same_presets_as_canonical_import() -> None:
    """The Tier-2 AST source parse of research/presets.py must
    produce a superset (== set) of (name, timeframe) pairs as the
    canonical Tier-1 import. Tier 2 is what the VPS uses when its
    system Python cannot import the project's deps."""
    canonical: dict[str, str] = {}
    for p in _PRODUCTION_PRESETS:
        if p.name and p.timeframe:
            canonical[p.name] = p.timeframe
    ast_out = ir._parse_presets_source_via_ast()
    ast_pairs = {n: e["timeframe"] for n, e in ast_out.items()}
    assert ast_pairs == canonical, (
        f"AST source parse drift:\n  canonical={canonical!r}\n  ast={ast_pairs!r}"
    )


# ---------------------------------------------------------------------------
# Tier 3 — preset_name regex fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "preset_name,expected",
    [
        # Real production preset names observed on the VPS.
        ("vol_compression_breakout_crypto_4h", "4h"),
        ("trend_equities_4h_baseline", "4h"),
        ("trend_pullback_crypto_1h", "1h"),
        ("trend_regime_filtered_equities_4h", "4h"),
        ("vol_compression_breakout_crypto_1h", "1h"),
        # Other timeframe shapes.
        ("strategy_15m_xyz", "15m"),
        ("xyz_5m_baseline", "5m"),
        ("daily_only_1d", "1d"),
        ("anchor_1w", "1w"),
        ("monthly_1M", "1M"),
        # Negative cases — must NOT match.
        ("no_timeframe_token_here", None),
        ("crypto4hello", None),  # not bounded by underscore
        ("only_4hours", None),  # 4hours has 4h as substring but not a token
        ("", None),
    ],
)
def test_parse_timeframe_from_preset_name(
    preset_name: str, expected: str | None,
) -> None:
    out = ir._parse_timeframe_from_preset_name(preset_name)
    assert out == expected


def test_parse_timeframe_from_preset_name_none_input() -> None:
    assert ir._parse_timeframe_from_preset_name(None) is None
    assert ir._parse_timeframe_from_preset_name(42) is None


def test_coords_uses_preset_name_fallback_when_catalog_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate the VPS environment: catalog import fails AND the
    AST source parse fails. The regex on preset_name then fires."""
    # Force both tiers to return empty by clearing the cache and
    # monkeypatching _parse_presets_source_via_ast to {}, then also
    # making the real PRESETS import return nothing usable. The
    # cleanest way: override the cache directly with empty content.
    ir._reset_preset_lookup_cache_for_tests()
    monkeypatch.setattr(ir, "_PRESET_LOOKUP_CACHE", {})
    rec = {
        "campaign_id": "col-fallback",
        "preset_name": "trend_pullback_crypto_1h",  # Tier-3 will parse "1h"
        "asset_class": "crypto",
        "strategy_family": "trend_pullback",
        "extra": {},
        "input_artifact_fingerprint": "abcd",
    }
    coords, preset_name, _fp, has_full = ir._coords_for_campaign(
        "col-fallback", {"col-fallback": rec},
    )
    assert coords.timeframe == "1h"
    assert coords.derivation_source == "preset_name_fallback"
    assert preset_name == "trend_pullback_crypto_1h"
    assert has_full is True
    # Restore catalog so other tests are unaffected.
    ir._reset_preset_lookup_cache_for_tests()


def test_coords_preset_name_fallback_failure_yields_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all three tiers fail (preset_name has no recognizable
    timeframe token), derivation_source == 'missing'."""
    ir._reset_preset_lookup_cache_for_tests()
    monkeypatch.setattr(ir, "_PRESET_LOOKUP_CACHE", {})
    rec = {
        "campaign_id": "col-no-timeframe",
        "preset_name": "no_timeframe_token_here",
        "asset_class": "crypto",
        "strategy_family": "ema_crossover",
        "extra": {},
    }
    coords, _preset_name, _fp, has_full = ir._coords_for_campaign(
        "col-no-timeframe", {"col-no-timeframe": rec},
    )
    assert coords.timeframe == "unknown"
    assert coords.derivation_source == "missing"
    assert has_full is False
    ir._reset_preset_lookup_cache_for_tests()


def test_coords_preference_order_registry_then_catalog_then_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the registry record carries an explicit timeframe, it
    wins over both the catalog and the regex (already pinned by
    test_coords_extra_timeframe_takes_priority_over_preset_catalog).
    When registry omits timeframe but catalog has it, catalog wins
    over the regex (the regex never even runs). Verify the regex is
    reached only when both registry AND catalog are silent."""
    real_preset = next(
        p for p in _PRODUCTION_PRESETS if p.timeframe and p.name
    )
    ir._reset_preset_lookup_cache_for_tests()
    # Catalog populated normally — regex must NOT fire.
    rec = {
        "campaign_id": "col-cat-wins",
        "preset_name": real_preset.name,
        "asset_class": "equity",
        "strategy_family": "ema_crossover",
        "extra": {},
    }
    coords, _, _, _ = ir._coords_for_campaign(
        "col-cat-wins", {"col-cat-wins": rec},
    )
    assert coords.timeframe == real_preset.timeframe
    assert coords.derivation_source == "preset_catalog"  # NOT "preset_name_fallback"
    ir._reset_preset_lookup_cache_for_tests()


# ---------------------------------------------------------------------------
# _coords_for_campaign — derivation_source labels
# ---------------------------------------------------------------------------


def test_coords_full_registry_yields_registry_source() -> None:
    """When the registry record carries family + asset_class +
    timeframe directly, derivation_source == 'registry'."""
    rec = {
        "campaign_id": "col-x",
        "preset_name": "preset_x",
        "strategy_family": "ema_crossover",
        "asset_class": "crypto",
        "timeframe": "4h",
        "input_artifact_fingerprint": "abcd1234",
    }
    index = {"col-x": rec}
    coords, preset_name, fp, has_full = ir._coords_for_campaign(
        "col-x", index,
    )
    assert coords.family == "ema_crossover"
    assert coords.asset_class == "crypto"
    assert coords.timeframe == "4h"
    assert coords.derivation_source == "registry"
    assert preset_name == "preset_x"
    assert fp == "abcd1234"
    assert has_full is True


def test_coords_production_record_uses_preset_catalog_for_timeframe() -> None:
    """Production registry records carry preset_name + asset_class
    but NOT timeframe. The preset-catalog lookup fills timeframe;
    derivation_source becomes 'preset_catalog'."""
    # Use a real preset name from the live catalog.
    real_preset = next(p for p in _PRODUCTION_PRESETS)
    rec = {
        "campaign_id": "col-y",
        "preset_name": real_preset.name,
        "asset_class": "equity",
        "strategy_family": "ema_crossover",
        # NB: no timeframe / interval; extra empty.
        "extra": {},
        "input_artifact_fingerprint": "ffff0000",
    }
    index = {"col-y": rec}
    ir._reset_preset_lookup_cache_for_tests()
    coords, preset_name, fp, has_full = ir._coords_for_campaign(
        "col-y", index,
    )
    assert coords.family == "ema_crossover"
    assert coords.asset_class == "equity"
    assert coords.timeframe == real_preset.timeframe
    assert coords.derivation_source == "preset_catalog"
    assert preset_name == real_preset.name
    assert has_full is True


def test_coords_unknown_preset_yields_missing() -> None:
    """When the registry record's preset_name is not in the catalog
    AND no timeframe field exists, derivation_source == 'missing'
    and timeframe stays unknown."""
    rec = {
        "campaign_id": "col-z",
        "preset_name": "preset_does_not_exist_anywhere",
        "asset_class": "crypto",
        "strategy_family": "ema_crossover",
        "extra": {},
        "input_artifact_fingerprint": "deadbeef",
    }
    index = {"col-z": rec}
    coords, preset_name, fp, has_full = ir._coords_for_campaign(
        "col-z", index,
    )
    assert coords.timeframe == "unknown"
    assert coords.derivation_source == "missing"
    assert has_full is False


def test_coords_extra_timeframe_takes_priority_over_preset_catalog() -> None:
    """When the registry record's ``extra`` carries a timeframe
    explicitly, it wins over the preset-catalog fallback."""
    real_preset = next(p for p in _PRODUCTION_PRESETS)
    rec = {
        "campaign_id": "col-w",
        "preset_name": real_preset.name,
        "asset_class": "crypto",
        "strategy_family": "ema_crossover",
        "extra": {"timeframe": "1d"},  # NOT real_preset.timeframe
        "input_artifact_fingerprint": "abcd",
    }
    index = {"col-w": rec}
    coords, _preset_name, _fp, has_full = ir._coords_for_campaign(
        "col-w", index,
    )
    assert coords.timeframe == "1d"  # extra wins
    assert coords.derivation_source == "registry"  # registry source
    assert has_full is True


def test_coords_missing_record_yields_missing() -> None:
    """No record at all → coords are all unknown,
    derivation_source == 'missing'."""
    coords, preset_name, fp, has_full = ir._coords_for_campaign(
        "col-not-in-index", {},
    )
    assert coords.family == "unknown"
    assert coords.asset_class == "unknown"
    assert coords.timeframe == "unknown"
    assert coords.derivation_source == "missing"
    assert preset_name == "unknown"
    assert fp is None
    assert has_full is False


# ---------------------------------------------------------------------------
# build_report — full pipeline using a production-shape fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_now_utc() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _write(tmp_path: Path, queue, registry, dz, ig) -> dict[str, Path]:
    paths = {
        "queue": tmp_path / "q.json",
        "registry": tmp_path / "r.json",
        "dead_zones": tmp_path / "d.json",
        "ig": tmp_path / "i.json",
    }
    paths["queue"].write_text(json.dumps(queue), encoding="utf-8")
    paths["registry"].write_text(json.dumps(registry), encoding="utf-8")
    paths["dead_zones"].write_text(json.dumps(dz), encoding="utf-8")
    paths["ig"].write_text(json.dumps(ig), encoding="utf-8")
    return paths


def test_build_report_against_production_shape_closes_metadata_gap(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Build a report from a fixture mirroring the production VPS
    shape (dict-keyed campaigns, registry records carrying
    preset_name/asset_class/strategy_family but NOT timeframe).
    Assert the metadata gap is closed for the rows whose preset is
    in the canonical catalog."""
    real_preset = next(
        p for p in _PRODUCTION_PRESETS if p.timeframe and p.name
    )
    queue = {
        "schema_version": "1.0",
        "queue": [
            {
                "campaign_id": "col-real",
                "priority_tier": 2,
                "spawned_at_utc": "2026-05-06T10:00:00+00:00",
                "state": "pending",
            },
        ],
    }
    registry = {
        "schema_version": "1.0",
        # Production dict shape.
        "campaigns": {
            "col-real": {
                "campaign_id": "col-real",
                "preset_name": real_preset.name,
                "asset_class": "crypto",
                "strategy_family": "ema_crossover",
                "extra": {},
                "input_artifact_fingerprint": "feedface",
                "spawned_at_utc": "2026-05-06T10:00:00+00:00",
            },
        },
    }
    paths = _write(tmp_path, queue, registry, {"zones": []}, {})
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
    )
    assert report.summary.total == 1
    # Metadata gap is closed: the preset-catalog filled in timeframe.
    assert report.summary.metadata_gaps == 0
    decision = report.decisions[0]
    coords = decision.behavior_coordinates
    assert coords.family == "ema_crossover"
    assert coords.asset_class == "crypto"
    assert coords.timeframe == real_preset.timeframe
    assert coords.derivation_source == "preset_catalog"
    payload = decision.to_payload()
    coord_payload = payload["behavior_coordinates"]
    assert coord_payload["derivation_source"] == "preset_catalog"
    assert coord_payload["provisional"] is True
    # Framing intact.
    full_payload = report.to_payload()
    assert full_payload["routing_effect"] == "advisory_only"
    assert full_payload["queue_ordering_effect"] == "none"


def test_build_report_legacy_list_shape_still_works(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """Backwards-compatibility: pre-PR-E fixtures using the legacy
    list-shape registry must still index correctly."""
    queue = {
        "queue": [
            {"campaign_id": "col-legacy", "spawned_at_utc": "2026-05-06T10:00:00+00:00"},
        ],
    }
    registry = {
        "campaigns": [
            {
                "campaign_id": "col-legacy",
                "preset_name": "preset_legacy",
                "strategy_family": "ema_crossover",
                "asset_class": "crypto",
                "timeframe": "4h",
                "input_artifact_fingerprint": "abcd",
                "spawned_at_utc": "2026-05-06T10:00:00+00:00",
            },
        ],
    }
    paths = _write(tmp_path, queue, registry, {"zones": []}, {})
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
    )
    assert report.summary.total == 1
    coords = report.decisions[0].behavior_coordinates
    assert coords.timeframe == "4h"
    # Legacy fixture had timeframe directly in the record → registry.
    assert coords.derivation_source == "registry"


def test_build_report_dict_with_partial_strategy_family(
    tmp_path: Path, fixed_now_utc: _dt.datetime,
) -> None:
    """The production registry records sometimes have
    ``strategy_family: null`` (when no hypothesis is bound). The
    routing layer must mark ``derivation_source = 'missing'`` for
    those rows even if preset_name + asset_class + timeframe are
    available, because ``family`` is a coordinate field too."""
    real_preset = next(
        p for p in _PRODUCTION_PRESETS if p.timeframe and p.name
    )
    queue = {
        "queue": [
            {"campaign_id": "col-partial", "spawned_at_utc": "t"},
        ],
    }
    registry = {
        "campaigns": {
            "col-partial": {
                "campaign_id": "col-partial",
                "preset_name": real_preset.name,
                "asset_class": "equity",
                "strategy_family": None,  # ← partial
                "extra": {},
            },
        },
    }
    paths = _write(tmp_path, queue, registry, {"zones": []}, {})
    report = ir.build_report(
        now_utc=fixed_now_utc,
        queue_path=paths["queue"],
        registry_path=paths["registry"],
        dead_zones_path=paths["dead_zones"],
        information_gain_path=paths["ig"],
    )
    coords = report.decisions[0].behavior_coordinates
    assert coords.family == "unknown"
    assert coords.derivation_source == "missing"
    assert report.summary.metadata_gaps == 1
