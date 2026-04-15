from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_TIMED_OUT,
    build_screening_runtime_records,
    build_screening_sidecar_payload,
    execute_screening_candidate,
)


class FakeClock:
    def __init__(self, start: datetime):
        self.current = start
        self.mono = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.mono += seconds
        self.current += timedelta(seconds=seconds)


def test_screening_sidecar_payload_counts_are_deterministic():
    records = build_screening_runtime_records(
        candidates=[
            {"candidate_id": "b", "strategy_name": "beta", "asset": "ETH-USD", "interval": "1h"},
            {"candidate_id": "a", "strategy_name": "alpha", "asset": "BTC-USD", "interval": "1d"},
        ],
        budget_seconds=30,
    )
    records[0]["final_status"] = "rejected"
    records[1]["final_status"] = "passed"

    payload = build_screening_sidecar_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC),
        records=records,
    )

    assert payload["summary"] == {
        "candidate_count": 2,
        "pending_count": 0,
        "running_count": 0,
        "passed_count": 1,
        "rejected_count": 1,
        "timed_out_count": 0,
        "errored_count": 0,
        "skipped_count": 0,
    }
    assert [item["candidate_id"] for item in payload["candidates"]] == ["a", "b"]


def test_execute_screening_candidate_times_out_cooperatively():
    clock = FakeClock(datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC))

    class SlowEngine:
        def __init__(self):
            self.last_evaluation_report = None

        def run(self, strategie_func, assets, interval="1d"):
            clock.advance(2)
            self.last_evaluation_report = {
                "evaluation_samples": {
                    "daily_returns": [0.01, -0.01],
                }
            }
            return {
                "totaal_trades": 12,
                "goedgekeurd": True,
            }

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: SimpleNamespace(params=params),
            "params": {"periode": [14, 21, 28]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=SlowEngine(),
        budget_seconds=1,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )

    assert outcome["final_status"] == FINAL_STATUS_TIMED_OUT
    assert outcome["reason_code"] == "candidate_budget_exceeded"
    assert outcome["samples_total"] == 3
    assert outcome["samples_completed"] == 1
    assert outcome["legacy_decision"]["reason"] == "candidate_budget_exceeded"


def test_execute_screening_candidate_surfaces_candidate_error():
    clock = FakeClock(datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC))

    class BrokenEngine:
        def run(self, strategie_func, assets, interval="1d"):
            raise RuntimeError("boom")

    outcome = execute_screening_candidate(
        strategy={
            "factory": lambda **params: None,
            "params": {"periode": [14]},
        },
        candidate={"asset": "BTC-USD", "interval": "1d"},
        engine=BrokenEngine(),
        budget_seconds=30,
        max_samples=3,
        now_source=clock.now,
        monotonic_source=clock.monotonic,
    )

    assert outcome["final_status"] == FINAL_STATUS_ERRORED
    assert outcome["reason_code"] == "screening_candidate_error"
    assert outcome["reason_detail"] == "boom"
    assert outcome["samples_completed"] == 0
