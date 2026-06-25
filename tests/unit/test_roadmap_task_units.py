"""Unit tests for A20b — Implementation Unit Decomposer.

Pins:

* closed vocabularies (UNIT_KIND, RISK_CLASS, AUTHORITY_HINT,
  OPERATOR_GATE, UNIT_STATUS, TARGET_LAYER,
  FORBIDDEN_SURFACE_REASON);
* schema integrity (ImplementationUnit, UnitDecompositionProjection);
* deterministic output with injected ``generated_at_utc``;
* byte-identical output for identical input;
* atomic write only allowed under ``logs/roadmap_task_units/``;
* ``--no-write`` does not write; ``--status`` does not write;
* every A20a roadmap task has at least one implementation unit;
* phases v3.15.16..v3.15.20 each have more than one unit;
* baseline forbidden_files and forbidden_surface_reasons appear on
  every unit;
* every unit's mandatory fields are populated;
* Addendum 2 / Addendum 3 phases are not decomposed into invented
  units;
* no unit declares paper / shadow / live / broker / risk / execution
  surface as an ``expected_files`` target;
* no unit grants runtime / trading / paper / shadow / live
  authority;
* module source contains no forbidden imports or forbidden runtime
  tokens (subprocess / socket / urllib / http / requests / dashboard
  import / automation import / broker import / agent.risk import /
  agent.execution import / research.run_research import / gh pr /
  git push / git commit / os.system / eval( / exec(); the strings
  ``research/research_latest.json``, ``research/strategy_matrix.csv``,
  ``live/**``, ``paper/**``, ``shadow/**``, ``broker/**``,
  ``agent/risk/**``, ``agent/execution/**`` are intentionally allowed
  to appear inside the baseline-forbidden-files list and are not
  treated as runtime-token violations.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from reporting import roadmap_task_catalog as rtc
from reporting import roadmap_task_units as rtu


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-18T00:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)


@pytest.fixture
def catalog_snap() -> dict:
    return rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_unit_kind_vocabulary_is_closed() -> None:
    assert rtu.UNIT_KIND == (
        "reporting_module",
        "research_module",
        "governance_doc",
        "test_only",
        "schema_only",
        "diagnostic_primitive",
        "external_intelligence_source",
    )


def test_risk_class_vocabulary_matches_classifier_enum() -> None:
    assert rtu.RISK_CLASS == ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


def test_authority_hint_vocabulary_is_closed() -> None:
    assert rtu.AUTHORITY_HINT == (
        "AUTO_ALLOWED_CANDIDATE",
        "NEEDS_HUMAN_CANDIDATE",
        "PERMANENTLY_DENIED_SURFACE",
    )


def test_operator_gate_vocabulary_is_closed() -> None:
    assert rtu.OPERATOR_GATE == (
        "none",
        "operator_go_required",
        "governance_bootstrap_pr_required",
    )


def test_unit_status_vocabulary_is_closed() -> None:
    assert rtu.UNIT_STATUS == (
        "not_started",
        "ready",
        "in_flight",
        "merged",
        "blocked",
        "human_needed",
        "permanently_denied",
    )


def test_target_layer_vocabulary_matches_catalog() -> None:
    assert rtu.TARGET_LAYER == rtc.TARGET_LAYER


def test_forbidden_surface_reason_vocabulary_is_closed() -> None:
    assert "live_path" in rtu.FORBIDDEN_SURFACE_REASON
    assert "frozen_contract" in rtu.FORBIDDEN_SURFACE_REASON
    assert "claude_governance_hook" in rtu.FORBIDDEN_SURFACE_REASON
    assert "dashboard_wiring" in rtu.FORBIDDEN_SURFACE_REASON
    assert "branch_protection_config" in rtu.FORBIDDEN_SURFACE_REASON
    assert "canonical_roadmap" in rtu.FORBIDDEN_SURFACE_REASON
    assert "canonical_policy_doc" in rtu.FORBIDDEN_SURFACE_REASON
    assert "step5_blocked" in rtu.FORBIDDEN_SURFACE_REASON
    assert "level6_disabled" in rtu.FORBIDDEN_SURFACE_REASON
    assert "n5b_phase4_denied" in rtu.FORBIDDEN_SURFACE_REASON
    assert "addendum_2_not_present" in rtu.FORBIDDEN_SURFACE_REASON
    assert "addendum_3_not_present" in rtu.FORBIDDEN_SURFACE_REASON


def test_authority_hint_fail_closed_on_unknown() -> None:
    assert rtu._resolve_authority_hint("nonsense") == "NEEDS_HUMAN_CANDIDATE"
    assert rtu._resolve_authority_hint(None) == "NEEDS_HUMAN_CANDIDATE"
    assert (
        rtu._resolve_authority_hint("AUTO_ALLOWED_CANDIDATE")
        == "AUTO_ALLOWED_CANDIDATE"
    )


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_implementation_unit_field_list_exact() -> None:
    assert rtu.IMPLEMENTATION_UNIT_FIELDS == (
        "id",
        "roadmap_task_id",
        "title",
        "phase",
        "unit_kind",
        "target_layer",
        "source_requirement_ids",
        "expected_files",
        "forbidden_files",
        "forbidden_surface_reasons",
        "required_tests",
        "definition_of_done",
        "stop_conditions",
        "prerequisites",
        "risk_class",
        "authority_hint",
        "operator_gate",
        "status",
    )


def test_unit_decomposition_projection_field_list_exact() -> None:
    assert rtu.UNIT_DECOMPOSITION_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "source_catalog_schema_version",
        "implementation_units",
        "decomposition_invariants",
    )


def test_every_unit_has_every_field(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert set(u.keys()) == set(rtu.IMPLEMENTATION_UNIT_FIELDS), u


def test_projection_carries_every_required_top_level_field(snap: dict) -> None:
    for field in rtu.UNIT_DECOMPOSITION_PROJECTION_FIELDS:
        assert field in snap, field


def test_every_unit_phase_is_in_catalog_phase_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["phase"] in rtc.PHASE


def test_every_unit_target_layer_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["target_layer"] in rtu.TARGET_LAYER


def test_every_unit_unit_kind_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["unit_kind"] in rtu.UNIT_KIND


def test_every_unit_risk_class_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["risk_class"] in rtu.RISK_CLASS


def test_every_unit_authority_hint_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["authority_hint"] in rtu.AUTHORITY_HINT


def test_every_unit_operator_gate_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["operator_gate"] in rtu.OPERATOR_GATE


def test_every_unit_status_is_in_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["status"] in rtu.UNIT_STATUS


def test_every_unit_forbidden_surface_reason_in_closed_vocab(snap: dict) -> None:
    for u in snap["implementation_units"]:
        for r in u["forbidden_surface_reasons"]:
            assert r in rtu.FORBIDDEN_SURFACE_REASON, (u["id"], r)


# ---------------------------------------------------------------------------
# Mandatory field population
# ---------------------------------------------------------------------------


def test_every_unit_has_non_empty_expected_files(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["expected_files"], u["id"]


def test_every_unit_has_non_empty_forbidden_files(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["forbidden_files"], u["id"]


def test_every_unit_has_forbidden_surface_reasons(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["forbidden_surface_reasons"], u["id"]


def test_every_unit_has_required_tests(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["required_tests"], u["id"]


def test_every_unit_has_definition_of_done(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["definition_of_done"], u["id"]


def test_every_unit_has_stop_conditions(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert u["stop_conditions"], u["id"]


def test_every_unit_has_prerequisites_field_even_if_empty(snap: dict) -> None:
    for u in snap["implementation_units"]:
        assert "prerequisites" in u, u["id"]
        assert isinstance(u["prerequisites"], list), u["id"]


# ---------------------------------------------------------------------------
# Baseline forbidden-file / reason injection
# ---------------------------------------------------------------------------


_REQUIRED_FORBIDDEN_FILES = (
    ".claude/**",
    "dashboard/dashboard.py",
    "research/research_latest.json",
    "research/strategy_matrix.csv",
    "automation/live_gate.py",
    "broker/**",
    "agent/risk/**",
    "agent/execution/**",
    "live/**",
    "paper/**",
    "shadow/**",
    "trading/**",
)


@pytest.mark.parametrize("required", _REQUIRED_FORBIDDEN_FILES)
def test_every_unit_forbidden_files_contains_required_entry(
    snap: dict, required: str
) -> None:
    for u in snap["implementation_units"]:
        assert required in u["forbidden_files"], (u["id"], required)


def test_every_unit_forbidden_files_includes_frozen_contracts(
    snap: dict,
) -> None:
    for u in snap["implementation_units"]:
        assert "research/research_latest.json" in u["forbidden_files"]
        assert "research/strategy_matrix.csv" in u["forbidden_files"]


def test_every_unit_forbidden_surface_reasons_includes_baseline(
    snap: dict,
) -> None:
    for u in snap["implementation_units"]:
        reasons = set(u["forbidden_surface_reasons"])
        for required in (
            "frozen_contract",
            "live_path",
            "claude_governance_hook",
            "dashboard_wiring",
            "branch_protection_config",
        ):
            assert required in reasons, (u["id"], required)


# ---------------------------------------------------------------------------
# Expected-files safety: no live / paper / shadow / risk / broker / exec
# surface as an EXPECTED target.
# ---------------------------------------------------------------------------


_FORBIDDEN_EXPECTED_PREFIXES = (
    "automation/live_gate",
    "broker/",
    "agent/risk/",
    "agent/execution/",
    "live/",
    "paper/",
    "shadow/",
    "trading/",
    ".claude/",
    "dashboard/dashboard.py",
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def test_no_unit_expects_to_modify_forbidden_surface(snap: dict) -> None:
    for u in snap["implementation_units"]:
        for path in u["expected_files"]:
            for forbidden in _FORBIDDEN_EXPECTED_PREFIXES:
                assert not path.startswith(forbidden) and path != forbidden, (
                    u["id"],
                    path,
                )


# ---------------------------------------------------------------------------
# Phase coverage
# ---------------------------------------------------------------------------


def _units_by_task(snap: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for u in snap["implementation_units"]:
        out.setdefault(u["roadmap_task_id"], []).append(u)
    return out


def _units_by_phase(snap: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for u in snap["implementation_units"]:
        out.setdefault(u["phase"], []).append(u)
    return out


def test_every_catalog_task_has_at_least_one_unit(
    snap: dict, catalog_snap: dict
) -> None:
    by_task = _units_by_task(snap)
    for t in catalog_snap["roadmap_tasks"]:
        assert by_task.get(t["id"]), t["id"]


def test_ade_qre_017a_to_017e_each_have_one_seed_unit(snap: dict) -> None:
    by_phase = _units_by_phase(snap)
    for phase in (
        "ade_qre_017a",
        "ade_qre_017b",
        "ade_qre_017c",
        "ade_qre_017d",
        "ade_qre_017e",
    ):
        assert len(by_phase.get(phase, [])) == 1, phase


@pytest.mark.parametrize(
    "phase",
    ["v3.15.16", "v3.15.17", "v3.15.18", "v3.15.19", "v3.15.20"],
)
def test_v3_phases_have_more_than_one_unit(snap: dict, phase: str) -> None:
    by_phase = _units_by_phase(snap)
    assert len(by_phase.get(phase, [])) > 1, (
        phase,
        len(by_phase.get(phase, [])),
    )


def test_addendum_1_has_multiple_units(snap: dict) -> None:
    by_phase = _units_by_phase(snap)
    assert len(by_phase.get("addendum_1", [])) >= 3


def test_addendum_2_has_units_after_a23(snap: dict) -> None:
    """A23 made Addendum 2 repo-resident and added its implementation
    units to the decomposer seed."""
    by_phase = _units_by_phase(snap)
    units = by_phase.get("addendum_2", [])
    assert len(units) >= 1
    unit_ids = {u["id"] for u in units}
    assert (
        "u_addendum_2_state_diagnostics_governance_doc_001" in unit_ids
    )


def test_addendum_3_has_units_after_a23(snap: dict) -> None:
    by_phase = _units_by_phase(snap)
    units = by_phase.get("addendum_3", [])
    assert len(units) >= 1
    unit_ids = {u["id"] for u in units}
    assert (
        "u_addendum_3_source_candidate_registry_governance_doc_001"
        in unit_ids
    )


def test_addendum_2_3_units_attach_to_their_addendum_tasks(
    snap: dict,
) -> None:
    """Every Addendum 2 / 3 unit's roadmap_task_id must reference
    one of the two Addendum 2 / 3 catalog tasks."""
    a2_task_id = "addendum_2_state_sequential_knowledge_retrieval"
    a3_task_id = "addendum_3_source_identity_data_quality_throughput"
    for u in snap["implementation_units"]:
        if u["phase"] == "addendum_2":
            assert u["roadmap_task_id"] == a2_task_id, u["id"]
        elif u["phase"] == "addendum_3":
            assert u["roadmap_task_id"] == a3_task_id, u["id"]


def test_every_unit_roadmap_task_id_matches_catalog(
    snap: dict, catalog_snap: dict
) -> None:
    task_ids = {t["id"] for t in catalog_snap["roadmap_tasks"]}
    for u in snap["implementation_units"]:
        assert u["roadmap_task_id"] in task_ids, u["id"]


def test_unit_prerequisites_reference_known_units(snap: dict) -> None:
    unit_ids = {u["id"] for u in snap["implementation_units"]}
    for u in snap["implementation_units"]:
        for prereq in u["prerequisites"]:
            assert prereq in unit_ids, (u["id"], prereq)


def test_all_unit_ids_unique(snap: dict) -> None:
    ids = [u["id"] for u in snap["implementation_units"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Authority / runtime guarantees
# ---------------------------------------------------------------------------


def test_no_unit_grants_runtime_authority(snap: dict) -> None:
    inv = snap["decomposition_invariants"]
    for key in (
        "grants_runtime_authority",
        "grants_trading_authority",
        "grants_paper_authority",
        "grants_shadow_authority",
        "grants_broker_authority",
        "grants_risk_authority",
        "grants_live_authority",
    ):
        assert inv[key] is False, key


def test_invariants_pin_step5_blocked(snap: dict) -> None:
    inv = snap["decomposition_invariants"]
    assert inv["step5_implementation_allowed"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_invariants_pin_addendum_2_3_now_present_after_a23(
    snap: dict,
) -> None:
    """A23 flipped both absence flags to False because Addendum 2 +
    3 are now repo-resident."""
    inv = snap["decomposition_invariants"]
    assert inv["addendum_2_not_present"] is False
    assert inv["addendum_3_not_present"] is False


def test_invariants_pin_no_final_authority(snap: dict) -> None:
    """A20b itself does not call the canonical classifier and does
    not record final authority — those are A20c's responsibilities,
    pinned by ``False`` here. A20c flips them to ``True`` in its own
    projection's invariant block, not A20b's. AAC visibility is
    ``True`` post-A20d because the AAC aggregator surfaces A20b
    rows. Next-buildable-unit selection is ``True`` post-A20e
    because reporting.roadmap_next_unit selects deterministically
    over A20b candidates."""
    inv = snap["decomposition_invariants"]
    assert inv["calls_execution_authority_classifier"] is False
    assert inv["final_authority_classified"] is False
    assert inv["next_buildable_selector_present"] is True
    assert inv["aac_visibility_present"] is True


def test_invariants_pin_diagnostics_do_not_trade(snap: dict) -> None:
    inv = snap["decomposition_invariants"]
    assert inv["diagnostics_do_not_trade"] is True
    assert inv["external_data_is_not_alpha"] is True


def test_invariants_pin_no_seed_jsonl_writes(snap: dict) -> None:
    inv = snap["decomposition_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False


def test_no_unit_paper_or_shadow_runtime_activation(snap: dict) -> None:
    for u in snap["implementation_units"]:
        # No expected_files path may indicate paper/shadow runtime
        # activation surfaces — those remain blocked until an
        # explicit, future, operator-go phase.
        for path in u["expected_files"]:
            lo = path.lower()
            assert not lo.startswith("paper/"), (u["id"], path)
            assert not lo.startswith("shadow/"), (u["id"], path)
            assert not lo.startswith("live/"), (u["id"], path)
            assert not lo.startswith("trading/"), (u["id"], path)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_snapshot_deterministic_with_injected_ts() -> None:
    a = rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rtu.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_unit_order_stable(snap: dict) -> None:
    sorted_pairs = [(u["phase"], u["id"]) for u in snap["implementation_units"]]
    assert sorted_pairs == sorted(sorted_pairs)


def test_snapshot_includes_source_catalog_schema_version(
    snap: dict, catalog_snap: dict
) -> None:
    assert (
        snap["source_catalog_schema_version"] == catalog_snap["schema_version"]
    )


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rtu._atomic_write_json(bad, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rtu._atomic_write_json(good, {"x": 1})
    assert good.is_file()
    assert json.loads(good.read_text(encoding="utf-8")) == {"x": 1}


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rtu._atomic_write_json(target, {"x": 1})
    rtu._atomic_write_json(target, {"x": 2})
    siblings = list(target.parent.iterdir())
    assert siblings == [target], siblings


def test_atomic_write_refuses_frozen_contract_paths(tmp_path: Path) -> None:
    """Reassert that the atomic write helper rejects every
    frozen-contract path, even though the strings appear inside
    the baseline forbidden_files list (which is allowed)."""
    for forbidden in (
        "research/research_latest.json",
        "research/strategy_matrix.csv",
    ):
        target = tmp_path / forbidden
        target.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError):
            rtu._atomic_write_json(target, {"x": 1})


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    monkeypatch.setattr(rtu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtu, "ARTIFACT_DIR", sentinel.parent)
    rc = rtu.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert '"roadmap_task_units"' in out


def test_cli_status_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    monkeypatch.setattr(rtu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtu, "ARTIFACT_DIR", sentinel.parent)
    rc = rtu.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_task_units" in out
    assert "step5_implementation_allowed=False" in out
    # A23 flipped both absence flags to False.
    assert "addendum_2_not_present=False" in out
    assert "addendum_3_not_present=False" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    monkeypatch.setattr(rtu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtu, "ARTIFACT_DIR", sentinel.parent)
    rc = rtu.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_task_units"
    assert payload["module_version"].startswith("v3.15.16.A20b")


def test_cli_indent_zero_compact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_units" / "latest.json"
    monkeypatch.setattr(rtu, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtu, "ARTIFACT_DIR", sentinel.parent)
    rc = rtu.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rtu.__file__).read_text(encoding="utf-8")


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


def test_no_forbidden_module_imports() -> None:
    src = _module_source()
    for forbidden in (
        "from dashboard",
        "import dashboard",
        "from automation",
        "import automation",
        "from broker",
        "import broker",
        "from agent.risk",
        "import agent.risk",
        "from agent.execution",
        "import agent.execution",
        "from research.run_research",
        "import research.run_research",
        "from reporting.intelligent_routing",
        "import reporting.intelligent_routing",
        "from reporting.execution_authority",
        "import reporting.execution_authority",
        "from reporting.development_queue_admission_policy",
        "import reporting.development_queue_admission_policy",
        "from reporting.development_agent_activity_timeline",
        "import reporting.development_agent_activity_timeline",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_runtime_tokens() -> None:
    """Scans for runtime *use* tokens — process execution, dynamic
    eval / exec, shell invocation. Docstring mentions of ``gh`` /
    ``git`` / ``subprocess`` as negative guarantees are explicitly
    allowed (they are pinned by the import / subprocess scans
    above). The strings ``gh pr create``, ``git push``,
    ``git commit`` legitimately appear in baseline DoD bullets as
    descriptive text for the future PR's lifecycle; they are not
    runtime calls from this module.
    """
    src = _module_source()
    for forbidden in (
        "subprocess.run(",
        "subprocess.Popen(",
        "os.system(",
        "os.popen(",
        "shell=True",
        "eval(",
        "exec(",
    ):
        assert forbidden not in src, forbidden


def test_no_llm_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "anthropic",
        "openai",
        "Bearer ",
        "X-API-Key",
    ):
        assert forbidden not in src, forbidden


def _module_imports() -> list[str]:
    """Return the list of dotted module names imported by the A20b
    module via static AST analysis. Distinguishes real import
    statements from docstring mentions of the same names."""
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


def test_module_does_not_call_execution_authority_classifier() -> None:
    """A20b must NOT import or call execution_authority.classify.
    Real authority classification is A20c's job. We check actual
    imports via AST rather than docstring mentions of the module
    name, since the docstring legitimately lists
    ``reporting.execution_authority`` as a forbidden import.
    """
    imports = _module_imports()
    for forbidden_import in imports:
        assert "execution_authority" not in forbidden_import, forbidden_import
    src = _module_source()
    # Real call patterns: a) `ea.classify(...)` if imported aliased,
    # b) `execution_authority.classify(...)` if imported plain. The
    # docstring uses backticked Sphinx-style references, never the
    # raw call form.
    assert "ea.classify(" not in src
    # Bare `execution_authority.classify(` would indicate a real
    # call. Docstring mentions use the form
    # ``execution_authority.classify(...)`` inside double backticks.
    # Strip the docstring before scanning to avoid false positives.
    import ast as _ast

    tree = _ast.parse(src)
    module_doc = _ast.get_docstring(tree) or ""
    code_only = src.replace(module_doc, "")
    assert "execution_authority.classify(" not in code_only


def test_module_does_not_touch_canonical_roadmap_files_at_runtime() -> None:
    """A20b derives task identity from the in-memory catalog. It must
    not parse canonical roadmap files at runtime — those reads belong
    only to A20a + the Roadmap Intake Bridge. We check by AST: there
    are zero ``open(...)`` / ``read_text(...)`` / ``read_bytes(...)``
    / ``Path(canonical_roadmap_path)`` call sites in the module
    code. Docstring mentions of the canonical roadmap paths as
    negative guarantees are explicitly allowed.
    """
    import ast as _ast

    src = _module_source()
    tree = _ast.parse(src)
    module_doc = _ast.get_docstring(tree) or ""

    # Walk the AST for any call site invoking common file-read APIs.
    # ``open(...)`` / ``Path(...).read_text(...)`` / ``read_bytes`` /
    # ``read``. The canonical roadmap paths legitimately appear in
    # the BASELINE_FORBIDDEN_FILES tuple as forbidden-path string
    # literals; the semantic invariant is that they are never
    # passed to any file-read call, which is enforced here at the
    # AST level rather than via fragile substring scans.
    forbidden_call_names = {"open", "read_text", "read_bytes", "read"}
    found_calls: list[str] = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        if isinstance(node.func, _ast.Attribute):
            name = node.func.attr
        elif isinstance(node.func, _ast.Name):
            name = node.func.id
        else:
            continue
        if name in forbidden_call_names:
            found_calls.append(name)
    assert not found_calls, found_calls
    # silence unused-variable lint for module_doc
    assert isinstance(module_doc, str)


def test_module_imports_cleanly() -> None:
    importlib.reload(rtu)
    assert callable(rtu.collect_snapshot)
    assert callable(rtu.write_outputs)
    assert callable(rtu.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rtu.SCHEMA_VERSION, str) and rtu.SCHEMA_VERSION
    assert isinstance(rtu.MODULE_VERSION, str) and rtu.MODULE_VERSION
    assert rtu.MODULE_VERSION.endswith("A20b")


# ---------------------------------------------------------------------------
# Governance doc cross-references (A20b extension)
# ---------------------------------------------------------------------------


def _governance_doc_text() -> str:
    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "governance"
        / "roadmap_task_catalog.md"
    )
    return doc.read_text(encoding="utf-8").lower()


def test_governance_doc_documents_a20b() -> None:
    text = _governance_doc_text()
    for needle in (
        "a20b",
        "implementationunit",
        "pr-sized",
        "forbidden_files",
        "forbidden_surface_reasons",
        "required_tests",
        "definition of done",
        "stop conditions",
        "prerequisites",
        "authority_hint",
    ):
        assert needle in text, needle


def test_governance_doc_pins_a20b_no_final_authority() -> None:
    text = _governance_doc_text()
    assert "a20c" in text
    # The doc must somewhere make clear that A20b's authority_hint
    # is not the final authority classification — A20c integrates
    # the real classifier.
    not_final_phrasing = (
        "authority_hint is not final authority",
        "authority_hint is not final",
        "not a substitute for the real classifier",
        "not the final authority",
        "is **not** a substitute",
        "is not a substitute",
    )
    assert any(p in text for p in not_final_phrasing), text[:500]


def test_governance_doc_pins_no_dashboard_or_aac_changes_in_a20b() -> None:
    text = _governance_doc_text()
    assert "a20d" in text
    assert "aac" in text or "agent activity" in text


def test_governance_doc_pins_no_next_buildable_selector_in_a20b() -> None:
    text = _governance_doc_text()
    assert "a20e" in text
    assert "next-buildable" in text or "next buildable" in text


# ---------------------------------------------------------------------------
# Queue-status update: u_v3_15_16_diagnostic_routing_signals_schema_001
# was implemented and merged via PR #250. The A20 pipeline is deterministic
# and read-only — it does not auto-discover merged PRs — so the unit's
# status was advanced manually in the seed via a small follow-up PR.
# ---------------------------------------------------------------------------


_ROUTING_SIGNALS_SCHEMA_UNIT_ID = (
    "u_v3_15_16_diagnostic_routing_signals_schema_001"
)


def test_routing_signals_schema_unit_status_is_merged(snap: dict) -> None:
    """After the queue-status update PR, A20b emits this unit with
    ``status="merged"``. The A20e selector must therefore stop
    recommending it."""
    rows = [
        u
        for u in snap["implementation_units"]
        if u["id"] == _ROUTING_SIGNALS_SCHEMA_UNIT_ID
    ]
    assert len(rows) == 1
    assert rows[0]["status"] == "merged"


def test_routing_signals_schema_unit_retains_full_metadata(snap: dict) -> None:
    """Queue-status update is narrow: only the status field flipped.
    All other unit metadata that downstream consumers (A20c, A20d,
    A20e) depend on must remain intact."""
    rows = [
        u
        for u in snap["implementation_units"]
        if u["id"] == _ROUTING_SIGNALS_SCHEMA_UNIT_ID
    ]
    assert len(rows) == 1
    unit = rows[0]
    # Mandatory list / scalar fields A20c and A20e read.
    assert unit["expected_files"], unit
    assert unit["forbidden_files"], unit
    assert unit["required_tests"], unit
    assert unit["definition_of_done"], unit
    assert unit["stop_conditions"], unit
    assert isinstance(unit["authority_hint"], str) and unit["authority_hint"]
    # Authority hint matches the original A20b seed.
    assert unit["authority_hint"] == "AUTO_ALLOWED_CANDIDATE"
    assert unit["operator_gate"] == "none"
    assert unit["risk_class"] == "LOW"
    assert unit["phase"] == "v3.15.16"
    assert unit["roadmap_task_id"] == "phase_v3_15_16"


#: Set of unit ids that have been queue-status-advanced to
#: ``merged`` via prior follow-up PRs. Each entry must point at a
#: real implementation PR that landed on ``main``. This set grows
#: monotonically as the queue progresses; it never shrinks except
#: in the extremely rare case of an operator-approved revert PR
#: (which is out of scope here).
_MERGED_UNIT_IDS: frozenset[str] = frozenset(
    {
        # ADE-QRE-017A maturity-matrix reporter merged via the current queue item PR.
        "u_ade_qre_017a_maturity_matrix_reporter_001",
        # ADE-QRE-017B evidence-density reporter merged via the current queue item PR.
        "u_ade_qre_017b_evidence_density_inventory_001",
        # ADE-QRE-017C reason-record maturity reporter merged via the current queue item PR.
        "u_ade_qre_017c_reason_record_maturity_reporter_001",
        # ADE-QRE-017D routing/sampling readiness reporter merged via the current queue item PR.
        "u_ade_qre_017d_readiness_population_reporter_001",
        # PR #250 (merge SHA fcb1abb) + PR #251 queue-status update.
        "u_v3_15_16_diagnostic_routing_signals_schema_001",
        # PR #252 (merge SHA 6f588a8) + this queue-status update PR.
        "u_v3_15_16_routing_explanation_reporter_001",
    }
)


def test_other_units_unchanged_by_status_update(snap: dict) -> None:
    """Each queue-status update PR flips exactly one unit's status
    to ``merged``. Every other unit in the seed must still carry a
    status drawn from the closed UNIT_STATUS vocabulary and must
    not have been altered to ``merged`` by accident. The expected
    merged set is :data:`_MERGED_UNIT_IDS`."""
    for u in snap["implementation_units"]:
        assert u["status"] in rtu.UNIT_STATUS, u
        if u["id"] in _MERGED_UNIT_IDS:
            assert u["status"] == "merged", u["id"]
        else:
            # Defence-in-depth: no other unit silently flipped to merged.
            assert u["status"] != "merged", u["id"]


def test_routing_signals_schema_unit_is_listed_exactly_once(snap: dict) -> None:
    ids = [u["id"] for u in snap["implementation_units"]]
    assert ids.count(_ROUTING_SIGNALS_SCHEMA_UNIT_ID) == 1


def test_downstream_v3_15_16_units_still_reference_merged_unit(
    snap: dict,
) -> None:
    """The two downstream v3.15.16 units list the routing-signals
    schema unit as a prerequisite. After the status update the
    prerequisite edge is preserved (still listed) and A20e can now
    treat it as satisfied because the prereq unit's status is
    ``merged``."""
    downstream = [
        u
        for u in snap["implementation_units"]
        if u["id"]
        in (
            "u_v3_15_16_routing_explanation_reporter_001",
            "u_v3_15_16_routing_governance_doc_001",
        )
    ]
    assert len(downstream) == 2
    for u in downstream:
        assert _ROUTING_SIGNALS_SCHEMA_UNIT_ID in u["prerequisites"], u["id"]


def test_ade_qre_017_wave_prerequisites_form_linear_chain(snap: dict) -> None:
    by_id = {u["id"]: u for u in snap["implementation_units"]}
    assert by_id["u_ade_qre_017a_maturity_matrix_reporter_001"]["prerequisites"] == []
    assert by_id["u_ade_qre_017b_evidence_density_inventory_001"]["prerequisites"] == [
        "u_ade_qre_017a_maturity_matrix_reporter_001"
    ]
    assert by_id["u_ade_qre_017c_reason_record_maturity_reporter_001"]["prerequisites"] == [
        "u_ade_qre_017b_evidence_density_inventory_001"
    ]
    assert by_id["u_ade_qre_017d_readiness_population_reporter_001"]["prerequisites"] == [
        "u_ade_qre_017c_reason_record_maturity_reporter_001"
    ]
    assert by_id["u_ade_qre_017e_kpi_snapshot_reporter_001"]["prerequisites"] == [
        "u_ade_qre_017d_readiness_population_reporter_001"
    ]


def test_ade_qre_017a_through_017d_units_are_merged_and_future_wave_units_not_started(
    snap: dict,
) -> None:
    by_id = {u["id"]: u for u in snap["implementation_units"]}
    assert by_id["u_ade_qre_017a_maturity_matrix_reporter_001"]["status"] == "merged"
    assert by_id["u_ade_qre_017b_evidence_density_inventory_001"]["status"] == "merged"
    assert by_id["u_ade_qre_017c_reason_record_maturity_reporter_001"]["status"] == "merged"
    assert by_id["u_ade_qre_017d_readiness_population_reporter_001"]["status"] == "merged"
    assert by_id["u_ade_qre_017e_kpi_snapshot_reporter_001"]["status"] == "not_started"


# ---------------------------------------------------------------------------
# Queue-status update: u_v3_15_16_routing_explanation_reporter_001 was
# implemented and merged via PR #252 (merge SHA
# 6f588a89b43a2cfec40f92252bde530220877b37). The status is advanced
# manually in this follow-up PR because A20 projections do not
# auto-discover merged PRs.
# ---------------------------------------------------------------------------


_ROUTING_EXPLANATION_REPORTER_UNIT_ID = (
    "u_v3_15_16_routing_explanation_reporter_001"
)


def test_routing_explanation_reporter_unit_status_is_merged(snap: dict) -> None:
    """After the queue-status update PR, A20b emits this unit with
    ``status="merged"``. The A20e selector must therefore stop
    recommending it and advance to the next eligible v3.15.16
    unit."""
    rows = [
        u
        for u in snap["implementation_units"]
        if u["id"] == _ROUTING_EXPLANATION_REPORTER_UNIT_ID
    ]
    assert len(rows) == 1
    assert rows[0]["status"] == "merged"


def test_routing_explanation_reporter_unit_retains_full_metadata(
    snap: dict,
) -> None:
    """Queue-status update is narrow: only the status field flipped.
    All other unit metadata that downstream consumers (A20c, A20d,
    A20e) depend on must remain intact."""
    rows = [
        u
        for u in snap["implementation_units"]
        if u["id"] == _ROUTING_EXPLANATION_REPORTER_UNIT_ID
    ]
    assert len(rows) == 1
    unit = rows[0]
    assert unit["expected_files"], unit
    assert unit["forbidden_files"], unit
    assert unit["required_tests"], unit
    assert unit["definition_of_done"], unit
    assert unit["stop_conditions"], unit
    assert isinstance(unit["authority_hint"], str) and unit["authority_hint"]
    assert unit["authority_hint"] == "AUTO_ALLOWED_CANDIDATE"
    assert unit["operator_gate"] == "none"
    assert unit["risk_class"] == "LOW"
    assert unit["phase"] == "v3.15.16"
    assert unit["roadmap_task_id"] == "phase_v3_15_16"
    # The prerequisite edge from the explanation reporter to the
    # routing-signals-schema unit must remain — A20e relies on it
    # to treat the prerequisite as satisfied (the prereq is also
    # merged).
    assert (
        _ROUTING_SIGNALS_SCHEMA_UNIT_ID in unit["prerequisites"]
    ), unit


def test_routing_explanation_reporter_unit_is_listed_exactly_once(
    snap: dict,
) -> None:
    ids = [u["id"] for u in snap["implementation_units"]]
    assert ids.count(_ROUTING_EXPLANATION_REPORTER_UNIT_ID) == 1


def test_prior_merged_routing_signals_schema_unit_still_merged(
    snap: dict,
) -> None:
    """PR #251 marked the routing-signals-schema unit as merged.
    PR #252's follow-up status update must NOT undo that previous
    transition. Both merged units must be ``status="merged"`` on
    the same seed."""
    schema_rows = [
        u
        for u in snap["implementation_units"]
        if u["id"] == _ROUTING_SIGNALS_SCHEMA_UNIT_ID
    ]
    assert len(schema_rows) == 1
    assert schema_rows[0]["status"] == "merged"


def test_merged_set_contains_exactly_the_expected_unit_ids(snap: dict) -> None:
    """Every unit with status==merged must appear in the explicit
    :data:`_MERGED_UNIT_IDS` set. This prevents accidental merged
    drift in either direction (forgotten status flip OR silent
    bonus merged)."""
    merged_in_snap = {
        u["id"]
        for u in snap["implementation_units"]
        if u["status"] == "merged"
    }
    assert merged_in_snap == set(_MERGED_UNIT_IDS), merged_in_snap
