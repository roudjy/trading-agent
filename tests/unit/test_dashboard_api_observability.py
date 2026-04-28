"""Unit tests for dashboard/api_observability.py (v3.15.15.3).

Verifies:

* Each endpoint returns 200 with ``available=true`` for a valid
  artifact, 200 with ``available=false`` for a missing/corrupt
  artifact.
* All endpoints are GET-only (mutating verbs rejected).
* No mutation of the artifact directory across reads.
* Static import-surface guarantee: the module never imports
  campaign / sprint / strategy / runtime modules. Allowed imports
  are limited to stdlib + flask + ``research.diagnostics.paths``.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from dashboard import api_observability
from dashboard import dashboard as dashboard_mod
from research.diagnostics import paths as diag_paths


# ---------- fixture ----------


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test client with all observability paths redirected into tmp_path.

    The blueprint is registered at module load time; we monkeypatch the
    in-module path constants so the GET handlers resolve to our tmp
    artifacts.
    """
    obs = tmp_path / "research" / "observability"
    obs.mkdir(parents=True)

    monkeypatch.setattr(api_observability, "OBSERVABILITY_DIR", obs)
    monkeypatch.setattr(
        api_observability, "ARTIFACT_HEALTH_PATH", obs / "artifact_health_latest.v1.json"
    )
    monkeypatch.setattr(
        api_observability, "FAILURE_MODES_PATH", obs / "failure_modes_latest.v1.json"
    )
    monkeypatch.setattr(
        api_observability,
        "THROUGHPUT_METRICS_PATH",
        obs / "throughput_metrics_latest.v1.json",
    )
    monkeypatch.setattr(
        api_observability,
        "SYSTEM_INTEGRITY_PATH",
        obs / "system_integrity_latest.v1.json",
    )
    monkeypatch.setattr(
        api_observability,
        "OBSERVABILITY_SUMMARY_PATH",
        obs / "observability_summary_latest.v1.json",
    )

    # Re-bind the active endpoints tuple so the index endpoint uses the
    # tmp paths too.
    monkeypatch.setattr(
        api_observability,
        "_ACTIVE_ENDPOINTS",
        (
            (
                "artifact_health",
                "artifact-health",
                "artifact_health_latest.v1.json",
                obs / "artifact_health_latest.v1.json",
            ),
            (
                "failure_modes",
                "failure-modes",
                "failure_modes_latest.v1.json",
                obs / "failure_modes_latest.v1.json",
            ),
            (
                "throughput_metrics",
                "throughput",
                "throughput_metrics_latest.v1.json",
                obs / "throughput_metrics_latest.v1.json",
            ),
            (
                "system_integrity",
                "system-integrity",
                "system_integrity_latest.v1.json",
                obs / "system_integrity_latest.v1.json",
            ),
            (
                "observability_summary",
                "summary",
                "observability_summary_latest.v1.json",
                obs / "observability_summary_latest.v1.json",
            ),
        ),
    )

    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client(), obs


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


ACTIVE_ENDPOINTS = [
    ("/api/observability/summary", "observability_summary_latest.v1.json"),
    ("/api/observability/artifact-health", "artifact_health_latest.v1.json"),
    ("/api/observability/failure-modes", "failure_modes_latest.v1.json"),
    ("/api/observability/throughput", "throughput_metrics_latest.v1.json"),
    ("/api/observability/system-integrity", "system_integrity_latest.v1.json"),
]


DEFERRED_ENDPOINTS = [
    "/api/observability/funnel",
    "/api/observability/campaign-timeline",
    "/api/observability/parameter-coverage",
    "/api/observability/data-freshness",
    "/api/observability/policy-trace",
    "/api/observability/no-touch-health",
]


# ---------- positive path ----------


@pytest.mark.parametrize("endpoint, filename", ACTIVE_ENDPOINTS)
def test_active_endpoint_returns_200_when_artifact_present(
    client,
    endpoint: str,
    filename: str,
):
    test_client, obs = client
    _write(obs / filename, {"schema_version": "1.0", "marker": filename})
    resp = test_client.get(endpoint)
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["available"] is True
    assert body["state"] == "valid"
    assert body["artifact_name"] == filename
    assert body["payload"]["marker"] == filename


