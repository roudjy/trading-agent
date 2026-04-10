"""Unit tests for dashboard operator auth and audit logging."""

import json
from pathlib import Path


class _ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


def test_pause_endpoint_requires_operator_auth(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash, "PAUSE_FLAG", tmp_path / "logs" / "agent_pause.flag")
    monkeypatch.setattr(dash.audit_log, "AUDIT_LOG_PATH", tmp_path / "logs" / "audit.log")
    monkeypatch.setattr(dash, "_operator_token_secret", lambda: "secret-token")

    dash.app.testing = True
    client = dash.app.test_client()

    response = client.post("/api/agent/pauze", json={"actie": "pauze"})

    assert response.status_code == 401


def test_pause_endpoint_accepts_operator_token_and_audits(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    pause_flag = tmp_path / "logs" / "agent_pause.flag"
    audit_path = tmp_path / "logs" / "audit.log"
    monkeypatch.setattr(dash, "PAUSE_FLAG", pause_flag)
    monkeypatch.setattr(dash.audit_log, "AUDIT_LOG_PATH", audit_path)
    monkeypatch.setattr(dash, "_operator_token_secret", lambda: "secret-token")

    dash.app.testing = True
    client = dash.app.test_client()
    response = client.post(
        "/api/agent/pauze",
        json={"actie": "pauze"},
        headers={"X-Operator-Token": "secret-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["gepauzeerd"] is True
    assert pause_flag.exists()

    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    events = [entry["event"] for entry in entries]
    assert events == ["dashboard_pause_requested", "dashboard_pause_succeeded"]


def test_tests_run_endpoint_accepts_session_cookie_and_audits(monkeypatch, tmp_path):
    import subprocess
    from dashboard import dashboard as dash

    audit_path = tmp_path / "logs" / "audit.log"
    test_log = tmp_path / "logs" / "test_resultaat.log"
    monkeypatch.setattr(dash.audit_log, "AUDIT_LOG_PATH", audit_path)
    monkeypatch.setattr(dash, "Path", Path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dash.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": "ok", "stderr": "", "returncode": 0})(),
    )

    dash.app.testing = True
    client = dash.app.test_client()
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "joery"

    response = client.post("/api/tests/run")

    assert response.status_code == 200
    assert response.get_json()["status"] == "gestart"
    assert test_log.exists()

    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    events = {entry["event"] for entry in entries}
    assert "dashboard_tests_run_requested" in events
    assert "dashboard_tests_run_queued" in events
    assert "dashboard_tests_run_finished" in events


def test_backtests_endpoint_returns_404_without_crash(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash, "BASE_DIR", tmp_path)
    dash.app.testing = True
    client = dash.app.test_client()

    response = client.get("/api/backtests")

    assert response.status_code == 404
    assert response.get_json()["error"] == "Nog geen backtest resultaten"
