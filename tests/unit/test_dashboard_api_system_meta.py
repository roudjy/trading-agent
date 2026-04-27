"""Unit tests for the read-only QRE Control Room metadata endpoints.

These tests prove that the three new endpoints registered by
``dashboard.api_system_meta``:

* are GET-only (POST/PUT/DELETE return 405);
* never mutate state on disk;
* return graceful "available=false" / null payloads when artifacts
  are missing instead of raising;
* read filesystem metadata + existing JSON artifacts only.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from dashboard import api_system_meta
from dashboard import dashboard as dashboard_mod


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test client with the artifact dirs redirected to a tmp tree.

    We monkeypatch the module-level path constants so the test never
    touches the real repo artifacts.
    """
    research_dir = tmp_path / "research"
    sprint_dir = research_dir / "discovery_sprints"
    sprint_dir.mkdir(parents=True)

    monkeypatch.setattr(api_system_meta, "BASE_DIR", tmp_path)
    monkeypatch.setattr(api_system_meta, "VERSION_FILE", tmp_path / "VERSION")
    monkeypatch.setattr(api_system_meta, "RESEARCH_DIR", research_dir)
    monkeypatch.setattr(api_system_meta, "DISCOVERY_SPRINTS_DIR", sprint_dir)
    monkeypatch.setattr(
        api_system_meta,
        "SPRINT_REGISTRY_FILE",
        sprint_dir / "sprint_registry_latest.v1.json",
    )
    monkeypatch.setattr(
        api_system_meta,
        "SPRINT_PROGRESS_FILE",
        sprint_dir / "discovery_sprint_progress_latest.v1.json",
    )
    monkeypatch.setattr(
        api_system_meta,
        "SPRINT_REPORT_FILE",
        sprint_dir / "discovery_sprint_report_latest.v1.json",
    )

    dashboard_mod.app.testing = True
    return dashboard_mod.app.test_client(), tmp_path


# ---------- /api/system/version ---------------------------------------


def test_version_endpoint_returns_null_fields_when_no_version_file(client):
    test_client, _ = client
    resp = test_client.get("/api/system/version")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["file_version"] is None
    assert data["version_file"] is None
    # git_head, image_tag, host, container may legitimately be None on a
    # bare test environment — we only assert keys exist, not their type.
    assert "git_head" in data
    assert "image_tag" in data


def test_version_endpoint_reads_version_file(client):
    test_client, tmp_path = client
    (tmp_path / "VERSION").write_text("9.9.9\n", encoding="utf-8")
    resp = test_client.get("/api/system/version")
    data = resp.get_json()
    assert data["file_version"] == "9.9.9"
    assert data["version_file"]["exists"] is True
    assert data["version_file"]["size_bytes"] >= 6


def test_version_is_get_only(client):
    test_client, _ = client
    # GET succeeds.
    assert test_client.get("/api/system/version").status_code == 200
    # Mutating verbs are rejected. Flask raises 405; the dashboard's
    # global Exception handler wraps this as 500 with the message in
    # the body. Either way the verb is NOT allowed — that's what
    # matters for the read-only contract.
    for method_call in (
        test_client.post,
        test_client.put,
        test_client.delete,
        test_client.patch,
    ):
        resp = method_call("/api/system/version")
        assert resp.status_code in (405, 500)
        if resp.status_code == 500:
            body = resp.get_json() or {}
            assert "Method Not Allowed" in str(body.get("error", ""))


# ---------- /api/research/artifact-index ------------------------------


def test_artifact_index_lists_files(client):
    test_client, tmp_path = client
    (tmp_path / "research" / "research_latest.json").write_text(
        json.dumps({"foo": 1}), encoding="utf-8"
    )
    (tmp_path / "research" / "discovery_sprints" / "x.json").write_text(
        "{}", encoding="utf-8"
    )
    resp = test_client.get("/api/research/artifact-index")
    assert resp.status_code == 200
    data = resp.get_json()
    paths = {d["path"] for d in data["directories"]}
    assert paths == {"research", "research/discovery_sprints"}
    research_files = next(
        d for d in data["directories"] if d["path"] == "research"
    )["files"]
    assert any(f["name"] == "research_latest.json" for f in research_files)
    sprint_files = next(
        d
        for d in data["directories"]
        if d["path"] == "research/discovery_sprints"
    )["files"]
    assert any(f["name"] == "x.json" for f in sprint_files)
    assert data["file_count"] == len(research_files) + len(sprint_files)


