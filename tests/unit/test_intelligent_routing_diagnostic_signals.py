"""Unit tests for v3.15.16 Intelligent Routing Layer —
diagnostic-aware routing signals schema and projector.

Pins:

* closed vocabularies (ROUTING_SIGNAL_FAMILY,
  ROUTING_SIGNAL_STATUS, ROUTING_SIGNAL_DIRECTION,
  ROUTING_SIGNAL_SOURCE, ROUTING_SIGNAL_TARGET_LAYER);
* schema integrity (RoutingDiagnosticSignal,
  RoutingSignalProjection field tuples);
* deterministic output with injected ``generated_at_utc``;
* byte-identical output for identical input;
* atomic write only under
  ``logs/intelligent_routing_diagnostic_signals/``;
* ``--no-write`` does not write; ``--status`` does not write;
* every Roadmap v6 + Addendum 1 signal family is represented
  with at least one signal;
* every signal has non-empty ``allowed_use``, ``forbidden_use``,
  and ``missing_input_behavior``;
* effect fields are bounded prose: non-empty, ≤200 chars, no
  newline, no authority-granting / trade / execute / order /
  capital-allocation phrases;
* ``status="schema_only"`` is hard-coded in ``_normalise_signal``
  (a synthetic seed with a different status is still emitted as
  ``schema_only``);
* baseline ``forbidden_use`` is prepended on every signal;
  per-signal extras append without replacing the baseline;
  duplicates are deterministically de-duplicated; order is
  stable;
* projection_invariants pin: diagnostics_do_not_trade,
  external_data_is_not_alpha, no_runtime_trading_authority,
  no_campaign_queue_mutation, no_strategy_generation,
  no_step5_runtime, no_level6,
  no_production_merge_authority, read_only;
* no forbidden imports or forbidden runtime tokens appear in the
  module source.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import intelligent_routing_diagnostic_signals as rsd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T22:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_routing_signal_family_is_closed_exact() -> None:
    """Roadmap v6 + Addendum 1 diagnostic families. Exactly 14
    entries; order matters for deterministic projection."""
    assert rsd.ROUTING_SIGNAL_FAMILY == (
        "entropy",
        "tail",
        "criticality",
        "network",
        "quorum",
        "external_intelligence",
        "dead_zone",
        "null_model",
        "barrier",
        "resonance",
        "adversarial",
        "seismic",
        "turbulence",
        "market_language",
    )


def test_routing_signal_status_is_closed() -> None:
    assert rsd.ROUTING_SIGNAL_STATUS == (
        "schema_only",
        "advisory_planned",
        "advisory_active",
        "suppressed",
        "deprecated",
    )


def test_routing_signal_direction_is_closed() -> None:
    """Direction values describe routing priority effect only; no
    buy/sell direction — diagnostics do not trade."""
    assert rsd.ROUTING_SIGNAL_DIRECTION == (
        "prioritize",
        "deprioritize",
        "suppress",
        "neutral",
        "require_confirmation",
    )
    # Forbid trading-direction words.
    for value in rsd.ROUTING_SIGNAL_DIRECTION:
        for forbidden in ("buy", "sell", "long", "short", "exit"):
            assert forbidden != value, (value, forbidden)


def test_routing_signal_source_is_closed_and_non_empty() -> None:
    assert isinstance(rsd.ROUTING_SIGNAL_SOURCE, tuple)
    assert len(rsd.ROUTING_SIGNAL_SOURCE) >= 14
    for s in rsd.ROUTING_SIGNAL_SOURCE:
        assert isinstance(s, str) and s


def test_routing_signal_target_layer_is_closed_exact() -> None:
    assert rsd.ROUTING_SIGNAL_TARGET_LAYER == (
        "market_behavior",
        "hypothesis_discovery",
        "strategy_mapping",
        "preset",
        "campaign",
        "funnel",
        "evidence",
        "policy",
    )


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_routing_diagnostic_signal_field_list_exact() -> None:
    assert rsd.ROUTING_DIAGNOSTIC_SIGNAL_FIELDS == (
        "id",
        "family",
        "name",
        "description",
        "source",
        "target_layer",
        "direction",
        "status",
        "expected_information_gain_effect",
        "dead_zone_risk_effect",
        "orthogonality_effect",
        "public_data_quality_effect",
        "confirmation_requirement_effect",
        "allowed_use",
        "forbidden_use",
        "required_inputs",
        "missing_input_behavior",
    )


def test_routing_signal_projection_field_list_exact() -> None:
    assert rsd.ROUTING_SIGNAL_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "signals",
        "projection_invariants",
    )


def test_every_signal_has_every_field(snap: dict) -> None:
    for s in snap["signals"]:
        assert set(s.keys()) == set(
            rsd.ROUTING_DIAGNOSTIC_SIGNAL_FIELDS
        ), s


def test_projection_carries_every_top_level_field(snap: dict) -> None:
    for field in rsd.ROUTING_SIGNAL_PROJECTION_FIELDS:
        assert field in snap, field


def test_every_signal_value_in_closed_vocab(snap: dict) -> None:
    for s in snap["signals"]:
        assert s["family"] in rsd.ROUTING_SIGNAL_FAMILY
        assert s["status"] in rsd.ROUTING_SIGNAL_STATUS
        assert s["direction"] in rsd.ROUTING_SIGNAL_DIRECTION
        assert s["source"] in rsd.ROUTING_SIGNAL_SOURCE
        assert s["target_layer"] in rsd.ROUTING_SIGNAL_TARGET_LAYER


def test_signal_ids_are_unique(snap: dict) -> None:
    ids = [s["id"] for s in snap["signals"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# All Roadmap v6 + Addendum 1 families are represented
# ---------------------------------------------------------------------------


_REQUIRED_FAMILIES = (
    "entropy",
    "tail",
    "criticality",
    "network",
    "quorum",
    "external_intelligence",
    "dead_zone",
    "null_model",
    "barrier",
    "resonance",
    "adversarial",
    "seismic",
    "turbulence",
    "market_language",
)


@pytest.mark.parametrize("family", _REQUIRED_FAMILIES)
def test_every_required_family_has_at_least_one_signal(
    snap: dict, family: str
) -> None:
    matched = [s for s in snap["signals"] if s["family"] == family]
    assert len(matched) >= 1, family


def test_signal_count_matches_family_count(snap: dict) -> None:
    """Today there is exactly one signal per family. Future
    operator-approved units may add more; if they do, this test is
    the canonical place to update the expected count."""
    assert len(snap["signals"]) == len(_REQUIRED_FAMILIES)


# ---------------------------------------------------------------------------
# Mandatory list / scalar fields are non-empty
# ---------------------------------------------------------------------------


def test_every_signal_has_non_empty_allowed_use(snap: dict) -> None:
    for s in snap["signals"]:
        assert isinstance(s["allowed_use"], list)
        assert s["allowed_use"], s["id"]


def test_every_signal_has_non_empty_forbidden_use(snap: dict) -> None:
    for s in snap["signals"]:
        assert isinstance(s["forbidden_use"], list)
        assert s["forbidden_use"], s["id"]


def test_every_signal_has_non_empty_required_inputs(snap: dict) -> None:
    for s in snap["signals"]:
        assert isinstance(s["required_inputs"], list)
        assert s["required_inputs"], s["id"]


def test_every_signal_has_missing_input_behavior(snap: dict) -> None:
    for s in snap["signals"]:
        assert isinstance(s["missing_input_behavior"], str)
        assert s["missing_input_behavior"].strip(), s["id"]


# ---------------------------------------------------------------------------
# Effect fields are bounded prose: non-empty, <=200 chars, no newline,
# no authority-granting / trade / execute / order / capital phrases.
# ---------------------------------------------------------------------------


_EFFECT_FIELDS = (
    "expected_information_gain_effect",
    "dead_zone_risk_effect",
    "orthogonality_effect",
    "public_data_quality_effect",
    "confirmation_requirement_effect",
)


@pytest.mark.parametrize("field", _EFFECT_FIELDS)
def test_effect_field_is_non_empty_bounded_string(
    snap: dict, field: str
) -> None:
    for s in snap["signals"]:
        v = s[field]
        assert isinstance(v, str), (s["id"], field, type(v))
        assert v.strip(), (s["id"], field, "empty")
        assert len(v) <= rsd.MAX_EFFECT_LEN, (s["id"], field, len(v))


@pytest.mark.parametrize("field", _EFFECT_FIELDS)
def test_effect_field_has_no_newline(snap: dict, field: str) -> None:
    for s in snap["signals"]:
        v = s[field]
        assert "\n" not in v, (s["id"], field)
        assert "\r" not in v, (s["id"], field)


_FORBIDDEN_EFFECT_SEMANTICS = (
    # Authority-granting verb phrases on the signal itself.
    "places order",
    "places orders",
    "place orders",
    "places trade",
    "places trades",
    "place trades",
    "place a trade",
    "executes trade",
    "executes trades",
    "execute trade",
    "execute trades",
    "execute orders",
    "allocates capital",
    "allocate capital",
    "moves funds",
    "moves capital",
    "move capital",
    "mutates live",
    "mutates risk",
    "mutate live",
    "mutate risk",
    "opens position",
    "opens positions",
    "open position",
    "open positions",
    "submits order",
    "submit order",
    "submits orders",
    "submit orders",
    "should trade",
    "should execute",
    "should allocate",
    "should place",
)


@pytest.mark.parametrize("field", _EFFECT_FIELDS)
def test_effect_field_has_no_authority_granting_semantics(
    snap: dict, field: str
) -> None:
    for s in snap["signals"]:
        lo = s[field].lower()
        for forbidden in _FORBIDDEN_EFFECT_SEMANTICS:
            assert forbidden not in lo, (s["id"], field, forbidden)


# ---------------------------------------------------------------------------
# status="schema_only" is hard-coded in _normalise_signal
# ---------------------------------------------------------------------------


def test_every_emitted_signal_has_status_schema_only(snap: dict) -> None:
    for s in snap["signals"]:
        assert s["status"] == "schema_only", s["id"]


def test_normalise_signal_overrides_status_with_schema_only() -> None:
    """Synthetic seed with a different status must STILL emit
    status='schema_only'. This pins the hard-coded override in
    `_normalise_signal()`."""
    synthetic_raw = {
        "id": "synthetic_signal",
        "family": "entropy",
        "name": "Synthetic signal for status-override test",
        "description": "Test fixture.",
        "source": "research/diagnostics/entropy.py",
        "target_layer": "campaign",
        "direction": "neutral",
        # Deliberately wrong: the seed claims advisory_active.
        "status": "advisory_active",
        "expected_information_gain_effect": "neutral",
        "dead_zone_risk_effect": "neutral",
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": "neutral",
        "allowed_use": ("advisory routing input",),
        "extra_forbidden_use": (),
        "required_inputs": ("synthetic input",),
        "missing_input_behavior": "fall to suppressed",
    }
    out = rsd._normalise_signal(synthetic_raw)
    assert out["status"] == "schema_only"


# ---------------------------------------------------------------------------
# Baseline forbidden_use prepended on every signal; per-signal extras
# appended without replacing baseline; duplicates dedup'd; stable order.
# ---------------------------------------------------------------------------


def test_every_signal_carries_all_baseline_forbidden_use_entries(
    snap: dict,
) -> None:
    for s in snap["signals"]:
        for required in rsd._BASE_FORBIDDEN_USE:
            assert required in s["forbidden_use"], (s["id"], required)


def test_baseline_forbidden_use_appears_before_per_signal_extras() -> None:
    """The baseline order is preserved at the front of every emitted
    forbidden_use list. Per-signal extras are appended after the
    baseline."""
    synthetic_raw = {
        "id": "synthetic_for_order_test",
        "family": "entropy",
        "name": "Synthetic order-pin",
        "description": "Order-pin test fixture.",
        "source": "research/diagnostics/entropy.py",
        "target_layer": "campaign",
        "direction": "neutral",
        "status": "schema_only",
        "expected_information_gain_effect": "neutral",
        "dead_zone_risk_effect": "neutral",
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": "neutral",
        "allowed_use": ("advisory routing input",),
        "extra_forbidden_use": (
            "may not synthetically forbid one extra thing",
        ),
        "required_inputs": ("synthetic input",),
        "missing_input_behavior": "fall to suppressed",
    }
    out = rsd._normalise_signal(synthetic_raw)
    forbidden = out["forbidden_use"]
    # The baseline list appears in order at the head of the merged
    # list, then the extra entry.
    baseline_indices = [
        forbidden.index(b) for b in rsd._BASE_FORBIDDEN_USE if b in forbidden
    ]
    assert baseline_indices == sorted(baseline_indices), forbidden
    extra_idx = forbidden.index(
        "may not synthetically forbid one extra thing"
    )
    for i in baseline_indices:
        assert i < extra_idx, (forbidden, i, extra_idx)


def test_per_signal_extra_does_not_replace_baseline(snap: dict) -> None:
    """No signal-specific forbid replaces the baseline list. The
    baseline survives every merge."""
    for s in snap["signals"]:
        for required in rsd._BASE_FORBIDDEN_USE:
            assert required in s["forbidden_use"], (s["id"], required)


def test_duplicate_forbidden_use_entries_are_deduplicated() -> None:
    """Per-signal extras that duplicate a baseline entry are
    deterministically dropped; the order remains stable."""
    duplicate_extra = rsd._BASE_FORBIDDEN_USE[0]
    synthetic_raw = {
        "id": "synthetic_for_dedup_test",
        "family": "entropy",
        "name": "Synthetic dedup-pin",
        "description": "Dedup-pin test fixture.",
        "source": "research/diagnostics/entropy.py",
        "target_layer": "campaign",
        "direction": "neutral",
        "status": "schema_only",
        "expected_information_gain_effect": "neutral",
        "dead_zone_risk_effect": "neutral",
        "orthogonality_effect": "neutral",
        "public_data_quality_effect": "neutral",
        "confirmation_requirement_effect": "neutral",
        "allowed_use": ("advisory routing input",),
        "extra_forbidden_use": (
            duplicate_extra,  # exact baseline duplicate
            "may not do something specific",
        ),
        "required_inputs": ("synthetic input",),
        "missing_input_behavior": "fall to suppressed",
    }
    out = rsd._normalise_signal(synthetic_raw)
    forbidden = out["forbidden_use"]
    # The duplicate baseline entry appears exactly once.
    assert forbidden.count(duplicate_extra) == 1
    # The unique extra is appended.
    assert "may not do something specific" in forbidden


def test_forbidden_use_order_is_stable_across_runs(snap: dict) -> None:
    a = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    for sa, sb in zip(a["signals"], b["signals"]):
        assert sa["forbidden_use"] == sb["forbidden_use"]


# ---------------------------------------------------------------------------
# Projection invariants
# ---------------------------------------------------------------------------


def test_projection_invariants_pin_diagnostics_do_not_trade(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["diagnostics_do_not_trade"] is True


def test_projection_invariants_pin_external_data_is_not_alpha(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["external_data_is_not_alpha"] is True


def test_projection_invariants_pin_read_only(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["read_only"] is True


def test_projection_invariants_pin_no_runtime_trading_authority(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_projection_invariants_pin_no_campaign_queue_mutation(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_campaign_queue_mutation"] is True


def test_projection_invariants_pin_no_strategy_generation(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_strategy_generation"] is True


def test_projection_invariants_pin_no_step5_runtime(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_step5_runtime"] is True
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_projection_invariants_pin_no_level6(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_level6"] is True


def test_projection_invariants_pin_no_production_merge_authority(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_production_merge_authority"] is True


def test_projection_invariants_pin_no_routing_mutation(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_routing_mutation"] is True
    assert inv["no_research_runtime_change"] is True


def test_projection_invariants_pin_no_branch_pr_merge_deploy(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_branch_creation"] is True
    assert inv["no_pr_creation"] is True
    assert inv["no_merge_or_deploy"] is True


def test_projection_invariants_pin_no_mutation_routes_or_approval_buttons(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_mutation_routes"] is True
    assert inv["no_approval_buttons"] is True


def test_projection_invariants_pin_writes_only_signals_log(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["writes_only_intelligent_routing_diagnostic_signals_log"] is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_signals_sorted_stably_by_family_then_id(snap: dict) -> None:
    pairs = [(s["family"], s["id"]) for s in snap["signals"]]
    assert pairs == sorted(pairs)


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rsd._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rsd._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    good.parent.mkdir(parents=True, exist_ok=True)
    rsd._atomic_write_json(good, {"x": 1})
    assert good.is_file()


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    rsd._atomic_write_json(target, {"x": 1})
    rsd._atomic_write_json(target, {"x": 2})
    siblings = list(target.parent.iterdir())
    assert siblings == [target]


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    monkeypatch.setattr(rsd, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rsd, "ARTIFACT_DIR", sentinel.parent)
    rc = rsd.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"intelligent_routing_diagnostic_signals"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    monkeypatch.setattr(rsd, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rsd, "ARTIFACT_DIR", sentinel.parent)
    rc = rsd.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "intelligent_routing_diagnostic_signals" in out
    assert "diagnostics_do_not_trade=True" in out
    assert "external_data_is_not_alpha=True" in out
    assert "no_runtime_trading_authority=True" in out
    assert "no_step5_runtime=True" in out
    assert "no_level6=True" in out
    assert "no_production_merge_authority=True" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    monkeypatch.setattr(rsd, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rsd, "ARTIFACT_DIR", sentinel.parent)
    rc = rsd.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "intelligent_routing_diagnostic_signals"
    assert payload["module_version"].startswith("v3.15.16.routing_signals")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = (
        tmp_path
        / "logs"
        / "intelligent_routing_diagnostic_signals"
        / "latest.json"
    )
    monkeypatch.setattr(rsd, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rsd, "ARTIFACT_DIR", sentinel.parent)
    rc = rsd.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rsd.__file__).read_text(encoding="utf-8")


def _module_imports() -> list[str]:
    import ast as _ast

    tree = _ast.parse(_module_source())
    out: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, _ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                out.append(f"{mod}.{alias.name}" if mod else alias.name)
    return out


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    assert "subprocess." not in src


def test_no_socket_or_urllib_or_http_or_requests() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "from socket",
        "import urllib",
        "from urllib",
        "import http",
        "from http",
        "import requests",
        "from requests",
        "import httpx",
        "from httpx",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_runtime_imports_via_ast() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "live",
        "paper",
        "shadow",
        "trading",
        "reporting.intelligent_routing",
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
        "reporting.execution_authority",
        "reporting.roadmap_task_catalog",
        "reporting.roadmap_task_units",
        "reporting.roadmap_unit_authority",
        "reporting.roadmap_next_unit",
    )
    for module in _module_imports():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_has_no_third_party_imports() -> None:
    """Stdlib only — pin the import set explicitly."""
    allowed_stdlib_modules = {
        "__future__.annotations",
        "argparse",
        "datetime",
        "json",
        "os",
        "sys",
        "tempfile",
        "pathlib.Path",
        "typing.Any",
        "typing.Final",
    }
    for module in _module_imports():
        assert module in allowed_stdlib_modules, module


def test_no_gh_or_git_cli_calls() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system(",
        "os.popen(",
        "shell=True",
        "eval(",
        "exec(",
    ):
        assert forbidden not in src, forbidden


def test_no_github_api_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "api.github.com",
        "anthropic",
        "openai",
        "Bearer ",
        "X-API-Key",
        "X-GitHub-Token",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(rsd)
    assert callable(rsd.collect_snapshot)
    assert callable(rsd.write_outputs)
    assert callable(rsd.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rsd.SCHEMA_VERSION, str) and rsd.SCHEMA_VERSION
    assert isinstance(rsd.MODULE_VERSION, str) and rsd.MODULE_VERSION
    assert "v3.15.16.routing_signals" in rsd.MODULE_VERSION
