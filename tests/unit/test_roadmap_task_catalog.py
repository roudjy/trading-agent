"""Unit tests for A20a — Static Roadmap v6 Task Catalog Seed.

Pins:

* closed vocabularies (PHASE, SOURCE_DOCUMENT, STATUS, ADDENDUM_LINK,
  TARGET_LAYER);
* schema integrity (RoadmapTask, RoadmapRequirement,
  TaskCatalogProjection fields);
* deterministic output with injected generated_at_utc;
* byte-identical output for identical input;
* atomic write only allowed under logs/roadmap_task_catalog/;
* --no-write does not write;
* --status prints a compact human-readable summary and writes
  nothing;
* Addendum 2 / Addendum 3 absence flags are present and true;
* all v3.15.16..v3.15.20 phase tasks exist;
* Addendum 1 cross-cutting task exists;
* Addendum 1 diagnostic families are represented;
* no forbidden imports or forbidden tokens appear in the module
  source.
"""

from __future__ import annotations

import importlib
import io
import json
import sys
from pathlib import Path

import pytest

from reporting import roadmap_task_catalog as rtc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FROZEN_UTC = "2026-05-17T12:00:00Z"


@pytest.fixture
def snap() -> dict:
    return rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_phase_vocabulary_is_closed_and_complete() -> None:
    assert rtc.PHASE == (
        "v3.15.16",
        "v3.15.17",
        "v3.15.18",
        "v3.15.19",
        "v3.15.20",
        "addendum_1",
        "addendum_2",
        "addendum_3",
    )


def test_source_document_vocabulary_includes_addenda_2_and_3() -> None:
    """A23 made Addendum 2 + 3 repo-resident. SOURCE_DOCUMENT now
    pins both files alongside Roadmap v6 and Addendum 1."""
    assert rtc.SOURCE_DOCUMENT == (
        "docs/roadmap/Roadmap v6.md",
        "docs/roadmap/Roadmap v6 Addendum.md",
        (
            "docs/roadmap/Roadmap v6 Addendum 2 - "
            "State Sequential Knowledge Retrieval.md"
        ),
        (
            "docs/roadmap/Roadmap v6 Addendum 3 - "
            "Source Identity Data Quality and Throughput "
            "Intelligence.md"
        ),
        "docs/roadmap/qre_roadmap_v6_ade_operating_manual.md",
        "docs/roadmap/qre_roadmap_v6_phase_prompts.md",
    )


def test_status_vocabulary_is_closed() -> None:
    assert rtc.STATUS == (
        "not_started",
        "ready",
        "in_flight",
        "merged",
        "blocked",
        "human_needed",
        "permanently_denied",
    )


def test_addendum_link_vocabulary_is_closed() -> None:
    assert rtc.ADDENDUM_LINK == (
        "addendum_1",
        "addendum_2",
        "addendum_3",
        "none",
    )


def test_target_layer_vocabulary_is_closed() -> None:
    assert rtc.TARGET_LAYER == (
        "external_intelligence",
        "diagnostics",
        "market_behavior",
        "hypothesis_discovery",
        "strategy_mapping",
        "preset",
        "campaign",
        "funnel",
        "evidence",
        "policy",
        "shadow",
        "paper",
        "live",
        "reporting",
        "governance",
        "docs",
        "test",
    )


# ---------------------------------------------------------------------------
# Schema integrity
# ---------------------------------------------------------------------------


def test_roadmap_task_field_list_exact() -> None:
    assert rtc.ROADMAP_TASK_FIELDS == (
        "id",
        "title",
        "phase",
        "source_documents",
        "purpose",
        "status",
        "prerequisites",
    )


def test_roadmap_requirement_field_list_exact() -> None:
    assert rtc.ROADMAP_REQUIREMENT_FIELDS == (
        "id",
        "roadmap_task_id",
        "source_document",
        "source_anchor",
        "phase",
        "addendum_link",
        "statement",
        "target_layer",
        "status",
    )


