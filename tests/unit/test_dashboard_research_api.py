import json
from datetime import UTC, datetime, timedelta


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

    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", tmp_path / "missing-state.json")
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(dash.research_artifacts, "RUN_CAMPAIGN_PATH", tmp_path / "missing-campaign.json")
    monkeypatch.setattr(dash.research_artifacts, "RUN_CAMPAIGN_PROGRESS_PATH", tmp_path / "missing-campaign-progress.json")

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["run_state"]["artifact_state"] == "absent"
    assert payload["run_progress"]["artifact_state"] == "absent"
    assert payload["run_campaign"]["artifact_state"] == "absent"
    assert payload["run_campaign_progress"]["artifact_state"] == "absent"
    assert payload["dashboard_observations"]["authoritative_status"] is None


def test_research_run_status_endpoint_with_valid_sidecar(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    now = datetime.now(UTC)
    state_path = tmp_path / "run_state.v1.json"
    progress_path = tmp_path / "run_progress_latest.v1.json"
    campaign_path = tmp_path / "run_campaign_latest.v1.json"
    campaign_progress_path = tmp_path / "run_campaign_progress_latest.v1.json"
    state_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"status\":\"running\","
            "\"run_id\":\"20260413T100000000000Z\","
            f"\"started_at_utc\":\"{(now - timedelta(seconds=180)).isoformat()}\","
            f"\"updated_at_utc\":\"{now.isoformat()}\","
            "\"stage\":\"evaluation\","
            "\"status_reason\":\"research_run_started\","
            "\"heartbeat_timeout_s\":300,"
            "\"progress_path\":\"research/run_progress_latest.v1.json\","
            "\"manifest_path\":\"research/run_manifest_latest.v1.json\","
            "\"log_path\":\"logs/research/20260413T100000000000Z.jsonl\","
            "\"pid\":123,"
            "\"error\":null"
            "}"
        ),
        encoding="utf-8",
    )
    progress_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"run_id\":\"20260413T100000000000Z\","
            "\"status\":\"running\","
            "\"current_stage\":\"evaluation\","
            "\"stage_progress\":{\"completed\":5,\"total\":10,\"percent\":50.0},"
            "\"total_items\":10,"
            "\"completed_items\":5,"
            "\"failed_items\":0,"
            "\"current_item\":{\"strategy\":\"sma\",\"asset\":\"BTC-USD\",\"interval\":\"1h\"},"
            f"\"started_at_utc\":\"{(now - timedelta(seconds=180)).isoformat()}\","
            f"\"updated_at_utc\":\"{now.isoformat()}\","
            "\"elapsed_seconds\":180,"
            "\"eta_seconds\":180,"
            "\"error\":null"
            "}"
        ),
        encoding="utf-8",
    )
    campaign_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"campaign_id\":\"campaign-20260413T100000000000Z\","
            "\"run_id\":\"20260413T100000000000Z\","
            f"\"generated_at_utc\":\"{now.isoformat()}\","
            "\"status\":\"running\","
            f"\"started_at\":\"{(now - timedelta(seconds=180)).isoformat()}\","
            "\"finished_at\":null,"
            "\"elapsed_seconds\":180,"
            "\"summary\":{\"batch_count\":1,\"pending_batch_count\":0,\"running_batch_count\":1,\"completed_batch_count\":0,\"partial_batch_count\":0,\"failed_batch_count\":0,\"skipped_batch_count\":0,\"total_candidate_count\":3,\"promoted_candidate_count\":1,\"rejected_candidate_count\":1,\"validated_candidate_count\":0,\"timed_out_candidate_count\":0,\"errored_candidate_count\":0},"
            "\"lineage\":{\"source_artifacts\":{\"run_batches_path\":\"research/run_batches_latest.v1.json\"}},"
            "\"batches\":[{\"batch_id\":\"batch-1\",\"batch_index\":1,\"strategy_family\":\"breakout\",\"interval\":\"1d\",\"status\":\"running\",\"started_at\":\"2026-04-13T10:00:00+00:00\",\"finished_at\":null,\"elapsed_seconds\":180,\"candidate_count\":3,\"completed_candidate_count\":1,\"promoted_candidate_count\":1,\"validated_candidate_count\":0,\"screening_rejected_count\":1,\"timed_out_count\":0,\"errored_count\":0,\"validation_error_count\":0,\"reason_code\":null,\"reason_detail\":null}]"
            "}"
        ),
        encoding="utf-8",
    )
    campaign_progress_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"campaign_id\":\"campaign-20260413T100000000000Z\","
            "\"run_id\":\"20260413T100000000000Z\","
            f"\"generated_at_utc\":\"{now.isoformat()}\","
            "\"status\":\"running\","
            f"\"started_at\":\"{(now - timedelta(seconds=180)).isoformat()}\","
            "\"finished_at\":null,"
            "\"elapsed_seconds\":180,"
            "\"summary\":{\"batch_count\":1,\"pending_batch_count\":0,\"running_batch_count\":1,\"completed_batch_count\":0,\"partial_batch_count\":0,\"failed_batch_count\":0,\"skipped_batch_count\":0,\"total_candidate_count\":3,\"promoted_candidate_count\":1,\"rejected_candidate_count\":1,\"validated_candidate_count\":0,\"timed_out_candidate_count\":0,\"errored_candidate_count\":0},"
            "\"active_batch\":{\"batch_id\":\"batch-1\",\"batch_index\":1,\"strategy_family\":\"breakout\",\"interval\":\"1d\",\"status\":\"running\",\"completed_candidates\":1,\"total_candidates\":3,\"elapsed_seconds\":180}"
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", state_path)
    monkeypatch.setattr(dash.research_artifacts, "RUN_PROGRESS_PATH", progress_path)
    monkeypatch.setattr(dash.research_artifacts, "RUN_CAMPAIGN_PATH", campaign_path)
    monkeypatch.setattr(dash.research_artifacts, "RUN_CAMPAIGN_PROGRESS_PATH", campaign_progress_path)
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["run_state"]["artifact_state"] == "valid"
    assert payload["run_state"]["artifact"]["status"] == "running"
    assert payload["run_progress"]["artifact"]["completed_items"] == 5
    assert payload["run_campaign"]["artifact"]["status"] == "running"
    assert payload["run_campaign_progress"]["artifact"]["active_batch"]["batch_id"] == "batch-1"
    assert payload["dashboard_observations"]["pid_live"] is True


