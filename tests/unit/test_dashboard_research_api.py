from datetime import UTC, datetime, timedelta


class _FakeProcess:
    def __init__(self, pid=4321, returncode=None):
        self.pid = pid
        self._returncode = returncode

    def poll(self):
        return self._returncode


def _set_operator_session(client):
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "joery"


class _UnreadablePath:
    def exists(self):
        return True

    def stat(self):
        return type("Stat", (), {"st_mtime": 0})()

    def read_text(self, encoding="utf-8"):
        raise OSError("cannot read")

    def relative_to(self, _base):
        raise ValueError

    def __str__(self):
        return "unreadable.json"


def test_research_routes_require_auth():
    from dashboard import dashboard as dash

    dash.app.testing = True
    client = dash.app.test_client()

    for route in (
        "/research",
        "/api/research/run-status",
        "/api/research/latest",
        "/api/research/empty-run-diagnostics",
        "/api/research/universe",
    ):
        response = client.get(route)
        assert response.status_code == 401


def test_research_run_status_endpoint_without_sidecar(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", None)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artifact_state"] == "absent"
    assert payload["dashboard_observations"]["local_process_active"] is False
    assert payload["artifact"] is None


def test_research_run_status_endpoint_with_valid_sidecar(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    now = datetime.now(UTC)
    path = tmp_path / "run_progress_latest.v1.json"
    path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"status\":\"running\","
            "\"run_id\":\"20260413T100000000000Z\","
            "\"current_stage\":\"evaluation\","
            f"\"started_at_utc\":\"{(now - timedelta(seconds=180)).isoformat()}\","
            f"\"last_updated_at_utc\":\"{now.isoformat()}\","
            "\"progress\":{\"completed\":5,\"total\":10,\"percent\":50.0},"
            "\"current_item\":{\"strategy\":\"sma\",\"asset\":\"BTC-USD\",\"interval\":\"1h\"},"
            "\"timing\":{\"elapsed_seconds\":180,\"stage_elapsed_seconds\":120,\"eta_seconds\":180},"
            "\"failure\":null"
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", path)
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", None)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artifact_state"] == "valid"
    assert payload["artifact"]["status"] == "running"
    assert payload["dashboard_observations"]["recent_progress_signal"] is True


def test_research_run_status_endpoint_with_stale_running_sidecar(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    now = datetime.now(UTC)
    stale_at = (now - timedelta(seconds=601)).isoformat()
    path = tmp_path / "run_progress_latest.v1.json"
    path.write_text(
        (
            "{"
            f"\"version\":\"v1\",\"status\":\"running\",\"last_updated_at_utc\":\"{stale_at}\""
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", path)
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", None)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    payload = response.get_json()
    assert payload["dashboard_observations"]["stale_progress_signal"] is True
    assert payload["warnings"]


def test_research_run_status_endpoint_with_invalid_json(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    path = tmp_path / "run_progress_latest.v1.json"
    path.write_text("{ invalid", encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    payload = response.get_json()
    assert payload["artifact_state"] == "invalid_json"
    assert payload["artifact_error"]


def test_research_run_trigger_accepted_when_idle(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", None)
    monkeypatch.setattr(
        dash.research_runner.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(pid=999, returncode=None),
    )

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.post("/api/research/run")

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["accepted"] is True
    assert payload["launch_state"] == "started"
    assert payload["pid"] == 999


def test_research_run_trigger_blocked_when_process_active(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", _FakeProcess(returncode=None))

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.post("/api/research/run")

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["accepted"] is False
    assert payload["launch_state"] == "blocked_active_run"


def test_research_run_trigger_returns_stale_signal_behavior(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    stale_at = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    path = tmp_path / "run_progress_latest.v1.json"
    path.write_text(
        (
            "{"
            f"\"version\":\"v1\",\"status\":\"running\",\"last_updated_at_utc\":\"{stale_at}\""
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", path)
    monkeypatch.setattr(dash.research_runner, "_ACTIVE_PROCESS", None)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.post("/api/research/run")

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["accepted"] is False
    assert payload["launch_state"] == "blocked_stale_signal"


def test_research_latest_endpoint_valid_artifact(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    path = tmp_path / "research_latest.json"
    path.write_text(
        '{"generated_at_utc":"2026-04-13T10:00:00+00:00","count":1,"results":[{"strategy_name":"sma"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RESEARCH_LATEST_PATH", path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/latest")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["artifact_state"] == "valid"
    assert payload["artifact"]["count"] == 1
    assert payload["artifact"]["results"][0]["strategy_name"] == "sma"


def test_research_latest_endpoint_invalid_artifact(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    path = tmp_path / "research_latest.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "RESEARCH_LATEST_PATH", path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/latest")

    payload = response.get_json()
    assert payload["artifact_state"] == "invalid_json"
    assert payload["artifact"] is None


def test_empty_run_diagnostics_endpoint_absent_and_present(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    missing = tmp_path / "missing.json"
    monkeypatch.setattr(dash.research_artifacts, "EMPTY_RUN_DIAGNOSTICS_PATH", missing)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    absent_response = client.get("/api/research/empty-run-diagnostics")
    assert absent_response.get_json()["artifact_state"] == "absent"

    present = tmp_path / "empty_run_diagnostics_latest.v1.json"
    present.write_text('{"version":"v1","failure_stage":"preflight","pairs":[]}', encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "EMPTY_RUN_DIAGNOSTICS_PATH", present)

    present_response = client.get("/api/research/empty-run-diagnostics")
    payload = present_response.get_json()
    assert payload["artifact_state"] == "valid"
    assert payload["artifact"]["failure_stage"] == "preflight"


def test_universe_endpoint_valid_artifact(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    path = tmp_path / "universe_snapshot_latest.v1.json"
    path.write_text('{"version":"v1","intervals":["1h","4h"]}', encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "UNIVERSE_SNAPSHOT_PATH", path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/universe")

    payload = response.get_json()
    assert payload["artifact_state"] == "valid"
    assert payload["artifact"]["intervals"] == ["1h", "4h"]


def test_research_latest_endpoint_unreadable_artifact(monkeypatch):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash.research_artifacts, "RESEARCH_LATEST_PATH", _UnreadablePath())

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/latest")

    payload = response.get_json()
    assert payload["artifact_state"] == "unreadable"
    assert payload["artifact_error"] == "cannot read"


def test_research_latest_endpoint_empty_artifact(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    path = tmp_path / "research_latest.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "RESEARCH_LATEST_PATH", path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/latest")

    payload = response.get_json()
    assert payload["artifact_state"] == "empty"
    assert payload["artifact"] == {}