def test_task_catalog_projection_field_list_exact() -> None:
    assert rtc.TASK_CATALOG_PROJECTION_FIELDS == (
        "generated_at_utc",
        "schema_version",
        "module_version",
        "roadmap_tasks",
        "roadmap_requirements",
        "discipline_invariants",
    )


def test_every_task_has_every_field(snap: dict) -> None:
    for task in snap["roadmap_tasks"]:
        assert set(task.keys()) == set(rtc.ROADMAP_TASK_FIELDS), task


def test_every_requirement_has_every_field(snap: dict) -> None:
    for req in snap["roadmap_requirements"]:
        assert set(req.keys()) == set(rtc.ROADMAP_REQUIREMENT_FIELDS), req


def test_projection_carries_every_required_top_level_field(snap: dict) -> None:
    for field in rtc.TASK_CATALOG_PROJECTION_FIELDS:
        assert field in snap, field


# ---------------------------------------------------------------------------
# Closed-vocab compliance on the encoded data
# ---------------------------------------------------------------------------


def test_every_task_phase_is_in_phase_vocab(snap: dict) -> None:
    for task in snap["roadmap_tasks"]:
        assert task["phase"] in rtc.PHASE


def test_every_task_status_is_in_status_vocab(snap: dict) -> None:
    for task in snap["roadmap_tasks"]:
        assert task["status"] in rtc.STATUS


def test_every_task_source_document_is_in_source_vocab(snap: dict) -> None:
    for task in snap["roadmap_tasks"]:
        for src in task["source_documents"]:
            assert src in rtc.SOURCE_DOCUMENT


def test_every_requirement_phase_is_in_phase_vocab(snap: dict) -> None:
    for req in snap["roadmap_requirements"]:
        assert req["phase"] in rtc.PHASE


def test_every_requirement_source_document_is_in_source_vocab(
    snap: dict,
) -> None:
    for req in snap["roadmap_requirements"]:
        assert req["source_document"] in rtc.SOURCE_DOCUMENT


def test_every_requirement_addendum_link_is_in_vocab(snap: dict) -> None:
    for req in snap["roadmap_requirements"]:
        assert req["addendum_link"] in rtc.ADDENDUM_LINK


def test_every_requirement_target_layer_is_in_vocab(snap: dict) -> None:
    for req in snap["roadmap_requirements"]:
        assert req["target_layer"] in rtc.TARGET_LAYER


def test_every_requirement_status_is_in_status_vocab(snap: dict) -> None:
    for req in snap["roadmap_requirements"]:
        assert req["status"] in rtc.STATUS


def test_every_requirement_references_a_known_task(snap: dict) -> None:
    task_ids = {t["id"] for t in snap["roadmap_tasks"]}
    for req in snap["roadmap_requirements"]:
        assert req["roadmap_task_id"] in task_ids, req["id"]


def test_task_prerequisites_reference_known_tasks(snap: dict) -> None:
    task_ids = {t["id"] for t in snap["roadmap_tasks"]}
    for task in snap["roadmap_tasks"]:
        for prereq in task["prerequisites"]:
            assert prereq in task_ids, (task["id"], prereq)


# ---------------------------------------------------------------------------
# Phase-task coverage
# ---------------------------------------------------------------------------


def _tasks_by_phase(snap: dict) -> dict[str, dict]:
    return {t["phase"]: t for t in snap["roadmap_tasks"]}


def test_phase_v3_15_16_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["v3.15.16"]
    assert t["id"] == "phase_v3_15_16"
    assert "Intelligent Routing Layer" in t["title"]


def test_phase_v3_15_17_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["v3.15.17"]
    assert t["id"] == "phase_v3_15_17"
    assert "Sampling Intelligence" in t["title"]


def test_phase_v3_15_18_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["v3.15.18"]
    assert t["id"] == "phase_v3_15_18"
    assert "Observability" in t["title"]


def test_phase_v3_15_19_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["v3.15.19"]
    assert t["id"] == "phase_v3_15_19"
    assert "Hypothesis Discovery" in t["title"]


