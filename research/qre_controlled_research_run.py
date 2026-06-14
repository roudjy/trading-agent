"""One-command controlled QRE research runner.

This operator runner materializes a bounded two-loop research flow:

hypothesis -> preset -> controlled campaign intent -> metric evidence ->
analysis -> learning -> next hypothesis/action.

It deliberately does not call run_research, campaign_launcher, subprocesses,
network, validation, broker/risk, paper/shadow/live, candidate promotion, or
strategy/preset mutation. True metrics are only allowed when a safe cache-only
no-public-output-mutation path exists; until then the runner emits structured
bounded metric evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research import qre_cache_only_metric_path as cache_metric_path
from research import qre_controlled_discovery_subset_adapter as subset_adapter
from research import qre_controlled_subset_candidate_feasibility as feasibility
from research import qre_controlled_subset_candidate_plan as candidate_plan
from research import qre_controlled_subset_local_runner_harness as local_harness
from research import qre_controlled_subset_runner_dry_run as runner_dry_run
from research import qre_controlled_subset_screening_dry_run_executor as screening_executor
from research import qre_controlled_subset_screening_dry_run_plan as screening_plan


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_research_run"

DEFAULT_INPUT_PATH: Final[Path] = Path(
    "logs/qre_controlled_subset_screening_dry_run_executor/latest.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_research_run")
DEFAULT_SUBSET_SOURCE_PATH: Final[Path] = Path(
    "logs/qre_controlled_discovery_grid_inspection/safe_executable_subset.json"
)

CONTROLLED_ASSETS: Final[tuple[str, ...]] = (
    "AAPL",
    "ADYEN",
    "ASML",
    "EWJ",
    "MSFT",
    "SONY",
    "SPY",
    "TM",
)
CONTROLLED_ASSET_SET: Final[frozenset[str]] = frozenset(CONTROLLED_ASSETS)
EXPECTED_REGION_BY_SYMBOL: Final[dict[str, str]] = {
    "AAPL": "US",
    "ADYEN": "NL/EU",
    "ASML": "NL/EU",
    "EWJ": "ETFs/context",
    "MSFT": "US",
    "SONY": "Asia/proxies",
    "SPY": "ETFs/context",
    "TM": "Asia/proxies",
}
EXPECTED_ASSET_CLASS_BY_SYMBOL: Final[dict[str, str]] = {
    "AAPL": "equity",
    "ADYEN": "equity",
    "ASML": "equity",
    "EWJ": "etf",
    "MSFT": "equity",
    "SONY": "equity",
    "SPY": "etf",
    "TM": "equity",
}
EXPECTED_PRESET: Final[str] = "trend_continuation_daily_v1"
EXPECTED_TIMEFRAME: Final[str] = "1d"

PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)
FORBIDDEN_ASSET_CLASSES: Final[frozenset[str]] = frozenset({"crypto", "crypto_legacy"})
FORBIDDEN_SYMBOLS: Final[frozenset[str]] = frozenset({"BTC", "ETH", "SOL", "DOGE", "XRP"})


class ControlledResearchRunError(RuntimeError):
    """Raised when the controlled research runner cannot proceed safely."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ControlledResearchRunError(f"input artifact does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": None}
    return {"exists": True, "sha256": _sha256_bytes(path.read_bytes())}


def _protected_fingerprints() -> dict[str, dict[str, Any]]:
    return {path.as_posix(): _file_fingerprint(path) for path in PROTECTED_PUBLIC_OUTPUTS}


def _assert_protected_outputs_unchanged(before: dict[str, dict[str, Any]]) -> None:
    after = _protected_fingerprints()
    if before != after:
        raise ControlledResearchRunError("protected public research artifacts changed")


def _assert_output_path_inside(output_dir: Path, path: Path) -> None:
    root = output_dir.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ControlledResearchRunError(f"refusing write outside output dir: {path.as_posix()}")


