from pathlib import Path


def test_dashboard_price_refresh_uses_repository(monkeypatch):
    from dashboard import dashboard as dash

    captured = {}

    class StubRepository:
        def get_latest_prices(self, instruments):
            captured["symbols"] = [instrument.id for instrument in instruments]
            return {
                "NVDA": {"prijs": 100.0, "type": "equity"},
                "BTC/EUR": {"prijs": 90000.0, "type": "crypto"},
            }

    monkeypatch.setattr(dash, "MARKET_REPOSITORY", StubRepository())
    monkeypatch.setattr(dash, "_start_daemon_timer", lambda delay, callback: None)

    dash._ververs_prijzen()

    assert "NVDA" in captured["symbols"]
    assert "BTC/EUR" in captured["symbols"]
    assert dash._prijzen_cache["NVDA"]["prijs"] == 100.0
    assert dash._prijzen_cache["BTC/EUR"]["prijs"] == 90000.0


def test_dashboard_module_no_longer_imports_yfinance():
    dashboard_source = Path("dashboard/dashboard.py").read_text(encoding="utf-8")

    assert "import yfinance" not in dashboard_source