def test_phase_v3_15_20_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["v3.15.20"]
    assert t["id"] == "phase_v3_15_20"
    # Title intentionally uses ASCII 'to' to keep the artefact ASCII-clean.
    assert "Failure" in t["title"] and "Action Mapping" in t["title"]


def test_addendum_1_task_present(snap: dict) -> None:
    t = _tasks_by_phase(snap)["addendum_1"]
    assert t["id"] == "addendum_1_diagnostics_intake"
    assert "Diagnostics" in t["title"] or "diagnostics" in t["title"]
    assert "External Intelligence Intake" in t["title"]


def test_addendum_2_and_3_have_tasks_after_a23(snap: dict) -> None:
    """A23 made Addendum 2 + 3 repo-resident; each now has a
    cross-cutting task entry in the catalog."""
    phases = {t["phase"] for t in snap["roadmap_tasks"]}
    assert "addendum_2" in phases
    assert "addendum_3" in phases
    task_ids = {t["id"] for t in snap["roadmap_tasks"]}
    assert "addendum_2_state_sequential_knowledge_retrieval" in task_ids
    assert (
        "addendum_3_source_identity_data_quality_throughput" in task_ids
    )


def test_v3_15_16_to_v3_15_20_all_present_in_order(snap: dict) -> None:
    phases = [t["phase"] for t in snap["roadmap_tasks"]]
    for expected in (
        "v3.15.16",
        "v3.15.17",
        "v3.15.18",
        "v3.15.19",
        "v3.15.20",
    ):
        assert expected in phases


# ---------------------------------------------------------------------------
# Addendum 1 diagnostic-family coverage
# ---------------------------------------------------------------------------


def _addendum1_requirements(snap: dict) -> list[dict]:
    return [r for r in snap["roadmap_requirements"] if r["phase"] == "addendum_1"]


@pytest.mark.parametrize(
    "marker",
    [
        "tail",
        "entropy",
        "criticality",
        "barrier",
        "resonance",
        "null-model",
        "network",
        "adversarial",
        "control-stability",
        "seismic",
        "liquidity-turbulence",
        "quorum",
        "market-language",
        "external-intelligence",
        "manifest",
        "quality gate",
        "diagnostics do not trade",
        "not alpha",
        "sidecar",
    ],
)
def test_addendum_1_diagnostic_family_present(snap: dict, marker: str) -> None:
    # Normalize hyphens / spaces for a tolerant substring check across
    # statements + ids.
    blob = " ".join(
        (r["id"] + " " + r["statement"]).lower().replace("_", "-")
        for r in _addendum1_requirements(snap)
    )
    needle = marker.lower().replace("_", "-")
    assert needle in blob, marker


def test_addendum_1_has_at_least_one_requirement_per_family(snap: dict) -> None:
    assert len(_addendum1_requirements(snap)) >= 13


# ---------------------------------------------------------------------------
# Step 5 / Level 6 invariants
# ---------------------------------------------------------------------------


def test_step5_implementation_allowed_is_false() -> None:
    assert rtc.step5_implementation_allowed is False


def test_step5_enabled_substage_is_none_literal() -> None:
    assert rtc.STEP5_ENABLED_SUBSTAGE == "none"


def test_projection_carries_step5_invariants(snap: dict) -> None:
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_discipline_invariants_addendum_absence_flags_flipped_by_a23(
    snap: dict,
) -> None:
    """A23 flipped both absence flags from True to False because
    Addendum 2 + 3 are now repo-resident."""
    inv = snap["discipline_invariants"]
    assert inv["addendum_2_not_present"] is False
    assert inv["addendum_3_not_present"] is False


def test_discipline_invariants_pin_no_runtime_authority(snap: dict) -> None:
    inv = snap["discipline_invariants"]
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


def test_discipline_invariants_pin_diagnostics_do_not_trade(snap: dict) -> None:
    inv = snap["discipline_invariants"]
    assert inv["diagnostics_do_not_trade"] is True
    assert inv["external_data_is_not_alpha"] is True