def _write_text(output_dir: Path, path: Path, content: str) -> None:
    _assert_output_path_inside(output_dir, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def ensure_controlled_input(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    subset_source_path: Path = DEFAULT_SUBSET_SOURCE_PATH,
    write_intermediates: bool = True,
) -> Path:
    """Materialize the existing controlled subset chain if needed."""

    if input_path.exists():
        return input_path
    if input_path != DEFAULT_INPUT_PATH:
        raise ControlledResearchRunError(f"custom input missing: {input_path.as_posix()}")

    subset = subset_adapter.build_subset_adapter_packet(subset_source_path)
    if write_intermediates:
        subset_adapter.write_outputs(subset)

    plan = candidate_plan.build_candidate_plan()
    if write_intermediates:
        candidate_plan.write_outputs(plan)

    feasible = feasibility.build_feasibility_report()
    if write_intermediates:
        feasibility.write_outputs(feasible)

    runner = runner_dry_run.build_runner_dry_run_packet()
    if write_intermediates:
        runner_dry_run.write_outputs(runner)

    harness = local_harness.build_local_runner_harness_packet()
    if write_intermediates:
        local_harness.write_outputs(harness)

    screen_plan = screening_plan.build_screening_dry_run_plan()
    if write_intermediates:
        screening_plan.write_outputs(screen_plan)

    executed = screening_executor.build_screening_dry_run_executor_packet()
    if write_intermediates:
        screening_executor.write_outputs(executed)

    if not input_path.exists():
        raise ControlledResearchRunError("controlled input chain did not produce executor artifact")
    return input_path


def _records_from_packet(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ControlledResearchRunError("controlled input must be a JSON object")
    if payload.get("report_kind") != "qre_controlled_subset_screening_dry_run_executor":
        raise ControlledResearchRunError("input_report_kind_not_screening_dry_run_executor")
    records = payload.get("screening_dry_run_result_records")
    if not isinstance(records, list):
        raise ControlledResearchRunError("screening_dry_run_result_records_missing")
    if not all(isinstance(record, dict) for record in records):
        raise ControlledResearchRunError("screening_dry_run_result_records_malformed")
    return list(records)


def _validate_records(records: list[dict[str, Any]]) -> None:
    blockers: list[str] = []
    symbols = [str(record.get("instrument_symbol") or "") for record in records]
    counts = Counter(symbols)
    duplicates = sorted(symbol for symbol, count in counts.items() if count > 1)
    if duplicates:
        blockers.append("duplicate_controlled_universe_rows:" + ",".join(duplicates))
    if set(symbols) != set(CONTROLLED_ASSETS):
        blockers.append("controlled_universe_mismatch:" + ",".join(sorted(symbols)))
    if len(records) != len(CONTROLLED_ASSETS):
        blockers.append(f"controlled_universe_row_count_not_8:{len(records)}")

    false_flags = (
        "validation_executed",
        "execution_performed",
        "subprocess_called",
        "network_called",
        "external_data_called",
        "run_research_called",
        "campaign_launcher_called",
        "candidate_promotion_allowed",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
        "broker_execution_allowed",
        "risk_authority_allowed",
        "candidate_registry_mutated",
        "campaign_artifacts_mutated",
        "queue_mutated",
        "strategy_registered",
        "preset_mutated",
        "research_latest_mutated",
        "strategy_matrix_mutated",
    )
    for index, record in enumerate(records, start=1):
        symbol = str(record.get("instrument_symbol") or "")
        upper = symbol.upper()
        asset_class = str(record.get("asset_class") or "").lower()
        if asset_class in FORBIDDEN_ASSET_CLASSES:
            blockers.append(f"row_{index}:forbidden_asset_class:{asset_class}")
        if upper.endswith("-USD") or upper in FORBIDDEN_SYMBOLS:
            blockers.append(f"row_{index}:crypto_symbol_rejected:{symbol}")
        if symbol not in CONTROLLED_ASSET_SET:
            blockers.append(f"row_{index}:symbol_outside_controlled_universe:{symbol}")
        expected_region = EXPECTED_REGION_BY_SYMBOL.get(symbol)
        if expected_region is not None and record.get("region") != expected_region:
            blockers.append(f"row_{index}:region_drift:{symbol}:{record.get('region')}")
        expected_class = EXPECTED_ASSET_CLASS_BY_SYMBOL.get(symbol)
        if expected_class is not None and asset_class != expected_class:
            blockers.append(f"row_{index}:asset_class_drift:{symbol}:{asset_class}")
        if record.get("behavior_preset_id") != EXPECTED_PRESET:
            blockers.append(f"row_{index}:preset_drift:{record.get('behavior_preset_id')}")
        if record.get("timeframe") != EXPECTED_TIMEFRAME:
            blockers.append(f"row_{index}:timeframe_drift:{record.get('timeframe')}")
        if record.get("screening_result") != "metadata_only_pass":
            blockers.append(f"row_{index}:screening_result_not_pass:{symbol}")
        for flag in false_flags:
            if record.get(flag) is not False:
                blockers.append(f"row_{index}:{flag}_not_false")
    if blockers:
        raise ControlledResearchRunError("controlled input validation failed: " + "; ".join(blockers))


def _run_group_id(records: list[dict[str, Any]], loops: int) -> str:
    seed = {
        "assets": sorted(record["instrument_symbol"] for record in records),
        "preset": EXPECTED_PRESET,
        "timeframe": EXPECTED_TIMEFRAME,
        "loops": loops,
    }
    digest = _sha256_bytes(json.dumps(seed, sort_keys=True).encode("utf-8"))[:16]
    return f"controlled-research-{digest}"


def _bounded_metric_evidence(records: list[dict[str, Any]]) -> dict[str, Any]:
    assets = [str(record["instrument_symbol"]) for record in records]
    return cache_metric_path.build_cache_only_metric_evidence(
        assets=assets,
        timeframe=EXPECTED_TIMEFRAME,
    )


def _build_loop(
    *,
    loop_index: int,
    run_group_id: str,
    records: list[dict[str, Any]],
    previous_learning: dict[str, Any] | None,
) -> dict[str, Any]:
    assets = sorted(record["instrument_symbol"] for record in records)
    if previous_learning is None:
        hypothesis = (
            "The exact controlled non-crypto universe may support a daily trend-continuation "
            "research path if metadata readiness remains clean and metric evidence can be "
            "collected without public-output mutation."
        )
        hypothesis_mode = "initial_controlled_hypothesis"
    else:
        hypothesis = (
            "Loop 1 showed clean controlled metadata but blocked true metrics; keep the same "
            "universe and preset, and make the next action a safe cache-only metric path "
            "instead of rotating assets."
        )
        hypothesis_mode = "learning_adjusted_hypothesis"

    preset = {
        "preset_id": EXPECTED_PRESET,
        "timeframe": EXPECTED_TIMEFRAME,
        "selection_mode": "existing_controlled_read_only_preset",
        "preset_mutated": False,
    }
    campaign_intent = {
        "campaign_intent_id": f"{run_group_id}__campaign_intent__{loop_index}",
        "campaign_mode": "controlled_campaign_intent_no_launcher_no_mutation",
        "controlled_universe": assets,
        "selected_preset_id": EXPECTED_PRESET,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "campaign_registry_mutated": False,
        "candidate_promotion_allowed": False,
    }
    metric_evidence = _bounded_metric_evidence(records)
    true_metrics_available = metric_evidence["true_metrics_available"] is True
    metric_blockers = sorted(
        {
            str(row.get("blocker"))
            for row in metric_evidence.get("per_asset", [])
            if isinstance(row, dict) and row.get("blocker")
        }
    )
    analysis = {
        "analysis_id": f"{run_group_id}__analysis__{loop_index}",
        "metric_evidence_mode": metric_evidence["metric_mode"],
        "true_metrics_available": true_metrics_available,
        "analysis_statement": (
            "Controlled campaign intent has cache-only exact-universe metric evidence "
            "from local read-only artifacts."
            if true_metrics_available
            else "Controlled campaign intent is materially complete, but true metrics remain "
            "blocked by incomplete safe cache-only exact-universe metric evidence."
        ),
        "content_blockers": [] if true_metrics_available else (metric_blockers or [cache_metric_path.SAFE_METRIC_BLOCKER]),
        "safety_blockers": [],
    }
    learning = {
        "learning_feedback_id": f"{run_group_id}__learning__{loop_index}",
        "consumes_previous_learning_feedback_id": (
            previous_learning.get("learning_feedback_id") if previous_learning else None
        ),
        "learning_result": (
            "cache_only_metric_evidence_available"
            if true_metrics_available
            else "bounded_metric_evidence_requires_safe_metric_runner"
        ),
        "learning_statement": (
            "Do not rotate the controlled universe. The cache-only metric evidence path "
            "is available from local artifacts; keep any follow-up bounded by review gates."
            if true_metrics_available
            else "Do not rotate the controlled universe. The hypothesis/preset path is ready "
            "for metric collection, but the next implementation target is a cache-only "
            "no-public-output-mutation metric runner."
        ),
    }
    next_action = {
        "next_action_id": f"{run_group_id}__next_action__{loop_index}",
        "recommended_action": (
            "operator_review_cache_only_metric_evidence"
            if true_metrics_available
            else "add_cache_only_metric_path"
        ),
        "operator_command_after_next_pr": (
            "python -m research.qre_controlled_research_run --write --loops 2"
        ),
        "rationale": learning["learning_statement"],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_group_id": run_group_id,
        "run_id": f"{run_group_id}__loop__{loop_index}",
        "loop_index": loop_index,
        "created_at_utc": _utcnow(),
        "controlled_universe": assets,
        "flow": [
            "hypothesis",
            "preset",
            "controlled_campaign_intent",
            "metric_evidence",
            "analysis",
            "learning",
            "next_hypothesis_or_action",
        ],
        "hypothesis": {
            "hypothesis_id": f"{run_group_id}__hypothesis__{loop_index}",
            "hypothesis_mode": hypothesis_mode,
            "statement": hypothesis,
            "not_alpha_claim": True,
            "not_trade_signal": True,
        },
        "preset_selection": preset,
        "controlled_campaign_intent": campaign_intent,
        "metric_evidence": metric_evidence,
        "analysis": analysis,
        "learning_feedback": learning,
        "next_hypothesis_or_action": next_action,
        "safety": {
            "run_research_called": False,
            "campaign_launcher_called": False,
            "validation_executed": False,
            "execution_performed": False,
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "candidate_promotion_allowed": False,
            "research_latest_mutated": False,
            "strategy_matrix_mutated": False,
        },
    }


def build_controlled_research_packet(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    loops: int = 2,
) -> dict[str, Any]:
    if loops != 2:
        raise ControlledResearchRunError("--loops must be exactly 2 for this controlled runner")
    payload = _read_json(input_path)
    records = _records_from_packet(payload)
    _validate_records(records)
    run_group_id = _run_group_id(records, loops)

    runs: list[dict[str, Any]] = []
    previous_learning: dict[str, Any] | None = None
    for loop_index in range(1, loops + 1):
        run = _build_loop(
            loop_index=loop_index,
            run_group_id=run_group_id,
            records=records,
            previous_learning=previous_learning,
        )
        runs.append(run)
        previous_learning = run["learning_feedback"]

    true_metric_count = sum(
        1 for run in runs if run["metric_evidence"]["metric_mode"] == "true_metrics"
    )
    bounded_count = sum(
        1
        for run in runs
        if run["metric_evidence"]["metric_mode"] == "bounded_metric_evidence"
    )
    summary = {
        "controlled_research_run_ready": True,
        "loop_count": len(runs),
        "full_loop_materialized": True,
        "hypothesis_count": len(runs),
        "preset_selection_count": len(runs),
        "controlled_campaign_intent_count": len(runs),
        "metric_evidence_count": len(runs),
        "analysis_count": len(runs),
        "learning_feedback_count": len(runs),
        "next_action_count": len(runs),
        "true_metric_count": true_metric_count,
        "bounded_metric_evidence_count": bounded_count,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "validation_executed": False,
        "execution_performed": False,
        "paper_shadow_live_allowed": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "final_recommendation": "add_cache_only_metric_path",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_group_id": run_group_id,
        "created_at_utc": _utcnow(),
        "input_path": input_path.as_posix(),
        "summary": summary,
        "authority_boundaries": {
            "controlled_exact_universe_only": True,
            "writes_only_qre_controlled_research_run_logs": True,
            "does_not_call_run_research": True,
            "does_not_call_campaign_launcher": True,
            "does_not_call_subprocess": True,
            "does_not_call_network": True,
            "does_not_execute_validation": True,
            "does_not_activate_paper_shadow_live": True,
            "does_not_call_broker_or_risk": True,
            "does_not_promote_candidates": True,
            "does_not_register_strategy_or_preset": True,
            "does_not_mutate_protected_public_outputs": True,
        },
        "runs": runs,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    true_available = "available" if summary["true_metric_count"] else "unavailable"
    bounded_available = (
        "available" if summary["bounded_metric_evidence_count"] else "unavailable"
    )
    lines = [
        "# QRE Controlled Research Run",
        "",
        "- One-command controlled research run completed.",
        f"- Loops executed: {summary['loop_count']}.",
        "- Flow completed:",
        "  hypothesis -> preset -> controlled campaign intent -> metric evidence -> analysis -> learning -> next hypothesis/action.",
        f"- True metrics: {true_available}.",
        f"- Bounded metric evidence: {bounded_available}.",
        "- No paper/shadow/live.",
        "- No broker/risk authority.",
        "- No protected artifact mutation.",
        f"- Next recommended action: {summary['final_recommendation']}",
        "",
    ]
    for run in packet["runs"]:
        metric = run["metric_evidence"]
        first_asset = metric["per_asset"][0]
        lines.extend(
            [
                f"## Loop {run['loop_index']}",
                f"- hypothesis: {run['hypothesis']['statement']}",
                f"- preset: {run['preset_selection']['preset_id']}",
                f"- campaign intent: {run['controlled_campaign_intent']['campaign_intent_id']}",
                f"- metric evidence mode: {metric['metric_mode']}",
                f"- key metric/blocker: {first_asset['symbol']}={first_asset['blocker']}",
                f"- learning: {run['learning_feedback']['learning_statement']}",
                f"- next action: {run['next_hypothesis_or_action']['recommended_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def write_outputs(packet: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    latest_path = output_dir / "latest.json"
    summary_path = output_dir / "operator_summary.md"
    ledger_path = output_dir / "ledger.jsonl"
    runs_dir = output_dir / "runs"

    _write_text(output_dir, latest_path, _json_dumps(packet))
    _write_text(output_dir, summary_path, render_operator_summary(packet))

    run_paths: list[str] = []
    for run in packet["runs"]:
        run_path = runs_dir / f"{run['run_id']}.json"
        _write_text(output_dir, run_path, _json_dumps(run))
        run_paths.append(run_path.as_posix())

    ledger_lines = [
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "report_kind": REPORT_KIND,
                "run_group_id": packet["run_group_id"],
                "run_id": run["run_id"],
                "loop_index": run["loop_index"],
                "metric_mode": run["metric_evidence"]["metric_mode"],
                "learning_feedback_id": run["learning_feedback"]["learning_feedback_id"],
                "next_action": run["next_hypothesis_or_action"]["recommended_action"],
            },
            sort_keys=True,
        )
        for run in packet["runs"]
    ]
    _write_text(output_dir, ledger_path, "\n".join(ledger_lines) + "\n")
    return {
        "latest": latest_path.as_posix(),
        "operator_summary": summary_path.as_posix(),
        "ledger": ledger_path.as_posix(),
        "runs": run_paths,
    }


def run_controlled_research(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    loops: int = 2,
    write: bool = False,
) -> dict[str, Any]:
    before = _protected_fingerprints()
    materialized_input = ensure_controlled_input(input_path=input_path, write_intermediates=write)
    packet = build_controlled_research_packet(input_path=materialized_input, loops=loops)
    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)
    _assert_protected_outputs_unchanged(before)
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one-command controlled QRE research loop.")
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--loops", type=int, default=2)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    packet = run_controlled_research(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        loops=args.loops,
        write=args.write,
    )
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
