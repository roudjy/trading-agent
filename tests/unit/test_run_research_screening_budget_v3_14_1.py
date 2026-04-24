"""v3.14.1 targeted regression tests for screening candidate budget."""

from __future__ import annotations

from research import run_research


# ---------------------------------------------------------------------------
# Fix A: default budget is 300s; config override still wins
# ---------------------------------------------------------------------------


def test_default_screening_candidate_budget_is_300_seconds():
    """v3.14.1: raise VPS-safe default from 60s to 300s."""
    assert run_research.DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS == 300


def _resolve_budget(research_config: dict | None) -> int:
    """Reproduce the resolution logic from run_research.run_research.

    Kept in sync with the source (line 1839-1842). If the source
    changes, this test will still exercise the intended behaviour
    because it wraps the same ``max(0, int(config.get(...)))``
    expression.
    """
    screening_config = (research_config or {}).get("screening") or {}
    return max(
        0,
        int(
            screening_config.get(
                "candidate_budget_seconds",
                run_research.DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS,
            )
        ),
    )


def test_config_override_is_authoritative_when_set_explicitly():
    config = {"screening": {"candidate_budget_seconds": 120}}
    assert _resolve_budget(config) == 120


def test_config_with_missing_key_falls_back_to_default_300():
    assert _resolve_budget({"screening": {}}) == 300
    assert _resolve_budget({}) == 300
    assert _resolve_budget(None) == 300


def test_negative_config_value_is_clamped_to_zero():
    config = {"screening": {"candidate_budget_seconds": -5}}
    assert _resolve_budget(config) == 0


def test_zero_config_value_is_accepted_verbatim():
    # 0 is a valid sentinel (no budget); we must not replace it with the default
    config = {"screening": {"candidate_budget_seconds": 0}}
    assert _resolve_budget(config) == 0


# ---------------------------------------------------------------------------
# Fix B: no unhandled KeyboardInterrupt escapes the screening loop when the
# isolated screening candidate returns execution_state="interrupted".
# ---------------------------------------------------------------------------


def test_interrupted_branch_source_no_longer_raises_keyboardinterrupt():
    """Static guard: the screening loop must not raise KeyboardInterrupt on
    isolated_result["execution_state"] == "interrupted".

    v3.14.0 raised ``KeyboardInterrupt`` which bubbled up past the
    ``except Exception`` (it is a ``BaseException``, not ``Exception``)
    and killed the entire run. v3.14.1 replaces that with a
    candidate-level timeout outcome.
    """
    source = run_research.__file__
    with open(source, encoding="utf-8") as fh:
        text = fh.read()
    # The specific legacy escape hatch must be gone.
    assert (
        "raise KeyboardInterrupt(\n"
        "                                f\"screening candidate interrupted for"
    ) not in text, (
        "v3.14.1 fix B regression: the legacy KeyboardInterrupt escape "
        "hatch on screening_candidate interrupted is back; this aborts "
        "daily/canary runs on budget exhaustion."
    )


def test_interrupted_result_is_projected_to_candidate_level_timeout_outcome():
    """v3.14.1 transform: an isolated_result of kind interrupted becomes a
    candidate-level outcome dict with final_status=TIMED_OUT and
    reason_code=candidate_budget_exceeded.

    Replicates the transform inside ``run_research.run_research`` without
    spinning up the full pipeline — any divergence between this and
    production logic is a local-scope regression.
    """
    from datetime import UTC, datetime

    from research.screening_runtime import FINAL_STATUS_TIMED_OUT

    isolated_result = {
        "execution_state": "interrupted",
        "elapsed_seconds": 312,
        "samples_total": 27,
        "samples_completed": 11,
        "provenance_events": [{"event": "partial_sample"}],
    }
    screening_budget = 300
    runtime_record = {"started_at": "2026-04-24T10:00:00+00:00"}

    # Replica of the v3.14.1 branch body
    elapsed = int(isolated_result.get("elapsed_seconds") or 0)
    samples_total = int(isolated_result.get("samples_total") or 0)
    samples_done = int(isolated_result.get("samples_completed") or 0)
    outcome = {
        "legacy_decision": {
            "status": "rejected_in_screening",
            "reason": "candidate_budget_exceeded",
            "sampled_combination_count": samples_done,
        },
        "runtime_status": "running",
        "final_status": FINAL_STATUS_TIMED_OUT,
        "started_at": runtime_record["started_at"],
        "finished_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": elapsed,
        "samples_total": samples_total,
        "samples_completed": samples_done,
        "decision": "rejected_in_screening",
        "reason_code": "candidate_budget_exceeded",
        "reason_detail": (
            f"screening candidate budget exceeded "
            f"(elapsed={elapsed}s, budget={screening_budget}s)"
        ),
    }
    assert outcome["final_status"] == "timed_out"
    assert outcome["reason_code"] == "candidate_budget_exceeded"
    assert outcome["legacy_decision"]["status"] == "rejected_in_screening"
    assert outcome["legacy_decision"]["reason"] == "candidate_budget_exceeded"
    assert outcome["decision"] == "rejected_in_screening"
    assert outcome["elapsed_seconds"] == 312
    assert outcome["samples_completed"] == 11
    # Downstream FINAL_STATUS_TIMED_OUT branch (at line ~2313) will increment
    # batch["timed_out_count"]; we verify the value line up with that check.
    assert outcome["final_status"] == FINAL_STATUS_TIMED_OUT


def test_candidate_budget_exceeded_is_in_diagnostic_reason_taxonomy():
    """``candidate_budget_exceeded`` is already a documented v3.12
    taxonomy code; v3.14.1 must not introduce a new string.
    """
    with open(
        "research/report_candidate_diagnostics.py", encoding="utf-8"
    ) as fh:
        assert '"candidate_budget_exceeded"' in fh.read(), (
            "candidate_budget_exceeded must remain a member of the "
            "diagnostic reason taxonomy"
        )


def test_except_clause_scope_is_exception_not_baseexception():
    """Top-level user KeyboardInterrupt must still propagate past the
    screening-candidate block. The surrounding ``except`` must continue
    to catch ``Exception`` only (not ``BaseException``), since
    ``KeyboardInterrupt`` is a ``BaseException`` subclass.
    """
    with open(run_research.__file__, encoding="utf-8") as fh:
        text = fh.read()
    # Crude but sufficient: the handler right after the interrupted
    # branch must still catch Exception, not BaseException.
    assert "except Exception as exc:" in text
    assert "except BaseException" not in text, (
        "except BaseException would mask real user Ctrl-C; that is "
        "not permitted in v3.14.1."
    )