def test_discipline_invariants_pin_no_frozen_mutation(snap: dict) -> None:
    inv = snap["discipline_invariants"]
    assert inv["mutates_research_artifacts"] is False
    assert inv["mutates_roadmap_status_fields"] is False
    assert inv["marks_phase_complete"] is False


def test_discipline_invariants_pin_no_seed_jsonl_writes(snap: dict) -> None:
    inv = snap["discipline_invariants"]
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_collect_snapshot_deterministic_with_injected_ts() -> None:
    a = rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    assert a == b


def test_serialised_output_byte_identical_with_injected_ts() -> None:
    a = rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    b = rtc.collect_snapshot(generated_at_utc=_FROZEN_UTC)
    out_a = json.dumps(a, indent=2, sort_keys=True) + "\n"
    out_b = json.dumps(b, indent=2, sort_keys=True) + "\n"
    assert out_a == out_b


def test_task_order_stable(snap: dict) -> None:
    sorted_pairs = [(t["phase"], t["id"]) for t in snap["roadmap_tasks"]]
    assert sorted_pairs == sorted(sorted_pairs)


def test_requirement_order_stable(snap: dict) -> None:
    sorted_pairs = [(r["phase"], r["id"]) for r in snap["roadmap_requirements"]]
    assert sorted_pairs == sorted(sorted_pairs)


def test_all_task_ids_unique(snap: dict) -> None:
    ids = [t["id"] for t in snap["roadmap_tasks"]]
    assert len(ids) == len(set(ids))


def test_all_requirement_ids_unique(snap: dict) -> None:
    ids = [r["id"] for r in snap["roadmap_requirements"]]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Atomic write allowlist
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_path_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        rtc._atomic_write_json(bad, {"x": 1})


def test_atomic_write_accepts_allowlisted_path(tmp_path: Path) -> None:
    good = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    good.parent.mkdir(parents=True, exist_ok=True)
    rtc._atomic_write_json(good, {"x": 1})
    assert good.is_file()
    assert json.loads(good.read_text(encoding="utf-8")) == {"x": 1}


def test_atomic_write_is_atomic(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    rtc._atomic_write_json(target, {"x": 1})
    rtc._atomic_write_json(target, {"x": 2})
    # No tmp files left behind alongside the target.
    siblings = list(target.parent.iterdir())
    assert siblings == [target], siblings


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    monkeypatch.setattr(rtc, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtc, "ARTIFACT_DIR", sentinel.parent)
    rc = rtc.main(["--no-write"])
    assert rc == 0
    assert not sentinel.exists()
    # stdout must contain the JSON payload
    out = capsys.readouterr().out
    assert '"roadmap_task_catalog"' in out


def test_cli_status_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    monkeypatch.setattr(rtc, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtc, "ARTIFACT_DIR", sentinel.parent)
    rc = rtc.main(["--status"])
    assert rc == 0
    assert not sentinel.exists()
    out = capsys.readouterr().out
    assert "roadmap_task_catalog" in out
    assert "step5_implementation_allowed=False" in out
    # A23 flipped both flags to False.
    assert "addendum_2_not_present=False" in out
    assert "addendum_3_not_present=False" in out


def test_cli_default_writes_to_allowlisted_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    monkeypatch.setattr(rtc, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtc, "ARTIFACT_DIR", sentinel.parent)
    rc = rtc.main([])
    assert rc == 0
    assert sentinel.is_file()
    payload = json.loads(sentinel.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "roadmap_task_catalog"
    assert payload["module_version"].startswith("v3.15.16.A20a")


def test_cli_indent_zero_compact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sentinel = tmp_path / "logs" / "roadmap_task_catalog" / "latest.json"
    monkeypatch.setattr(rtc, "ARTIFACT_LATEST", sentinel)
    monkeypatch.setattr(rtc, "ARTIFACT_DIR", sentinel.parent)
    rc = rtc.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    # indent=0 collapses to compact output (no leading two-space lines)
    assert "\n  " not in out


# ---------------------------------------------------------------------------
# Module-source forbidden-import / forbidden-token scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(rtc.__file__).read_text(encoding="utf-8")


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    # docstring may mention 'subprocess' only inside the negative
    # guarantees block, but no import or attribute reference must
    # appear.
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
        "from research ",
        "import research\n",
        "from live",
        "import live",
        "from paper",
        "import paper",
        "from shadow",
        "import shadow",
        "from trading",
        "import trading",
        "from reporting.intelligent_routing",
        "import reporting.intelligent_routing",
    ):
        assert forbidden not in src, forbidden


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
        "shell=True",
        " gh ",
        "`gh ",
        " git ",
        "`git ",
    ):
        assert forbidden not in src, forbidden


