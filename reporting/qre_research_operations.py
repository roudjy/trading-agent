from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _ao() -> Any:
    return importlib.import_module("packages.qre_research.autonomous_orchestration")


def _print_json(payload: dict[str, Any], *, indent: int) -> None:
    json.dump(payload, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")


def _status_payload(repo_root: Path) -> dict[str, Any]:
    ao = _ao()
    status = ao._read_json(repo_root / ao.STATUS_PATH)
    if status is not None:
        return status
    config = ao.load_or_create_operations_config(repo_root=repo_root, write_outputs=False)
    portfolio = ao.build_unified_portfolio(repo_root=repo_root)
    work_items = ao.admit_work_items(
        actions=ao.build_typed_next_actions(portfolio=portfolio, config=config),
        config=config,
    )
    oos_budget = ao.build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)
    daily_report = ao.generate_daily_report(
        repo_root=repo_root,
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        cycle_ledger=[],
        oos_budget=oos_budget,
        write_outputs=False,
    )
    alerts = ao._alerts(
        portfolio=portfolio,
        oos_budget=oos_budget,
        config=config,
        cycle_ledger=[],
        daily_report_identity=str(daily_report.get("daily_report_identity") or ""),
    )
    return ao.build_status_artifact(
        config=config,
        portfolio=portfolio,
        work_items=work_items,
        throughput_schedule={"groups": []},
        oos_budget=oos_budget,
        alerts_payload=alerts,
        latest_daily_report=daily_report,
        cycle_ledger=[],
    )


def _portfolio_payload(repo_root: Path) -> dict[str, Any]:
    ao = _ao()
    return ao.build_unified_portfolio(repo_root=repo_root)


def _queue_payload(repo_root: Path) -> dict[str, Any]:
    ao = _ao()
    config = ao.load_or_create_operations_config(repo_root=repo_root, write_outputs=False)
    portfolio = ao.build_unified_portfolio(repo_root=repo_root)
    actions = ao.build_typed_next_actions(portfolio=portfolio, config=config)
    work_items = ao.admit_work_items(actions=actions, config=config)
    return {
        "schema_version": ao.SCHEMA_VERSION,
        "report_kind": "qre_research_operations_queue",
        "actions": actions,
        "work_items": work_items,
    }


def _budget_payload(repo_root: Path) -> dict[str, Any]:
    ao = _ao()
    config = ao.load_or_create_operations_config(repo_root=repo_root, write_outputs=False)
    portfolio = ao.build_unified_portfolio(repo_root=repo_root)
    return ao.build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)


def _build_parser() -> argparse.ArgumentParser:
    ao = _ao()
    parser = argparse.ArgumentParser(description="QRE research operations control surface")
    parser.add_argument("--repo-root", type=Path, default=ao.REPO_ROOT)
    parser.add_argument("--indent", type=int, default=2)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate-config")
    sub.add_parser("status")
    sub.add_parser("portfolio")
    sub.add_parser("queue")
    sub.add_parser("budgets")
    sub.add_parser("plan")

    run_once = sub.add_parser("run-once")
    run_once.add_argument("--mode", choices=ao.OPERATING_MODES)

    run_bounded = sub.add_parser("run-bounded")
    run_bounded.add_argument("--mode", choices=ao.OPERATING_MODES)
    run_bounded.add_argument("--max-cycles", type=int, default=None)

    sub.add_parser("pause")
    sub.add_parser("resume")
    sub.add_parser("daily-report")
    sub.add_parser("latest-report")
    sub.add_parser("alerts")

    explain = sub.add_parser("explain")
    explain.add_argument("work_item_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    ao = _ao()
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root
    indent = max(int(args.indent or 2), 0)

    if args.command == "validate-config":
        payload = ao.validate_operations_config(
            ao.load_or_create_operations_config(repo_root=repo_root, write_outputs=False)
        )
        _print_json(payload, indent=indent)
        return 0 if payload["valid"] else 2

    if args.command == "status":
        _print_json(_status_payload(repo_root), indent=indent)
        return 0

    if args.command == "portfolio":
        _print_json(_portfolio_payload(repo_root), indent=indent)
        return 0

    if args.command == "queue":
        _print_json(_queue_payload(repo_root), indent=indent)
        return 0

    if args.command == "budgets":
        _print_json(_budget_payload(repo_root), indent=indent)
        return 0

    if args.command == "plan":
        payload = ao.run_orchestration(
            repo_root=repo_root,
            mode="PLAN_ONLY",
            max_cycles=1,
            write_outputs=False,
        )
        _print_json(payload, indent=indent)
        return 0

    if args.command == "run-once":
        payload = ao.run_orchestration(
            repo_root=repo_root,
            mode=args.mode or "LOCAL_AUTONOMOUS",
            max_cycles=1,
            write_outputs=True,
        )
        _print_json(payload, indent=indent)
        return 0

    if args.command == "run-bounded":
        payload = ao.run_orchestration(
            repo_root=repo_root,
            mode=args.mode or "GOVERNED_CONTINUOUS_LOOP",
            max_cycles=args.max_cycles,
            write_outputs=True,
        )
        _print_json(payload, indent=indent)
        return 0

    if args.command == "pause":
        _print_json(ao.set_pause_state(repo_root=repo_root, paused=True), indent=indent)
        return 0

    if args.command == "resume":
        _print_json(ao.set_pause_state(repo_root=repo_root, paused=False), indent=indent)
        return 0

    if args.command == "daily-report":
        config = ao.load_or_create_operations_config(repo_root=repo_root, write_outputs=True)
        portfolio = ao.build_unified_portfolio(repo_root=repo_root)
        actions = ao.build_typed_next_actions(portfolio=portfolio, config=config)
        work_items = ao.admit_work_items(actions=actions, config=config)
        oos_budget = ao.build_oos_budget(repo_root=repo_root, portfolio=portfolio, config=config)
        cycle_ledger = (ao._read_json(repo_root / ao.CYCLE_LEDGER_PATH) or {}).get("rows") or []
        payload = ao.generate_daily_report(
            repo_root=repo_root,
            config=config,
            portfolio=portfolio,
            work_items=work_items,
            cycle_ledger=list(cycle_ledger),
            oos_budget=oos_budget,
            write_outputs=True,
        )
        _print_json(payload, indent=indent)
        return 0

    if args.command == "latest-report":
        payload = ao._read_json(repo_root / ao.LATEST_DAILY_JSON_PATH) or {}
        _print_json(payload, indent=indent)
        return 0

    if args.command == "alerts":
        payload = ao._read_json(repo_root / ao.ALERTS_PATH)
        if payload is None:
            payload = {"schema_version": ao.SCHEMA_VERSION, "report_kind": "qre_orchestration_alerts", "rows": []}
        _print_json(payload, indent=indent)
        return 0

    if args.command == "explain":
        queue = _queue_payload(repo_root)
        payload = ao.explain_selection(
            work_items=queue["work_items"],
            selected_work_item_id=args.work_item_id,
        )
        _print_json(payload, indent=indent)
        return 0 if payload.get("status") == "present" else 3

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