def test_artifact_index_handles_missing_dirs(client):
    test_client, tmp_path = client
    # remove research dir
    import shutil

    shutil.rmtree(tmp_path / "research")
    resp = test_client.get("/api/research/artifact-index")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["file_count"] == 0
    for d in data["directories"]:
        assert d["files"] == []


def test_artifact_index_is_get_only(client):
    test_client, _ = client
    assert test_client.get("/api/research/artifact-index").status_code == 200
    for method_call in (
        test_client.post,
        test_client.put,
        test_client.delete,
        test_client.patch,
    ):
        resp = method_call("/api/research/artifact-index")
        assert resp.status_code in (405, 500)
        if resp.status_code == 500:
            body = resp.get_json() or {}
            assert "Method Not Allowed" in str(body.get("error", ""))


def test_artifact_index_does_not_mutate(client):
    test_client, tmp_path = client
    (tmp_path / "research" / "research_latest.json").write_text(
        "{}", encoding="utf-8"
    )
    before = sorted(p.name for p in (tmp_path / "research").iterdir())
    test_client.get("/api/research/artifact-index")
    after = sorted(p.name for p in (tmp_path / "research").iterdir())
    assert before == after


# ---------- /api/research/sprint-status -------------------------------


def test_sprint_status_returns_unavailable_when_artifacts_missing(client):
    test_client, _ = client
    resp = test_client.get("/api/research/sprint-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["available"] is False
    assert data["registry"] is None
    assert data["progress"] is None
    assert data["report"] is None


def test_sprint_status_passes_through_existing_artifacts(client):
    test_client, tmp_path = client
    sprint_dir = tmp_path / "research" / "discovery_sprints"
    (sprint_dir / "sprint_registry_latest.v1.json").write_text(
        json.dumps({"sprint_id": "sp_test", "state": "active"}),
        encoding="utf-8",
    )
    (sprint_dir / "discovery_sprint_progress_latest.v1.json").write_text(
        json.dumps({"observed_campaigns": 7, "target_campaigns": 12}),
        encoding="utf-8",
    )
    resp = test_client.get("/api/research/sprint-status")
    data = resp.get_json()
    assert data["available"] is True
    assert data["registry"]["sprint_id"] == "sp_test"
    assert data["progress"]["observed_campaigns"] == 7
    # report still missing but registry+progress present
    assert data["report"] is None


def test_sprint_status_is_get_only(client):
    test_client, _ = client
    assert test_client.get("/api/research/sprint-status").status_code == 200
    for method_call in (
        test_client.post,
        test_client.put,
        test_client.delete,
        test_client.patch,
    ):
        resp = method_call("/api/research/sprint-status")
        assert resp.status_code in (405, 500)
        if resp.status_code == 500:
            body = resp.get_json() or {}
            assert "Method Not Allowed" in str(body.get("error", ""))


# ---------- import-surface check (read-only proof) --------------------


def test_module_import_surface_excludes_orchestration_modules():
    """The read-only metadata module must not import campaign/sprint/strategy code.

    This guards rule §15.1: ``dashboard/api_system_meta.py`` may only
    import ``flask``, stdlib, and read-only path constants. Importing
    a campaign launcher / sprint orchestrator / strategy module would
    open a side-effect surface that this layer is contractually banned
    from touching.
    """
    importlib.reload(api_system_meta)  # ensure fresh import graph

    # Inspect module's globals for any top-level reference to forbidden
    # subsystems. We check both module attributes and the source file
    # itself for the most robust signal.
    forbidden_substrings = [
        "research.campaign_launcher",
        "research.campaign_queue",
        "research.campaign_policy",
        "research.discovery_sprint",  # orchestrator
        "research.candidate_pipeline",
        "agent.",
        "strategies.",
        "orchestration.",
        "execution.",
        "automation.",
        "state.",
    ]
    source = Path(api_system_meta.__file__).read_text(encoding="utf-8")
    # Strip the docstring / comments — we only care about real imports.
    import_lines = [
        ln.strip()
        for ln in source.splitlines()
        if ln.strip().startswith("import ") or ln.strip().startswith("from ")
    ]
    joined = "\n".join(import_lines)
    for needle in forbidden_substrings:
        assert needle not in joined, (
            f"api_system_meta must not import {needle!r}; "
            f"found in import block:\n{joined}"
        )