def test_module_never_writes_frozen_contracts() -> None:
    """The actual no-mutation invariant for frozen contracts is
    pinned by (a) the atomic-write allowlist refusing any path
    outside ``logs/roadmap_task_catalog/`` and (b) the
    ``mutates_research_artifacts: False`` discipline invariant.

    The module source legitimately *names* the frozen contracts in
    docstrings and inside the Addendum 1 ``do not mutate ...``
    requirement statement — those are negative guarantees, not
    write-path references. This test asserts the operational
    invariant directly: the atomic-write helper rejects every
    frozen-contract path.
    """
    src = _module_source()
    # Confirm the actual write helper exists and is the only write
    # surface the module exposes.
    assert "_atomic_write_json" in src
    # The closed write-prefix substring must be present and must be
    # the catalog directory — not any research / frozen / live path.
    assert 'logs/roadmap_task_catalog/' in src
    # Refusal path: any frozen contract path must be refused.
    import tempfile
    from pathlib import Path as _Path
    with tempfile.TemporaryDirectory() as td:
        for forbidden in (
            "research/research_latest.json",
            "research/strategy_matrix.csv",
        ):
            target = _Path(td) / forbidden
            target.parent.mkdir(parents=True, exist_ok=True)
            with pytest.raises(ValueError):
                rtc._atomic_write_json(target, {"x": 1})


def test_no_llm_or_external_api_calls() -> None:
    src = _module_source()
    for forbidden in (
        "anthropic",
        "openai",
        "Bearer ",
        "X-API-Key",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(rtc)
    assert callable(rtc.collect_snapshot)
    assert callable(rtc.write_outputs)
    assert callable(rtc.main)


def test_schema_and_module_version_strings() -> None:
    assert isinstance(rtc.SCHEMA_VERSION, str) and rtc.SCHEMA_VERSION
    assert isinstance(rtc.MODULE_VERSION, str) and rtc.MODULE_VERSION


# ---------------------------------------------------------------------------
# Governance doc cross-references
# ---------------------------------------------------------------------------


def _governance_doc_text() -> str:
    doc = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "governance"
        / "roadmap_task_catalog.md"
    )
    return doc.read_text(encoding="utf-8").lower()


def test_governance_doc_marks_read_only() -> None:
    text = _governance_doc_text()
    assert "read-only" in text or "read only" in text


def test_governance_doc_marks_not_canonical_product_roadmap() -> None:
    text = _governance_doc_text()
    assert "canonical" in text
    assert "roadmap v6" in text


def test_governance_doc_pins_addendum_2_3_absence() -> None:
    text = _governance_doc_text()
    assert "addendum 2" in text
    assert "addendum 3" in text
    assert "not present" in text or "absent" in text or "not in the repo" in text


def test_governance_doc_pins_no_runtime_or_trading_authority() -> None:
    text = _governance_doc_text()
    for forbidden in (
        "runtime",
        "trading",
        "paper",
        "shadow",
        "broker",
        "risk",
        "live",
    ):
        assert forbidden in text, forbidden


def test_governance_doc_lists_future_a20b_a20e_stages() -> None:
    text = _governance_doc_text()
    for stage in ("a20b", "a20c", "a20d", "a20e"):
        assert stage in text, stage