@pytest.mark.parametrize("endpoint, filename", ACTIVE_ENDPOINTS)
def test_active_endpoint_returns_200_with_unavailable_when_missing(
    client,
    endpoint: str,
    filename: str,
):
    test_client, _ = client
    resp = test_client.get(endpoint)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is False
    assert body["state"] == "absent"
    assert body["payload"] is None


@pytest.mark.parametrize("endpoint, filename", ACTIVE_ENDPOINTS)
def test_active_endpoint_returns_200_with_unavailable_when_corrupt(
    client,
    endpoint: str,
    filename: str,
):
    test_client, obs = client
    (obs / filename).write_text("{not json", encoding="utf-8")
    resp = test_client.get(endpoint)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is False
    assert body["state"] == "invalid_json"
    assert body["error"]


# ---------- deferred endpoints ----------


@pytest.mark.parametrize("endpoint", DEFERRED_ENDPOINTS)
def test_deferred_endpoint_always_returns_unavailable(client, endpoint: str):
    test_client, _ = client
    resp = test_client.get(endpoint)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is False
    assert body["deferred"] is True
    assert body["error"] == "deferred_to_v3_15_15_4"


# ---------- index ----------


def test_index_lists_all_components(client):
    test_client, obs = client
    _write(
        obs / "artifact_health_latest.v1.json", {"schema_version": "1.0"}
    )
    resp = test_client.get("/api/observability/index")
    assert resp.status_code == 200
    body = resp.get_json()
    names = {c["component"] for c in body["components"]}
    assert {
        "artifact_health",
        "failure_modes",
        "throughput_metrics",
        "system_integrity",
        "observability_summary",
        "funnel_stage_summary",
        "campaign_timeline",
        "parameter_coverage",
        "data_freshness",
        "policy_decision_trace",
        "no_touch_health",
    } == names
    assert body["active_count"] == 5
    assert body["deferred_count"] == 6
    # the artifact_health row knows about the file we just wrote
    ah = next(c for c in body["components"] if c["component"] == "artifact_health")
    assert ah["exists"] is True
    assert ah["size_bytes"] is not None


# ---------- HTTP method discipline ----------


@pytest.mark.parametrize(
    "endpoint",
    ACTIVE_ENDPOINTS_PATHS := [e for e, _ in ACTIVE_ENDPOINTS]
    + DEFERRED_ENDPOINTS
    + ["/api/observability/index"],
)
def test_endpoint_is_get_only(client, endpoint: str):
    test_client, _ = client
    assert test_client.get(endpoint).status_code == 200
    for verb in (test_client.post, test_client.put, test_client.delete, test_client.patch):
        resp = verb(endpoint)
        # Flask's 405 may be wrapped as 500 by the dashboard's catch-all;
        # accept either as long as the verb is rejected.
        assert resp.status_code in (405, 500), (
            f"{endpoint} accepted {verb.__name__.upper()} (status={resp.status_code})"
        )
        if resp.status_code == 500:
            body = resp.get_json() or {}
            assert "Method Not Allowed" in str(body.get("error", ""))


# ---------- read-only proof ----------


def test_no_mutation_across_reads(client):
    test_client, obs = client
    # Write each active artifact then snapshot the directory.
    for endpoint, filename in ACTIVE_ENDPOINTS:
        _write(obs / filename, {"schema_version": "1.0"})

    import os

    before = {
        f.name: (f.stat().st_mtime, f.stat().st_size) for f in obs.iterdir()
    }
    for endpoint, _ in ACTIVE_ENDPOINTS:
        test_client.get(endpoint)
    for endpoint in DEFERRED_ENDPOINTS:
        test_client.get(endpoint)
    test_client.get("/api/observability/index")

    after = {
        f.name: (f.stat().st_mtime, f.stat().st_size) for f in obs.iterdir()
    }
    assert before == after, "observability endpoint mutated artifact directory"


# ---------- static import-surface guarantee ----------


