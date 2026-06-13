"""Bounded autonomous QRE market-research loop controller.

The controller composes the existing controlled research run into a V1/V2/V3
foundation:

* V1: market-intake -> analysis -> hypothesis -> preset -> campaign intent ->
  metric evidence -> result analysis -> learning -> next seed -> next action.
* V2: code-required next actions create ADE/Codex build-request artifacts.
* V3: post-merge continuation is represented as a data contract only.

It never executes builds, opens PRs, merges, trades, calls run_research, calls
campaign_launcher, or mutates protected public research outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research import qre_build_request_writer as build_requests
from research import qre_controlled_research_run as controlled_run
from research import qre_next_action_classifier as action_classifier


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_autonomous_market_research_loop"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_autonomous_market_research_loop")
DEFAULT_CONTROLLED_LATEST: Final[Path] = Path("logs/qre_controlled_research_run/latest.json")
PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)
CONTROLLED_UNIVERSE: Final[tuple[str, ...]] = controlled_run.CONTROLLED_ASSETS
EXPECTED_PRESET: Final[str] = controlled_run.EXPECTED_PRESET
EXPECTED_TIMEFRAME: Final[str] = controlled_run.EXPECTED_TIMEFRAME


class AutonomousMarketResearchLoopError(RuntimeError):
    """Raised when the autonomous controller cannot proceed safely."""


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _assert_protected_unchanged(before: dict[str, dict[str, Any]]) -> None:
    if before != _protected_fingerprints():
        raise AutonomousMarketResearchLoopError("protected public research artifacts changed")


def _assert_inside(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise AutonomousMarketResearchLoopError(f"refusing write outside output dir: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise AutonomousMarketResearchLoopError(f"input artifact unavailable: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousMarketResearchLoopError(f"input artifact malformed: {path}") from exc
    if not isinstance(parsed, dict):
        raise AutonomousMarketResearchLoopError("input artifact must be a JSON object")
    return parsed


def _load_or_build_controlled_packet(path: Path | None = None) -> dict[str, Any]:
    source = path or DEFAULT_CONTROLLED_LATEST
    if source.exists():
        packet = _read_json(source)
    else:
        packet = controlled_run.run_controlled_research(write=False)
    if packet.get("report_kind") != controlled_run.REPORT_KIND:
        raise AutonomousMarketResearchLoopError("controlled research packet has unexpected kind")
    summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    forbidden_true = (
        "run_research_called",
        "campaign_launcher_called",
        "validation_executed",
        "execution_performed",
        "paper_shadow_live_allowed",
        "research_latest_mutated",
        "strategy_matrix_mutated",
    )
    for key in forbidden_true:
        if summary.get(key) is not False:
            raise AutonomousMarketResearchLoopError(f"controlled packet safety flag not false: {key}")
    return packet


def _cycle_id(run_group_id: str, cycle_index: int) -> str:
    seed = f"{run_group_id}|{cycle_index}|{','.join(CONTROLLED_UNIVERSE)}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"qre-auto-cycle-{cycle_index:04d}-{digest}"


def _latest_inner_run(controlled_packet: dict[str, Any]) -> dict[str, Any]:
    runs = controlled_packet.get("runs")
    if not isinstance(runs, list) or not runs:
        raise AutonomousMarketResearchLoopError("controlled packet has no runs")
    run = runs[-1]
    if not isinstance(run, dict):
        raise AutonomousMarketResearchLoopError("controlled run row malformed")
    return run


def _market_intake(cycle_index: int, previous_seed: dict[str, Any] | None) -> dict[str, Any]:
    if previous_seed is None:
        return {
            "source": "controlled_default",
            "statement": (
                "Start from the exact controlled non-crypto universe and daily "
                "trend-continuation preset; no external market fetch is allowed."
            ),
            "universe": list(CONTROLLED_UNIVERSE),
            "preset": EXPECTED_PRESET,
            "timeframe": EXPECTED_TIMEFRAME,
        }
    return {
        "source": "previous_learning_seed",
        "statement": str(previous_seed.get("statement") or ""),
        "universe": list(previous_seed.get("universe") or CONTROLLED_UNIVERSE),
        "preset": str(previous_seed.get("preset") or EXPECTED_PRESET),
        "timeframe": str(previous_seed.get("timeframe") or EXPECTED_TIMEFRAME),
        "previous_seed_id": previous_seed.get("seed_id"),
        "cycle_index": cycle_index,
    }


def _validate_market_intake(intake: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    symbols = intake.get("universe")
    if not isinstance(symbols, list):
        return ["market_intake_universe_not_list"]
    if sorted(str(item) for item in symbols) != sorted(CONTROLLED_UNIVERSE):
        blockers.append("controlled_universe_mismatch")
    for symbol in symbols:
        upper = str(symbol).upper()
        if upper.endswith("-USD") or upper in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
            blockers.append(f"crypto_symbol_rejected:{symbol}")
    if intake.get("preset") != EXPECTED_PRESET:
        blockers.append("preset_drift")
    if intake.get("timeframe") != EXPECTED_TIMEFRAME:
        blockers.append("timeframe_drift")
    return blockers


def _build_cycle(
    *,
    controlled_packet: dict[str, Any],
    cycle_index: int,
    previous_seed: dict[str, Any] | None,
    build_request_pending: bool,
) -> dict[str, Any]:
    inner = _latest_inner_run(controlled_packet)
    run_group_id = str(controlled_packet.get("run_group_id") or "controlled-research")
    cycle_id = _cycle_id(run_group_id, cycle_index)
    market_intake = _market_intake(cycle_index, previous_seed)
    intake_blockers = _validate_market_intake(market_intake)

    metric_evidence = inner.get("metric_evidence") if isinstance(inner.get("metric_evidence"), dict) else {}
    analysis = inner.get("analysis") if isinstance(inner.get("analysis"), dict) else {}
    learning = inner.get("learning_feedback") if isinstance(inner.get("learning_feedback"), dict) else {}
    next_action_source = inner.get("next_hypothesis_or_action")
    if not isinstance(next_action_source, dict):
        next_action_source = {}
    next_action = str(
        next_action_source.get("recommended_action")
        or (controlled_packet.get("summary") or {}).get("final_recommendation")
        or "operator_review_required"
    )
    classification = action_classifier.classify_next_action(next_action)
    content_blockers = analysis.get("content_blockers")
    if not isinstance(content_blockers, list):
        content_blockers = []

    market_analysis = {
        "analysis_statement": (
            "Controlled market intake remains fixed; current blocker is interpreted "
            "as research infrastructure, not evidence to rotate the universe."
        ),
        "detected_constraints": [
            "exact_controlled_universe",
            "timeframe_1d",
            "preset_trend_continuation_daily_v1",
            "no_external_data_fetch",
        ],
        "detected_blockers": intake_blockers + [str(item) for item in content_blockers],
    }
    seed_id = f"{cycle_id}__next_market_intake_seed"
    next_seed = {
        "seed_id": seed_id,
        "source_cycle_id": cycle_id,
        "source_learning_feedback_id": learning.get("learning_feedback_id"),
        "statement": (
            "Keep the same market universe and preset. Feed back that the current "
            "blocker is infrastructure/metric evidence availability, not asset quality."
        ),
        "universe": list(CONTROLLED_UNIVERSE),
        "preset": EXPECTED_PRESET,
        "timeframe": EXPECTED_TIMEFRAME,
        "blocker_to_check": content_blockers[0] if content_blockers else None,
        "next_action": next_action,
    }
    waiting_for_build = classification.get("ade_build_allowed") is True and build_request_pending
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "cycle_id": cycle_id,
        "cycle_index": cycle_index,
        "created_at_utc": _utcnow(),
        "source_research_run_id": inner.get("run_id"),
        "source_research_run_group_id": run_group_id,
        "flow": [
            "market_intake",
            "market_analysis",
            "hypothesis_generation",
            "preset_selection",
            "controlled_campaign_intent",
            "metric_evidence",
            "result_analysis",
            "learning_feedback",
            "next_market_intake_seed",
            "next_action",
        ],
        "market_intake": market_intake,
        "market_analysis": market_analysis,
        "hypothesis_generation": inner.get("hypothesis") or {},
        "preset_selection": inner.get("preset_selection") or {},
        "controlled_campaign_intent": inner.get("controlled_campaign_intent") or {},
        "metric_evidence": metric_evidence,
        "result_analysis": {
            "analysis_id": analysis.get("analysis_id"),
            "analysis_statement": analysis.get("analysis_statement"),
            "metric_evidence_mode": analysis.get("metric_evidence_mode"),
            "true_metrics_available": analysis.get("true_metrics_available") is True,
            "content_blockers": content_blockers,
            "safety_blockers": analysis.get("safety_blockers") or [],
        },
        "learning_feedback": learning,
        "next_market_intake_seed": next_seed,
        "next_action": {
            "recommended_action": next_action,
            "classification": classification,
            "build_request_required": classification.get("ade_build_allowed") is True,
            "build_request_pending": waiting_for_build,
            "execution_allowed": False,
        },
        "safety": {
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "execution_allowed": False,
            "campaign_launcher_called": False,
            "run_research_called": False,
            "validation_executed": False,
            "protected_outputs_mutated": False,
            "build_executed_by_this_controller": False,
            "candidate_promotion_allowed": False,
            "strategy_registry_mutated": False,
            "preset_registry_mutated": False,
            "campaign_mutation_allowed": False,
            "external_data_or_network_fetch": False,
        },
    }


def build_autonomous_loop_packet(
    *,
    controlled_packet: dict[str, Any] | None = None,
    max_cycles: int = 3,
    until_build_request: bool = False,
    existing_build_request_pending: bool = False,
) -> dict[str, Any]:
    if max_cycles < 1 or max_cycles > 1000:
        raise AutonomousMarketResearchLoopError("--max-cycles must be between 1 and 1000")
    source_packet = controlled_packet or _load_or_build_controlled_packet()
    cycles: list[dict[str, Any]] = []
    previous_seed: dict[str, Any] | None = None
    build_request_needed = False
    for index in range(1, max_cycles + 1):
        cycle = _build_cycle(
            controlled_packet=source_packet,
            cycle_index=index,
            previous_seed=previous_seed,
            build_request_pending=existing_build_request_pending or build_request_needed,
        )
        cycles.append(cycle)
        previous_seed = cycle["next_market_intake_seed"]
        if cycle["next_action"]["build_request_required"]:
            build_request_needed = True
            if until_build_request:
                break

    action_classes = [
        str(cycle["next_action"]["classification"]["action_class"]) for cycle in cycles
    ]
    metric_modes = [str(cycle["metric_evidence"].get("metric_mode") or "") for cycle in cycles]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "created_at_utc": _utcnow(),
        "source_controlled_report_kind": source_packet.get("report_kind"),
        "source_controlled_run_group_id": source_packet.get("run_group_id"),
        "summary": {
            "autonomous_loop_ready": True,
            "cycle_count": len(cycles),
            "market_intake_cycle_count": len(cycles),
            "controlled_research_inner_loop_count": int(
                (source_packet.get("summary") or {}).get("loop_count") or 0
            )
            * len(cycles),
            "build_request_required_count": sum(
                1 for cycle in cycles if cycle["next_action"]["build_request_required"]
            ),
            "unsafe_actions_blocked": action_classes.count("blocked"),
            "unknown_actions": action_classes.count("unknown"),
            "latest_metric_mode": metric_modes[-1] if metric_modes else "",
            "latest_recommendation": cycles[-1]["next_action"]["recommended_action"],
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "execution_allowed": False,
            "campaign_launcher_called": False,
            "run_research_called": False,
            "validation_executed": False,
            "protected_outputs_mutated": False,
            "build_executed_by_this_controller": False,
            "auto_merge_allowed": False,
            "auto_trade_allowed": False,
        },
        "authority_boundaries": {
            "writes_only_qre_autonomous_market_research_loop_logs": True,
            "does_not_call_run_research": True,
            "does_not_call_campaign_launcher": True,
            "does_not_call_subprocess": True,
            "does_not_call_network": True,
            "does_not_execute_builds": True,
            "does_not_open_or_merge_prs": True,
            "does_not_activate_paper_shadow_live": True,
            "does_not_call_broker_or_risk": True,
            "does_not_mutate_protected_public_outputs": True,
        },
        "cycles": cycles,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    latest = packet["cycles"][-1]
    blockers = latest["result_analysis"].get("content_blockers") or []
    build_paths = packet.get("_build_request_paths") or {}
    lines = [
        "# QRE Autonomous Market-Research Loop",
        "",
        f"- Autonomous cycles: {summary['cycle_count']}.",
        f"- Market-intake cycles: {summary['market_intake_cycle_count']}.",
        f"- Controlled research inner loops: {summary['controlled_research_inner_loop_count']}.",
        "- Flow preserved: market_intake -> market_analysis -> hypothesis_generation -> preset_selection -> controlled_campaign_intent -> metric_evidence -> result_analysis -> learning_feedback -> next_market_intake_seed -> next_action.",
        f"- Latest universe: {', '.join(latest['market_intake']['universe'])}.",
        f"- Latest preset: {latest['preset_selection'].get('preset_id')}.",
        f"- Latest metric mode: {latest['metric_evidence'].get('metric_mode')}.",
        f"- Latest blocker: {blockers[0] if blockers else 'none'}.",
        f"- Latest recommendation: {summary['latest_recommendation']}.",
        f"- Build request: {build_paths.get('request_id', 'not_created')}.",
        "- No paper/shadow/live.",
        "- No broker/risk/execution authority.",
        "- No protected artifact mutation.",
        "- No Codex/ADE build execution by this controller.",
        "",
        "## Next System Action",
        "- If a build request exists, ADE/Codex may consume it in a later PR under normal review gates.",
        "- After merge/update, rerun `python -m research.qre_autonomous_market_research_loop --write --max-cycles 3`.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(packet: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    latest_path = output_dir / "latest.json"
    summary_path = output_dir / "operator_summary.md"
    ledger_path = output_dir / "ledger.jsonl"
    runs_dir = output_dir / "runs"
    for path in (latest_path, summary_path, ledger_path, runs_dir):
        _assert_inside(output_dir, path)
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    build_request_paths: dict[str, Any] = {}
    for cycle in packet["cycles"]:
        classification = cycle["next_action"]["classification"]
        if classification.get("ade_build_allowed") is True and not build_request_paths:
            build_packet = build_requests.build_request_packet(
                source_cycle=cycle,
                classification=classification,
            )
            build_request_paths = build_requests.write_build_request(
                build_packet,
                output_dir=output_dir,
                overwrite=False,
            )

    if build_request_paths:
        packet["_build_request_paths"] = build_request_paths
    latest_path.write_text(_json_dumps(packet), encoding="utf-8", newline="\n")
    summary_path.write_text(render_operator_summary(packet), encoding="utf-8", newline="\n")

    ledger_lines: list[str] = []
    for cycle in packet["cycles"]:
        run_path = runs_dir / f"{cycle['cycle_id']}.json"
        _assert_inside(output_dir, run_path)
        run_path.write_text(_json_dumps(cycle), encoding="utf-8", newline="\n")
        ledger_lines.append(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "report_kind": REPORT_KIND,
                    "cycle_id": cycle["cycle_id"],
                    "cycle_index": cycle["cycle_index"],
                    "metric_mode": cycle["metric_evidence"].get("metric_mode"),
                    "next_action": cycle["next_action"]["recommended_action"],
                    "action_class": cycle["next_action"]["classification"]["action_class"],
                },
                sort_keys=True,
            )
        )
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        for line in ledger_lines:
            handle.write(line + "\n")
    return {
        "latest": latest_path.as_posix(),
        "operator_summary": summary_path.as_posix(),
        "ledger": ledger_path.as_posix(),
        "runs_dir": runs_dir.as_posix(),
        "build_request": build_request_paths,
    }


def run_autonomous_loop(
    *,
    controlled_packet: dict[str, Any] | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_cycles: int = 3,
    until_build_request: bool = False,
    write: bool = False,
    report_only: bool = False,
) -> dict[str, Any]:
    before = _protected_fingerprints()
    if report_only:
        latest = output_dir / "latest.json"
        packet = _read_json(latest)
        if write:
            summary_path = output_dir / "operator_summary.md"
            _assert_inside(output_dir, summary_path)
            summary_path.write_text(render_operator_summary(packet), encoding="utf-8", newline="\n")
        _assert_protected_unchanged(before)
        return packet

    packet = build_autonomous_loop_packet(
        controlled_packet=controlled_packet,
        max_cycles=max_cycles,
        until_build_request=until_build_request,
        existing_build_request_pending=(output_dir / "latest_build_request.json").exists(),
    )
    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)
    _assert_protected_unchanged(before)
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded QRE autonomous market-research loop.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=3)
    parser.add_argument("--until-build-request", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    args = parser.parse_args(argv)
    packet = run_autonomous_loop(
        output_dir=Path(args.output_dir),
        max_cycles=args.max_cycles,
        until_build_request=args.until_build_request,
        write=args.write,
        report_only=args.report_only,
    )
    print(json.dumps(packet["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AutonomousMarketResearchLoopError",
    "CONTROLLED_UNIVERSE",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_autonomous_loop_packet",
    "render_operator_summary",
    "run_autonomous_loop",
    "write_outputs",
]