def test_research_run_status_endpoint_with_stale_running_sidecar(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    now = datetime.now(UTC)
    stale_at = (now - timedelta(seconds=601)).isoformat()
    state_path = tmp_path / "run_state.v1.json"
    state_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"run_id\":\"20260413T100000000000Z\","
            "\"status\":\"running\","
            "\"pid\":123,"
            f"\"started_at_utc\":\"{(now - timedelta(seconds=900)).isoformat()}\","
            f"\"updated_at_utc\":\"{stale_at}\","
            "\"stage\":\"evaluation\","
            "\"status_reason\":\"research_run_started\","
            "\"heartbeat_timeout_s\":300,"
            "\"progress_path\":\"research/run_progress_latest.v1.json\","
            "\"manifest_path\":\"research/run_manifest_latest.v1.json\","
            "\"log_path\":\"logs/research/20260413T100000000000Z.jsonl\","
            "\"error\":null"
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", state_path)
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    payload = response.get_json()
    assert payload["dashboard_observations"]["stale_state_repaired"] is True
    assert payload["warnings"]
    repaired = json.loads(state_path.read_text(encoding="utf-8"))
    assert repaired["status"] == "aborted"


def test_research_run_status_endpoint_with_invalid_json(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    state_path = tmp_path / "run_state.v1.json"
    state_path.write_text("{ invalid", encoding="utf-8")
    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", state_path)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.get("/api/research/run-status")

    payload = response.get_json()
    assert payload["run_state"]["artifact_state"] == "invalid_json"
    assert payload["run_state"]["artifact_error"]


def test_research_run_trigger_accepted_when_idle(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(
        dash.research_runner.subprocess,
        "Popen",
        lambda *args, **kwargs: type("FakeProcess", (), {"pid": 999})(),
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

    now = datetime.now(UTC)
    state_path = tmp_path / "run_state.v1.json"
    state_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"run_id\":\"run-live\","
            "\"status\":\"running\","
            "\"pid\":123,"
            f"\"started_at_utc\":\"{(now - timedelta(seconds=60)).isoformat()}\","
            f"\"updated_at_utc\":\"{now.isoformat()}\","
            "\"stage\":\"evaluation\","
            "\"status_reason\":\"research_run_started\","
            "\"heartbeat_timeout_s\":300,"
            "\"progress_path\":\"research/run_progress_latest.v1.json\","
            "\"manifest_path\":\"research/run_manifest_latest.v1.json\","
            "\"log_path\":\"logs/research/run-live.jsonl\","
            "\"error\":null"
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", state_path)
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.post("/api/research/run")

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["accepted"] is False
    assert payload["launch_state"] == "blocked_active_run"


def test_research_run_trigger_repairs_stale_signal_and_starts(monkeypatch, tmp_path):
    from dashboard import dashboard as dash

    stale_at = (datetime.now(UTC) - timedelta(seconds=600)).isoformat()
    state_path = tmp_path / "run_state.v1.json"
    state_path.write_text(
        (
            "{"
            "\"version\":\"v1\","
            "\"run_id\":\"run-stale\","
            "\"status\":\"running\","
            "\"pid\":123,"
            "\"started_at_utc\":\"2026-04-13T10:00:00+00:00\","
            f"\"updated_at_utc\":\"{stale_at}\","
            "\"stage\":\"evaluation\","
            "\"status_reason\":\"research_run_started\","
            "\"heartbeat_timeout_s\":300,"
            "\"progress_path\":\"research/run_progress_latest.v1.json\","
            "\"manifest_path\":\"research/run_manifest_latest.v1.json\","
            "\"log_path\":\"logs/research/run-stale.jsonl\","
            "\"error\":null"
            "}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dash.research_artifacts, "RUN_STATE_PATH", state_path)
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)
    monkeypatch.setattr(
        dash.research_runner.subprocess,
        "Popen",
        lambda *args, **kwargs: type("FakeProcess", (), {"pid": 888})(),
    )

    dash.app.testing = True
    client = dash.app.test_client()
    _set_operator_session(client)
    response = client.post("/api/research/run")

    assert response.status_code == 202
    payload = response.get_json()
    assert payload["accepted"] is True
    assert payload["launch_state"] == "started"
    assert payload["warnings"]


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