_FORBIDDEN_IMPORT_PREFIXES = (
    "research.campaign_policy",
    "research.campaign_launcher",
    "research.campaign_queue",
    "research.campaign_lease",
    "research.campaign_registry",
    "research.campaign_digest",
    "research.campaign_budget",
    "research.campaign_templates",
    "research.campaign_evidence_ledger",
    "research.campaign_followup",
    "research.campaign_funnel_policy",
    "research.campaign_invariants",
    "research.campaign_os_artifacts",
    "research.campaign_preset_policy",
    "research.campaign_family_policy",
    "research.campaigns",
    "research.discovery_sprint",
    "research.screening_runtime",
    "research.screening_evidence",
    "research.screening_process",
    "research.run_research",
    "research.run_state",
    "research.observability",  # legacy ProgressTracker module — pulls run_state
    "research.candidate_lifecycle",
    "research.candidate_pipeline",
    "research.candidate_registry_v2",
    "research.candidate_resume",
    "research.candidate_returns_feed",
    "research.candidate_scoring",
    "research.candidate_sidecars",
    "research.engine",
    "research.presets",
    "research.research_evidence_ledger",
    "research.funnel_spawn_proposer",
    "research.dead_zone_detection",
    "research.information_gain",
    "research.stop_condition_engine",
    "research.viability_metrics",
    "research.batch_execution",
    "research.batching",
    "research.strategy_hypothesis_catalog",
    "research.integrity",
    "research.integrity_reporting",
    "research.public_artifact_status",
    # Forbidden subsystems.
    "agent",
    "strategies",
    "orchestration",
    "execution",
    "automation",
    "state",
    # Observability builders/CLI also forbidden — only the path constants
    # may be imported, so we don't accidentally pull in anything heavier.
    "research.diagnostics.aggregator",
    "research.diagnostics.artifact_health",
    "research.diagnostics.failure_modes",
    "research.diagnostics.throughput",
    "research.diagnostics.system_integrity",
    "research.diagnostics.cli",
    "research.diagnostics.io",
    "research.diagnostics.clock",
)

_ALLOWED_PROJECT_IMPORTS = {
    "research.diagnostics.paths",
}


def test_api_module_only_imports_safe_modules():
    src_path = Path(api_observability.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # No relative imports — the dashboard package layout
                # doesn't expect any.
                imports.append(f"<relative:{node.level}>")
            else:
                imports.append(node.module or "")

    violations: list[str] = []
    for name in imports:
        if name.startswith("<relative:"):
            violations.append(name)
            continue
        for prefix in _FORBIDDEN_IMPORT_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                violations.append(name)
                break

    assert not violations, (
        f"dashboard/api_observability.py imports forbidden modules: {violations}"
    )

    # Project imports must come from the explicit allowlist.
    project_roots = {
        "agent",
        "strategies",
        "research",
        "orchestration",
        "execution",
        "automation",
        "state",
        "data",
        "reporting",
        "config",
        "ops",
        "dashboard",
    }
    project_imports = [
        n
        for n in imports
        if not n.startswith("<relative:")
        and n.split(".", 1)[0] in project_roots
        and n not in _ALLOWED_PROJECT_IMPORTS
    ]
    assert not project_imports, (
        f"dashboard/api_observability.py imports non-whitelisted project modules: "
        f"{project_imports}"
    )


def test_paths_module_does_not_pull_in_forbidden_modules():
    """``research.diagnostics.paths`` is the ONLY project module the API imports.

    This test ensures paths.py itself is still stdlib-only by re-running
    the same AST check on it.
    """
    src_path = Path(diag_paths.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    project_roots = {
        "agent",
        "strategies",
        "research",
        "orchestration",
        "execution",
        "automation",
        "state",
        "data",
        "reporting",
        "config",
        "ops",
        "dashboard",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            module = node.module or ""
            assert module.split(".", 1)[0] not in project_roots, (
                f"research/diagnostics/paths.py imports project module {module}"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".", 1)[0] not in project_roots, (
                    f"research/diagnostics/paths.py imports project module {alias.name}"
                )
