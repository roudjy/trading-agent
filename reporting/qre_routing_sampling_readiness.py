from __future__ import annotations

import argparse
import importlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_routing_sampling_readiness"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-017d-2026-06-25"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_routing_sampling_readiness")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_routing_sampling_readiness.md")
WRITE_PREFIX: Final[str] = "logs/qre_routing_sampling_readiness/"

_MAX_EXAMPLES: Final[int] = 16
_STATE_ORDER: Final[tuple[str, ...]] = ("ready", "blocked", "deferred", "fail_closed")


def _research_module(name: str) -> Any:
    return importlib.import_module(name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded_list(
    value: Any,
    *,
    limit: int = _MAX_EXAMPLES,
    width: int = 200,
) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item)
        if text and text not in out:
            out.append(text[:width])
    return out[:limit]


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if WRITE_PREFIX not in normalized:
        raise ValueError(
            "qre_routing_sampling_readiness: refusing write outside allowlist: "
            f"{path!r}"
        )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _reason_record_index(records: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        family = _text(row.get("record_family"))
        subject_id = _text(row.get("subject_id"))
        if family and subject_id:
            out[(family, subject_id)] = dict(row)
    return out


def _state_counts(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(_text(row.get(key)) or "unknown" for row in rows)
    ordered = {state: int(counts.get(state, 0)) for state in _STATE_ORDER}
    if counts.get("unknown"):
        ordered["unknown"] = int(counts["unknown"])
    return ordered


def _coverage_pct(total: int, present: int) -> float:
    if total <= 0:
        return 0.0
    return round((present / total) * 100.0, 2)


def _candidate_rows(
    *,
    routing_rows: Sequence[Mapping[str, Any]],
    sampling_rows: Sequence[Mapping[str, Any]],
    reason_record_index: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    sampling_by_id = {
        _text(row.get("candidate_id")): row
        for row in sampling_rows
        if _text(row.get("candidate_id"))
    }
    merged_rows: list[dict[str, Any]] = []
    for routing_row in routing_rows:
        candidate_id = _text(routing_row.get("candidate_id"))
        if not candidate_id:
            continue
        sampling_row = sampling_by_id.get(candidate_id, {})
        routing_reason = reason_record_index.get(("routing_readiness", candidate_id))
        sampling_reason = reason_record_index.get(("sampling_readiness", candidate_id))
        primary_reasons = [
            reason
            for reason in (
                _text(routing_row.get("primary_reason_code")),
                _text(sampling_row.get("primary_reason_code")),
            )
            if reason
        ]
        merged_rows.append(
            {
                "candidate_id": candidate_id,
                "symbol": _text(routing_row.get("symbol") or sampling_row.get("symbol")),
                "preset_id": _text(
                    routing_row.get("preset_id") or sampling_row.get("preset_id")
                ),
                "behavior_family": _text(
                    routing_row.get("behavior_family")
                    or sampling_row.get("behavior_family")
                ),
                "timeframes": _bounded_list(
                    routing_row.get("timeframes") or sampling_row.get("timeframes")
                ),
                "routing_state": _text(routing_row.get("routing_readiness_state")),
                "routing_score_pct": int(routing_row.get("routing_readiness_score_pct") or 0),
                "sampling_state": _text(sampling_row.get("sampling_readiness_state")),
                "sampling_score_pct": int(
                    sampling_row.get("sampling_readiness_score_pct") or 0
                ),
                "shared_ready": bool(routing_row.get("routing_ready"))
                and bool(sampling_row.get("sampling_ready")),
                "routing_reason_record_present": routing_reason is not None,
                "sampling_reason_record_present": sampling_reason is not None,
                "routing_reason_record_id": _text(
                    (routing_reason or {}).get("record_id")
                )[:64],
                "sampling_reason_record_id": _text(
                    (sampling_reason or {}).get("record_id")
                )[:64],
                "primary_reasons": primary_reasons[:4],
                "follow_up": _text(
                    sampling_row.get("follow_up") or routing_row.get("follow_up")
                ),
            }
        )
    merged_rows.sort(
        key=lambda row: (
            0 if row["shared_ready"] else 1,
            _STATE_ORDER.index(row["routing_state"])
            if row["routing_state"] in _STATE_ORDER
            else len(_STATE_ORDER),
            _STATE_ORDER.index(row["sampling_state"])
            if row["sampling_state"] in _STATE_ORDER
            else len(_STATE_ORDER),
            -int(row["routing_score_pct"]),
            -int(row["sampling_score_pct"]),
            row["symbol"],
            row["preset_id"],
        )
    )
    return merged_rows


def _final_recommendation(
    *,
    routing_total: int,
    sampling_total: int,
    routing_missing_reason_records: int,
    sampling_missing_reason_records: int,
    shared_ready_count: int,
) -> tuple[str, str]:
    if routing_total == 0 or sampling_total == 0:
        return (
            "readiness_population_missing_real_evidence",
            "materialize_real_basket_readiness_inputs",
        )
    if routing_missing_reason_records > 0 or sampling_missing_reason_records > 0:
        return (
            "readiness_population_reason_record_gap",
            "repair_reason_record_coverage_before_authority_upgrade",
        )
    if shared_ready_count == 0:
        return (
            "readiness_population_materialized_zero_shared_ready",
            "preserve_blockers_and_collect_more_real_evidence",
        )
    return (
        "readiness_population_materialized",
        "preserve_evidence_backed_ready_and_non_ready_states",
    )


def collect_snapshot(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
    materialize_supporting_outputs: bool = False,
) -> dict[str, Any]:
    routing = _research_module("research.qre_routing_readiness_from_basket")
    sampling = _research_module("research.qre_sampling_readiness_from_basket")
    reason_records = _research_module("research.qre_reason_records_v1")

    routing_snapshot = routing.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    sampling_snapshot = sampling.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    materialized_outputs: dict[str, str] = {}
    if materialize_supporting_outputs:
        for prefix, payload in (
            ("routing_", routing.write_outputs(routing_snapshot, repo_root=repo_root)),
            ("sampling_", sampling.write_outputs(sampling_snapshot, repo_root=repo_root)),
        ):
            for key, value in payload.items():
                materialized_outputs[prefix + key] = _text(value)

    routing_rows = [
        row for row in (routing_snapshot.get("rows") or []) if isinstance(row, Mapping)
    ]
    sampling_rows = [
        row for row in (sampling_snapshot.get("rows") or []) if isinstance(row, Mapping)
    ]
    reason_rows = [
        row for row in (reason_snapshot.get("records") or []) if isinstance(row, Mapping)
    ]
    reason_index = _reason_record_index(reason_rows)
    candidate_rows = _candidate_rows(
        routing_rows=routing_rows,
        sampling_rows=sampling_rows,
        reason_record_index=reason_index,
    )

    routing_reason_record_present = sum(
        1
        for row in candidate_rows
        if bool(row.get("routing_reason_record_present"))
    )
    sampling_reason_record_present = sum(
        1
        for row in candidate_rows
        if bool(row.get("sampling_reason_record_present"))
    )
    shared_ready_count = sum(1 for row in candidate_rows if bool(row.get("shared_ready")))
    ready_candidate_ids = [
        _text(row.get("candidate_id"))
        for row in candidate_rows
        if bool(row.get("shared_ready"))
    ][: _MAX_EXAMPLES]

    routing_reason_counter = Counter(
        _text(row.get("primary_reason_code"))
        for row in routing_rows
        if _text(row.get("primary_reason_code"))
    )
    sampling_reason_counter = Counter(
        _text(row.get("primary_reason_code"))
        for row in sampling_rows
        if _text(row.get("primary_reason_code"))
    )

    routing_total = len(routing_rows)
    sampling_total = len(sampling_rows)
    routing_missing_reason_records = routing_total - routing_reason_record_present
    sampling_missing_reason_records = sampling_total - sampling_reason_record_present
    final_recommendation, exact_next_action = _final_recommendation(
        routing_total=routing_total,
        sampling_total=sampling_total,
        routing_missing_reason_records=routing_missing_reason_records,
        sampling_missing_reason_records=sampling_missing_reason_records,
        shared_ready_count=shared_ready_count,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "routing_candidate_count": routing_total,
            "sampling_candidate_count": sampling_total,
            "routing_ready_count": int(
                ((_mapping := routing_snapshot.get("summary")) or {}).get("routing_ready_count")
                or 0
            ),
            "sampling_ready_count": int(
                ((_mapping := sampling_snapshot.get("summary")) or {}).get("sampling_ready_count")
                or 0
            ),
            "routing_state_counts": _state_counts(
                routing_rows,
                "routing_readiness_state",
            ),
            "sampling_state_counts": _state_counts(
                sampling_rows,
                "sampling_readiness_state",
            ),
            "shared_ready_count": shared_ready_count,
            "routing_reason_record_coverage_pct": _coverage_pct(
                routing_total,
                routing_reason_record_present,
            ),
            "sampling_reason_record_coverage_pct": _coverage_pct(
                sampling_total,
                sampling_reason_record_present,
            ),
            "routing_missing_reason_record_count": routing_missing_reason_records,
            "sampling_missing_reason_record_count": sampling_missing_reason_records,
            "final_recommendation": final_recommendation,
            "exact_next_action": exact_next_action,
        },
        "ready_candidate_ids_top": ready_candidate_ids,
        "routing_primary_reason_counts": dict(sorted(routing_reason_counter.items())),
        "sampling_primary_reason_counts": dict(sorted(sampling_reason_counter.items())),
        "candidate_examples_top": candidate_rows[:_MAX_EXAMPLES],
        "supporting_sources": {
            "routing_report_kind": _text(routing_snapshot.get("report_kind")),
            "sampling_report_kind": _text(sampling_snapshot.get("report_kind")),
            "reason_record_kind": _text(reason_snapshot.get("record_kind")),
            "routing_summary": dict(
                sorted(
                    (
                        (routing_snapshot.get("summary") or {})
                        if isinstance(routing_snapshot.get("summary"), Mapping)
                        else {}
                    ).items()
                )
            ),
            "sampling_summary": dict(
                sorted(
                    (
                        (sampling_snapshot.get("summary") or {})
                        if isinstance(sampling_snapshot.get("summary"), Mapping)
                        else {}
                    ).items()
                )
            ),
            "reason_record_meta": dict(
                sorted(
                    (
                        (reason_snapshot.get("meta") or {})
                        if isinstance(reason_snapshot.get("meta"), Mapping)
                        else {}
                    ).items()
                )
            ),
        },
        "materialized_supporting_outputs": materialized_outputs,
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "routing_runtime_activation": False,
            "sampling_runtime_activation": False,
        },
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    routing_counts = (
        summary.get("routing_state_counts")
        if isinstance(summary.get("routing_state_counts"), Mapping)
        else {}
    )
    sampling_counts = (
        summary.get("sampling_state_counts")
        if isinstance(summary.get("sampling_state_counts"), Mapping)
        else {}
    )
    rows = report.get("candidate_examples_top") if isinstance(report.get("candidate_examples_top"), list) else []
    summary_table = _table(
        ["Field", "Value"],
        [
            ["routing candidates", str(summary.get("routing_candidate_count") or 0)],
            ["sampling candidates", str(summary.get("sampling_candidate_count") or 0)],
            ["routing ready", str(summary.get("routing_ready_count") or 0)],
            ["sampling ready", str(summary.get("sampling_ready_count") or 0)],
            ["shared ready", str(summary.get("shared_ready_count") or 0)],
            [
                "routing reason-record coverage",
                f"{summary.get('routing_reason_record_coverage_pct') or 0.0}%",
            ],
            [
                "sampling reason-record coverage",
                f"{summary.get('sampling_reason_record_coverage_pct') or 0.0}%",
            ],
            ["final recommendation", _text(summary.get("final_recommendation"))],
            ["exact next action", _text(summary.get("exact_next_action"))],
        ],
    )
    state_table = _table(
        ["State", "Routing", "Sampling"],
        [
            [
                state,
                str(routing_counts.get(state) or 0),
                str(sampling_counts.get(state) or 0),
            ]
            for state in _STATE_ORDER
        ],
    )
    candidate_table = _table(
        [
            "Symbol",
            "Preset",
            "Routing",
            "Sampling",
            "Shared ready",
            "Reason records",
            "Primary reasons",
        ],
        [
            [
                _text(row.get("symbol")),
                _text(row.get("preset_id")),
                f"{_text(row.get('routing_state'))} ({row.get('routing_score_pct') or 0})",
                f"{_text(row.get('sampling_state'))} ({row.get('sampling_score_pct') or 0})",
                "yes" if bool(row.get("shared_ready")) else "no",
                (
                    "routing+sampling"
                    if bool(row.get("routing_reason_record_present"))
                    and bool(row.get("sampling_reason_record_present"))
                    else "routing-only"
                    if bool(row.get("routing_reason_record_present"))
                    else "sampling-only"
                    if bool(row.get("sampling_reason_record_present"))
                    else "missing"
                ),
                ", ".join(_bounded_list(row.get("primary_reasons"), limit=3)),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Routing and Sampling Readiness",
            "",
            "## 1. Summary",
            summary_table,
            "",
            "## 2. State counts",
            state_table,
            "",
            "## 3. Candidate examples",
            candidate_table,
            "",
            "## 4. Doctrine",
            "- Routing and sampling readiness are evidence-derived, read-only surfaces.",
            "- Missing reason-record support, missing basket evidence, or missing real readiness inputs fail closed.",
            "- This report does not activate routing, sampling, paper, shadow, live, broker, risk, or execution behavior.",
        ]
    )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    _validate_write_target(latest)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(payload, encoding="utf-8")
    os.replace(tmp_json, latest)

    doc_path = repo_root / DOC_PATH
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(render_markdown(report) + "\n", encoding="utf-8")
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "doc": DOC_PATH.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_routing_sampling_readiness",
        description=(
            "Materialize a read-only routing/sampling readiness summary from "
            "real basket evidence and reason-record coverage."
        ),
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = collect_snapshot(
        repo_root=Path("."),
        max_candidates=args.max_candidates,
        materialize_supporting_outputs=args.write,
    )
    if args.write:
        write_outputs(report, repo_root=Path("."))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
