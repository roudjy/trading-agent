"""Unit tests for the explicit live execution gate."""

import json


def test_live_gate_arm_and_disarm(monkeypatch, tmp_path):
    from automation import live_gate
    from reporting import audit_log

    state_path = tmp_path / "state" / "live_armed.json"
    secret_path = tmp_path / "state" / "live_gate.secret"
    audit_path = tmp_path / "logs" / "audit.log"

    monkeypatch.setattr(live_gate, "STATE_PATH", state_path)
    monkeypatch.setattr(live_gate, "SECRET_PATH", secret_path)
    monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", audit_path)

    assert live_gate.is_live_armed() is False

    live_gate.arm(operator_id="joery", candidate_id="candidate-1", ttl_hours=2)
    assert live_gate.is_live_armed() is True

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["operator_id"] == "joery"
    assert payload["candidate_id"] == "candidate-1"
    assert payload["signature"]

    live_gate.disarm(reason="manual stop")
    assert live_gate.is_live_armed() is False

    audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(audit_lines) == 2


def test_live_gate_rejects_tampered_state(monkeypatch, tmp_path):
    from automation import live_gate
    from reporting import audit_log

    state_path = tmp_path / "state" / "live_armed.json"
    secret_path = tmp_path / "state" / "live_gate.secret"
    audit_path = tmp_path / "logs" / "audit.log"

    monkeypatch.setattr(live_gate, "STATE_PATH", state_path)
    monkeypatch.setattr(live_gate, "SECRET_PATH", secret_path)
    monkeypatch.setattr(audit_log, "AUDIT_LOG_PATH", audit_path)

    live_gate.arm(operator_id="joery", candidate_id="candidate-1", ttl_hours=1)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["candidate_id"] = "tampered"
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    assert live_gate.is_live_armed() is False


def test_order_executor_requires_live_gate(monkeypatch):
    from agent.execution.order_executor import OrderExecutor

    config = {
        "kapitaal": {"start": 1000.0},
        "exchanges": {
            "bitvavo": {"actief": True, "paper_trading": False, "api_key": "", "api_secret": ""},
            "kraken": {"actief": False, "paper_trading": True, "api_key": "", "api_secret": ""},
            "ibkr": {"actief": True, "paper_trading": False},
        },
    }

    monkeypatch.setattr("agent.execution.order_executor.live_gate.is_live_armed", lambda: False)
    executor = OrderExecutor(config)
    assert executor._is_paper_mode("BTC/EUR") is True
    assert executor._is_paper_mode("NVDA") is True

    monkeypatch.setattr("agent.execution.order_executor.live_gate.is_live_armed", lambda: True)
    assert executor._is_paper_mode("BTC/EUR") is False
    assert executor._is_paper_mode("NVDA") is False


def test_run_enforces_live_gate(monkeypatch):
    import run

    config = {
        "exchanges": {
            "bitvavo": {"paper_trading": False},
            "ibkr": {"paper_trading": True},
        }
    }

    monkeypatch.setattr("run.live_gate.is_live_armed", lambda: False)
    run._enforce_live_gate(config)

    assert config["exchanges"]["bitvavo"]["paper_trading"] is True
