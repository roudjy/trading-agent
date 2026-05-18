"""Unit tests for v3.15.16 Intelligent Routing Layer — read-only
routing-decision explanation reporter
(``reporting.routing_explanation``).

Pins:

* closed vocabularies (ROUTING_EXPLANATION_STATUS,
  ROUTING_EXPLANATION_REASON_KIND, ROUTING_EXPLANATION_EFFECT,
  ROUTING_EXPLANATION_TARGET, ROUTING_EXPLANATION_SOURCE);
* schema integrity (RoutingExplanationReason, RoutingExplanation,
  RoutingExplanationProjection field tuples);
* deterministic output with injected ``generated_at_utc``;
* byte-identical output for identical input;
* atomic write only under ``logs/routing_explanation/``;
* ``--no-write`` does not write; ``--status`` does not write;
* every upstream diagnostic-routing signal gets exactly one
  explanation;
* explanations sorted deterministically by ``signal_id``;
* every explanation has at least one reason;
* every explanation has ``read_only=True`` and
  ``mutation_allowed=False``;
* ``supports_exploration`` / ``suppresses_exploration`` /
  ``requires_confirmation`` follow closed deterministic semantics
  keyed on the upstream signal's ``direction``;
* projection_invariants pin all required authority and read-only
  flags;
* no forbidden imports or runtime tokens appear in the module
  source.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import intelligent_routing_diagnostic_signals as rsd
from reporting import routing_explanation as rxn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T13:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rxn.collect_snapshot(generated_at_utc=_FROZEN_UTC)


@pytest.fixture
def upstream_snap() -> dict:
    return rsd.collect_snapshot(generated_at_utc=_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_routing_explanation_status_is_closed_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_STATUS == (
        "advisory_prioritize",
        "advisory_deprioritize",
        "advisory_suppress",
        "advisory_require_confirmation",
        "advisory_neutral",
        "informational",
    )


def test_routing_explanation_reason_kind_is_closed_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_REASON_KIND == (
        "direction_advice",
        "expected_information_gain",
        "dead_zone_risk",
        "orthogonality",
        "public_data_quality",
        "confirmation_requirement",
        "missing_input_fallback",
    )


def test_routing_explanation_effect_is_closed_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_EFFECT == (
        "supports_exploration",
        "suppresses_exploration",
        "requires_confirmation",
        "lowers_priority",
        "elevates_evidence_requirement",
        "neutral",
    )


def test_routing_explanation_target_mirrors_upstream() -> None:
    """Target-layer vocabulary is verbatim re-export from the
    upstream signal module."""
    assert rxn.ROUTING_EXPLANATION_TARGET == rsd.ROUTING_SIGNAL_TARGET_LAYER


def test_routing_explanation_source_is_closed_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_SOURCE == (
        "reporting.intelligent_routing_diagnostic_signals",
        "reporting.routing_explanation",
        "logs/intelligent_routing_diagnostic_signals/latest.json",
    )


def test_direction_status_mapping_is_total_over_upstream_directions() -> None:
    """Every upstream direction must map to an explanation status."""
    for direction in rsd.ROUTING_SIGNAL_DIRECTION:
        assert direction in rxn._DIRECTION_TO_STATUS, direction
        assert (
            rxn._DIRECTION_TO_STATUS[direction]
            in rxn.ROUTING_EXPLANATION_STATUS
        )


def test_direction_effect_mapping_is_total_over_upstream_directions() -> None:
    for direction in rsd.ROUTING_SIGNAL_DIRECTION:
        assert direction in rxn._DIRECTION_TO_EFFECT, direction
        assert (
            rxn._DIRECTION_TO_EFFECT[direction]
            in rxn.ROUTING_EXPLANATION_EFFECT
        )


def test_direction_aggregate_mapping_is_total_over_upstream_directions() -> None:
    for direction in rsd.ROUTING_SIGNAL_DIRECTION:
        assert direction in rxn._DIRECTION_TO_AGGREGATE, direction
        triple = rxn._DIRECTION_TO_AGGREGATE[direction]
        assert isinstance(triple, tuple) and len(triple) == 3
        for v in triple:
            assert isinstance(v, bool)


def test_family_reason_mapping_is_total_over_upstream_families() -> None:
    """Every upstream signal family must have a family-specific
    reason mapping with kind + effect drawn from closed vocab."""
    for family in rsd.ROUTING_SIGNAL_FAMILY:
        assert family in rxn._FAMILY_TO_REASON, family
        kind, effect = rxn._FAMILY_TO_REASON[family]
        assert kind in rxn.ROUTING_EXPLANATION_REASON_KIND, (family, kind)
        assert effect in rxn.ROUTING_EXPLANATION_EFFECT, (family, effect)
        # Family also maps to a known upstream effect field name.
        assert family in rxn._FAMILY_TO_REASON_FIELD, family


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_routing_explanation_reason_field_list_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_REASON_FIELDS == (
        "kind",
        "signal_id",
        "signal_family",
        "reason",
        "effect",
        "source",
    )


def test_routing_explanation_field_list_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_FIELDS == (
        "id",
        "signal_id",
        "signal_family",
        "title",
        "summary",
        "status",
        "target",
        "reasons",
        "supports_exploration",
        "suppresses_exploration",
        "requires_confirmation",
        "read_only",
        "mutation_allowed",
    )


def test_routing_explanation_projection_field_list_exact() -> None:
    assert rxn.ROUTING_EXPLANATION_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "source_signal_schema_version",
        "explanations",
        "projection_invariants",
    )


def test_every_explanation_has_every_field(snap: dict) -> None:
    for e in snap["explanations"]:
        assert set(e.keys()) == set(rxn.ROUTING_EXPLANATION_FIELDS), e


def test_every_reason_has_every_field(snap: dict) -> None:
    for e in snap["explanations"]:
        for r in e["reasons"]:
            assert set(r.keys()) == set(
                rxn.ROUTING_EXPLANATION_REASON_FIELDS
            ), r


def test_projection_carries_every_top_level_field(snap: dict) -> None:
    for field in rxn.ROUTING_EXPLANATION_PROJECTION_FIELDS:
        assert field in snap, field


def test_every_field_value_in_closed_vocab(snap: dict) -> None:
    for e in snap["explanations"]:
        assert e["status"] in rxn.ROUTING_EXPLANATION_STATUS
        assert e["target"] in rxn.ROUTING_EXPLANATION_TARGET
        assert e["signal_family"] in rsd.ROUTING_SIGNAL_FAMILY
        for r in e["reasons"]:
            assert r["kind"] in rxn.ROUTING_EXPLANATION_REASON_KIND
            assert r["effect"] in rxn.ROUTING_EXPLANATION_EFFECT
            assert r["source"] in rxn.ROUTING_EXPLANATION_SOURCE
            assert r["signal_family"] in rsd.ROUTING_SIGNAL_FAMILY


# ---------------------------------------------------------------------------
# Coverage and ordering
# ---------------------------------------------------------------------------


def test_one_explanation_per_upstream_signal(
    snap: dict, upstream_snap: dict
) -> None:
    upstream_ids = sorted(s["id"] for s in upstream_snap["signals"])
    explanation_signal_ids = sorted(
        e["signal_id"] for e in snap["explanations"]
    )
    assert explanation_signal_ids == upstream_ids


def test_explanation_count_matches_upstream_signal_count(
    snap: dict, upstream_snap: dict
) -> None:
    assert len(snap["explanations"]) == len(upstream_snap["signals"])


def test_explanations_sorted_by_signal_id(snap: dict) -> None:
    ids = [e["signal_id"] for e in snap["explanations"]]
    assert ids == sorted(ids)


def test_explanation_ids_are_unique(snap: dict) -> None:
    ids = [e["id"] for e in snap["explanations"]]
    assert len(ids) == len(set(ids))


def test_explanation_id_derives_from_signal_id(snap: dict) -> None:
    for e in snap["explanations"]:
        assert e["id"] == f"re_{e['signal_id']}", e


# ---------------------------------------------------------------------------
# Reasons content
# ---------------------------------------------------------------------------


def test_every_explanation_has_at_least_one_reason(snap: dict) -> None:
    for e in snap["explanations"]:
        assert isinstance(e["reasons"], list)
        assert len(e["reasons"]) >= 1, e["id"]


def test_every_explanation_has_three_reasons_today(snap: dict) -> None:
    """Today the deterministic builder emits exactly three reasons:
    direction_advice, family_specific, missing_input_fallback. If a
    future operator-approved change adds more reasons, this test is
    the canonical place to update the expected count."""
    for e in snap["explanations"]:
        assert len(e["reasons"]) == 3, (e["id"], len(e["reasons"]))


def test_every_explanation_has_direction_advice_reason(snap: dict) -> None:
    for e in snap["explanations"]:
        kinds = [r["kind"] for r in e["reasons"]]
        assert "direction_advice" in kinds, e["id"]


def test_every_explanation_has_missing_input_fallback_reason(
    snap: dict,
) -> None:
    for e in snap["explanations"]:
        kinds = [r["kind"] for r in e["reasons"]]
        assert "missing_input_fallback" in kinds, e["id"]


def test_direction_advice_reason_effect_matches_direction_map(
    snap: dict, upstream_snap: dict
) -> None:
    upstream_by_id = {s["id"]: s for s in upstream_snap["signals"]}
    for e in snap["explanations"]:
        upstream = upstream_by_id[e["signal_id"]]
        expected_effect = rxn._DIRECTION_TO_EFFECT[upstream["direction"]]
        direction_reasons = [
            r for r in e["reasons"] if r["kind"] == "direction_advice"
        ]
        assert len(direction_reasons) == 1
        assert direction_reasons[0]["effect"] == expected_effect


def test_family_specific_reason_matches_family_map(
    snap: dict, upstream_snap: dict
) -> None:
    upstream_by_id = {s["id"]: s for s in upstream_snap["signals"]}
    for e in snap["explanations"]:
        upstream = upstream_by_id[e["signal_id"]]
        family = upstream["family"]
        expected_kind, expected_effect = rxn._FAMILY_TO_REASON[family]
        # The family-specific reason is the one with the
        # _FAMILY_TO_REASON[family][0] kind (i.e., not
        # direction_advice and not missing_input_fallback).
        family_reasons = [
            r
            for r in e["reasons"]
            if r["kind"] not in {"direction_advice", "missing_input_fallback"}
        ]
        assert len(family_reasons) == 1, e["id"]
        r = family_reasons[0]
        assert r["kind"] == expected_kind, (e["id"], r)
        assert r["effect"] == expected_effect, (e["id"], r)
        assert r["source"] == "reporting.routing_explanation"


# ---------------------------------------------------------------------------
# Read-only / mutation_allowed semantics
# ---------------------------------------------------------------------------


def test_every_explanation_is_read_only(snap: dict) -> None:
    for e in snap["explanations"]:
        assert e["read_only"] is True


def test_every_explanation_has_mutation_allowed_false(snap: dict) -> None:
    for e in snap["explanations"]:
        assert e["mutation_allowed"] is False


# ---------------------------------------------------------------------------
# Aggregate boolean semantics (supports / suppresses / requires_confirmation)
# ---------------------------------------------------------------------------


def test_aggregate_booleans_match_direction_aggregate_map(
    snap: dict, upstream_snap: dict
) -> None:
    upstream_by_id = {s["id"]: s for s in upstream_snap["signals"]}
    for e in snap["explanations"]:
        upstream = upstream_by_id[e["signal_id"]]
        direction = upstream["direction"]
        supports, suppresses, requires_confirmation = (
            rxn._DIRECTION_TO_AGGREGATE[direction]
        )
        assert e["supports_exploration"] is supports, (e["id"], direction)
        assert e["suppresses_exploration"] is suppresses, (e["id"], direction)
        assert e["requires_confirmation"] is requires_confirmation, (
            e["id"],
            direction,
        )


def test_status_matches_direction_status_map(
    snap: dict, upstream_snap: dict
) -> None:
    upstream_by_id = {s["id"]: s for s in upstream_snap["signals"]}
    for e in snap["explanations"]:
        upstream = upstream_by_id[e["signal_id"]]
        assert (
            e["status"] == rxn._DIRECTION_TO_STATUS[upstream["direction"]]
        ), e


def test_no_explanation_is_simultaneously_supports_and_suppresses(
    snap: dict,
) -> None:
    """Defence-in-depth: a single explanation cannot both support
    and suppress exploration."""
    for e in snap["explanations"]:
        assert not (
            e["supports_exploration"] and e["suppresses_exploration"]
        ), e["id"]


# ---------------------------------------------------------------------------
# Projection invariants
# ---------------------------------------------------------------------------


def test_invariants_pin_diagnostics_do_not_trade(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["diagnostics_do_not_trade"] is True


def test_invariants_pin_external_data_is_not_alpha(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["external_data_is_not_alpha"] is True


def test_invariants_pin_read_only_and_mutation_allowed_false(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["read_only"] is True
    assert inv["mutation_allowed"] is False


def test_invariants_pin_no_runtime_trading_authority(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_runtime_trading_authority"] is True


def test_invariants_pin_no_campaign_queue_mutation(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_campaign_queue_mutation"] is True


def test_invariants_pin_no_actual_routing_decision(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_actual_routing_decision"] is True


def test_invariants_pin_no_strategy_generation(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_strategy_generation"] is True


def test_invariants_pin_no_step5_runtime(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_step5_runtime"] is True
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_invariants_pin_no_level6(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_level6"] is True


def test_invariants_pin_no_production_merge_authority(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_production_merge_authority"] is True


def test_invariants_pin_no_routing_mutation(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_routing_mutation"] is True
    assert inv["no_research_runtime_change"] is True


def test_invariants_pin_no_branch_pr_merge_deploy(snap: dict) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_branch_creation"] is True
    assert inv["no_pr_creation"] is True
    assert inv["no_merge_or_deploy"] is True


def test_invariants_pin_no_mutation_routes_or_approval_buttons(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["no_mutation_routes"] is True
    assert inv["no_approval_buttons"] is True


def test_invariants_pin_writes_only_routing_explanation_log(
    snap: dict,
) -> None:
    inv = snap["projection_invariants"]
    assert inv["writes_only_routing_explanation_log"] is True


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rxn.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rxn.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rxn.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rxn.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_upstream_schema_version_recorded(
    snap: dict, upstream_snap: dict
) -> None:
    assert (
        snap["source_signal_schema_version"]
        == upstream_snap["schema_version"]
    )


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rxn._atomic_write_json(bad, {"x": 1})


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rxn._atomic_write_json(target, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "routing_explanation" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rxn._atomic_write_json(good, {"x": 1})
    assert good.is_file()


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "routing_explanation" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rxn._atomic_write_json(target, {"x": 1})
    rxn._atomic_write_json(target, {"x": 2})
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
    sentinel = tmp_path / "logs" / "routing_explanation" / "latest.json"
    monkeypatch.setattr(rxn, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rxn, "ARTIFACT_DIR", sentinel.parent)
    rc = rxn.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"routing_explanation"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "routing_explanation" / "latest.json"
    monkeypatch.setattr(rxn, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rxn, "ARTIFACT_DIR", sentinel.parent)
    rc = rxn.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "routing_explanation" in out
    assert "diagnostics_do_not_trade=True" in out
    assert "external_data_is_not_alpha=True" in out
    assert "no_runtime_trading_authority=True" in out
    assert "no_actual_routing_decision=True" in out
    assert "no_campaign_queue_mutation=True" in out
    assert "no_strategy_generation=True" in out
    assert "read_only=True" in out
    assert "mutation_allowed=False" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "routing_explanation" / "latest.json"
    monkeypatch.setattr(rxn, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rxn, "ARTIFACT_DIR", sentinel.parent)
    rc = rxn.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "routing_explanation"
    assert payload["module_version"].startswith("v3.15.16.routing_explanation")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinel = tmp_path / "logs" / "routing_explanation" / "latest.json"
    monkeypatch.setattr(rxn, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rxn, "ARTIFACT_DIR", sentinel.parent)
    rc = rxn.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rxn.__file__).read_text(encoding="utf-8")


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
        "reporting.intelligent_routing",  # the legacy module path, distinct from intelligent_routing_diagnostic_signals
        "reporting.development_queue_admission_policy",
        "reporting.development_agent_activity_timeline",
        "reporting.execution_authority",
        "reporting.roadmap_task_catalog",
        "reporting.roadmap_task_units",
        "reporting.roadmap_unit_authority",
        "reporting.roadmap_next_unit",
    )
    for module in _module_imports():
        # The legitimate import this module uses is
        # ``reporting.intelligent_routing_diagnostic_signals``.
        # That is NOT a sub-module of ``reporting.intelligent_routing``;
        # the underscore boundary matters.
        if module.startswith("reporting.intelligent_routing_diagnostic_signals"):
            continue
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_imports_only_canonical_upstream() -> None:
    """A20-pipeline style: stdlib + exactly the one upstream
    reporting module."""
    allowed_reporting_imports = {
        "reporting.intelligent_routing_diagnostic_signals",
    }
    for module in _module_imports():
        if module.startswith("reporting."):
            assert module in allowed_reporting_imports, module


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
    importlib.reload(rxn)
    assert callable(rxn.collect_snapshot)
    assert callable(rxn.write_outputs)
    assert callable(rxn.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rxn.SCHEMA_VERSION, str) and rxn.SCHEMA_VERSION
    assert isinstance(rxn.MODULE_VERSION, str) and rxn.MODULE_VERSION
    assert "v3.15.16.routing_explanation" in rxn.MODULE_VERSION
