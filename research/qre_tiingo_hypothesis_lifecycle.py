from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

REPORT_KIND: Final[str] = "qre_tiingo_hypothesis_lifecycle"
SCHEMA_VERSION: Final[int] = 1
SOURCE_REPORT_KIND: Final[str] = "qre_tiingo_hypothesis_generator_e2e"
DEFAULT_INPUT_PATH: Final[Path] = Path("logs/qre_tiingo_hypothesis_generator_e2e/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_tiingo_hypothesis_lifecycle")
LATEST_NAME: Final[str] = "latest.json"
EVENTS_NAME: Final[str] = "events.jsonl"
SUMMARY_NAME: Final[str] = "operator_summary.md"
PASS_VERDICT: Final[str] = "pass_data_driven_hypothesis_generation"

REQUIRED_CANDIDATE_SPEC_FIELDS: Final[tuple[str, ...]] = (
    "candidate_id",
    "parent_hypothesis_seed_id",
    "source_snapshot_id",
    "feature_family",
    "signal_definition",
    "selection_rule",
    "rebalance_rule",
    "holding_period",
    "benchmark",
    "null_control_requirement",
    "split_adjustment_requirement",
    "screening_only",
    "trading_authority",
)
FORBIDDEN_AUTHORITIES: Final[tuple[str, ...]] = (
    "candidate_promotion",
    "strategy_registration",
    "validation",
    "paper",
    "shadow",
    "live",
    "trading",
    "broker",
    "orders",
)
KNOWN_FAMILIES: Final[tuple[str, ...]] = (
    "cross_sectional_momentum",
    "risk_on_risk_off_regime",
    "defensive_rotation",
    "volatility_compression_breakout",
    "mean_reversion_after_extreme_dispersion",
)
SAFETY: Final[dict[str, bool]] = {
    "trading_authority": False,
    "creates_candidates": False,
    "runs_screening": False,
    "promotes_candidates": False,
    "registers_strategy": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}
ADMISSION_POLICY: Final[dict[str, Any]] = {
    "name": "tiingo_research_candidate_admission_v1",
    "authority": "research_only",
    "creates_candidates": False,
    "runs_screening": False,
    "allows_promotion": False,
    "allows_validation": False,
    "allows_strategy_registration": False,
    "allows_paper_shadow_live": False,
    "requires_trading_authority_false": True,
    "requires_final_verdict": PASS_VERDICT,
    "requires_data_dependency_proven": True,
    "requires_split_adjusted_profile_if_corporate_actions_present": True,
    "requires_real_and_shuffled_identity_difference": True,
    "requires_truncated_control_blocked": True,
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable_payload(item) for item in value]
    return value


def _digest(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(_stable_payload(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing_upstream_report"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None, "malformed_upstream_report"
    if not isinstance(payload, dict):
        return None, "malformed_upstream_report"
    return payload, None


def _source_report_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _source_report_kind(payload: dict[str, Any]) -> Any:
    return payload.get("report_kind") or payload.get("source_report_kind")


def _mode(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    modes = payload.get("modes")
    if not isinstance(modes, dict):
        return None
    value = modes.get(name)
    return value if isinstance(value, dict) else None


def _content_identities(mode: dict[str, Any]) -> list[str]:
    values = mode.get("content_identities")
    if isinstance(values, list):
        return [str(item) for item in values]
    hypotheses = mode.get("hypotheses")
    if isinstance(hypotheses, list):
        return [str(row.get("content_identity") or row.get("hypothesis_id") or "") for row in hypotheses if isinstance(row, dict)]
    return []


def _truncated_control_blocked(truncated: dict[str, Any]) -> bool:
    if int(truncated.get("hypotheses_count") or 0) != 0:
        return False
    blocked = {str(item) for item in truncated.get("blocked_reasons") or []}
    profile = truncated.get("data_profile") if isinstance(truncated.get("data_profile"), dict) else {}
    insufficient = bool(profile.get("insufficient_history")) or bool(profile.get("insufficient_cross_section"))
    return insufficient or bool(blocked & {"insufficient_history", "insufficient_cross_section"})


def _validate_upstream(payload: dict[str, Any] | None, *, load_error: str | None) -> list[str]:
    if load_error is not None:
        return [load_error]
    if payload is None:
        return ["missing_upstream_report"]
    reasons: list[str] = []
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    source_snapshot_id = payload.get("source_snapshot_id")

    if _source_report_kind(payload) != SOURCE_REPORT_KIND:
        reasons.append("unexpected_upstream_report_kind")
    if not source_snapshot_id:
        reasons.append("missing_source_snapshot_id")
    if summary.get("final_verdict") != PASS_VERDICT:
        reasons.append("upstream_final_verdict_not_pass")
    if summary.get("data_dependency_proven") is not True:
        reasons.append("data_dependency_not_proven")
    if safety.get("trading_authority") is not False:
        reasons.append("unsafe_trading_authority")

    real = _mode(payload, "real")
    shuffled = _mode(payload, "shuffled_returns")
    truncated = _mode(payload, "truncated")
    if real is None:
        reasons.append("missing_real_mode")
    if shuffled is None:
        reasons.append("missing_shuffled_mode")
    if truncated is None:
        reasons.append("missing_truncated_mode")

    if real is not None:
        profile = real.get("data_profile") if isinstance(real.get("data_profile"), dict) else {}
        if real.get("data_profile_valid") is not True or not profile:
            reasons.append("invalid_real_data_profile")
        if int(real.get("hypotheses_count") or 0) <= 0 or not real.get("hypotheses"):
            reasons.append("missing_real_hypotheses")
        events = profile.get("corporate_action_events")
        if events and profile.get("adjusted_price_continuity_applied") is not True:
            reasons.append("split_adjustment_required_but_missing")
    if shuffled is not None and (int(shuffled.get("hypotheses_count") or 0) <= 0 or not shuffled.get("hypotheses")):
        reasons.append("missing_shuffled_hypotheses")
    if real is not None and shuffled is not None and _content_identities(real) == _content_identities(shuffled):
        reasons.append("real_shuffled_identity_not_different")
    if truncated is not None and not _truncated_control_blocked(truncated):
        reasons.append("truncated_control_not_blocked")

    if real is not None and source_snapshot_id:
        for hypothesis in real.get("hypotheses") or []:
            if not _valid_hypothesis_shape(hypothesis, source_snapshot_id=str(source_snapshot_id)):
                reasons.append("malformed_upstream_hypothesis")
                break
    return sorted(dict.fromkeys(reasons))


def _valid_hypothesis_shape(hypothesis: Any, *, source_snapshot_id: str) -> bool:
    if not isinstance(hypothesis, dict):
        return False
    return (
        bool(hypothesis.get("hypothesis_id"))
        and bool(hypothesis.get("feature_family"))
        and bool(hypothesis.get("content_identity"))
        and hypothesis.get("source_snapshot_id") == source_snapshot_id
        and hypothesis.get("trading_authority") is False
        and hypothesis.get("not_trade_signal") is True
    )


def _seed_id(hypothesis: dict[str, Any], *, source_snapshot_id: str) -> str:
    return "seed_tiingo_" + _digest(
        {
            "source_hypothesis_id": hypothesis.get("hypothesis_id"),
            "source_snapshot_id": source_snapshot_id,
            "feature_family": hypothesis.get("feature_family"),
            "content_identity": hypothesis.get("content_identity"),
        }
    )


def _event_id(event_type: str, lifecycle: dict[str, Any]) -> str:
    return "evt_tiingo_" + _digest(
        {
            "event_type": event_type,
            "hypothesis_seed_id": lifecycle.get("hypothesis_seed_id"),
            "source_snapshot_id": lifecycle.get("source_snapshot_id"),
            "decision": lifecycle.get("decision"),
            "status": lifecycle.get("status"),
        }
    )


def _source_digest(hypothesis: dict[str, Any]) -> dict[str, Any]:
    return {
        "digest": "sha256:" + _digest(hypothesis, length=64),
        "keys": sorted(str(key) for key in hypothesis),
    }


def _lifecycle_record(hypothesis: dict[str, Any], *, source_snapshot_id: str, source_report_path: str) -> dict[str, Any]:
    family = str(hypothesis.get("feature_family") or "")
    seed_id = _seed_id(hypothesis, source_snapshot_id=source_snapshot_id)
    return {
        "hypothesis_seed_id": seed_id,
        "source_hypothesis_id": str(hypothesis.get("hypothesis_id")),
        "source_snapshot_id": source_snapshot_id,
        "source_report_path": source_report_path,
        "feature_family": family,
        "status": "admissible_for_research_candidate_formulation",
        "decision": "admitted",
        "decision_reasons": ["upstream_tiingo_evidence_passed_research_only_admission_policy"],
        "blocked_reasons": [],
        "required_candidate_spec_fields": list(REQUIRED_CANDIDATE_SPEC_FIELDS),
        "allowed_candidate_families": [family] if family in KNOWN_FAMILIES else [],
        "forbidden_authorities": list(FORBIDDEN_AUTHORITIES),
        "next_action": "materialize_research_candidate_later",
        "operator_update_required": True,
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
        "source_hypothesis_digest": _source_digest(hypothesis),
    }


def _blocked_event(*, reason: str, source_snapshot_id: str | None, source_report_path: str) -> dict[str, Any]:
    lifecycle = {
        "hypothesis_seed_id": "seed_tiingo_blocked_" + _digest(
            {"reason": reason, "source_snapshot_id": source_snapshot_id or "unknown", "source_report_path": source_report_path}
        ),
        "source_hypothesis_id": "upstream_report",
        "source_snapshot_id": source_snapshot_id or "unknown",
        "status": "blocked_missing_or_unsafe_input",
        "decision": "blocked",
    }
    return {
        "event_id": _event_id("hypothesis_blocked", lifecycle),
        "event_type": "hypothesis_blocked",
        "hypothesis_seed_id": lifecycle["hypothesis_seed_id"],
        "source_hypothesis_id": lifecycle["source_hypothesis_id"],
        "source_snapshot_id": lifecycle["source_snapshot_id"],
        "status": lifecycle["status"],
        "decision": lifecycle["decision"],
        "operator_update_required": True,
        "operator_message": f"Tiingo hypothesis lifecycle blocked before admission: {reason}. No candidate created and no screening run.",
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
    }


def _event(event_type: str, lifecycle: dict[str, Any]) -> dict[str, Any]:
    if event_type == "hypothesis_generated":
        message = "Tiingo hypothesis seed observed from upstream generator output. No candidate created and no trading authority granted."
    elif event_type == "hypothesis_admitted":
        message = "Tiingo hypothesis admitted for research-only candidate formulation later. No candidate created and no trading authority granted."
    else:
        message = "Tiingo hypothesis did not pass research-only admission. No candidate created and no screening run."
    return {
        "event_id": _event_id(event_type, lifecycle),
        "event_type": event_type,
        "hypothesis_seed_id": lifecycle["hypothesis_seed_id"],
        "source_hypothesis_id": lifecycle["source_hypothesis_id"],
        "source_snapshot_id": lifecycle["source_snapshot_id"],
        "status": lifecycle["status"],
        "decision": lifecycle["decision"],
        "operator_update_required": True,
        "operator_message": message,
        "trading_authority": False,
        "creates_candidates": False,
        "runs_screening": False,
    }


def _operator_update(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type"))
    severity = "info" if event_type in {"hypothesis_generated", "hypothesis_admitted"} else "blocked"
    next_action = "materialize_research_candidate_later" if event_type == "hypothesis_admitted" else "repair_upstream_evidence"
    if event_type == "hypothesis_generated":
        next_action = "materialize_research_candidate_later" if event.get("decision") == "admitted" else "repair_upstream_evidence"
    return {
        "update_type": event_type,
        "severity": severity,
        "hypothesis_seed_id": event.get("hypothesis_seed_id"),
        "message": event.get("operator_message"),
        "next_action": next_action,
    }


def _daily_digest_input(
    *,
    source_snapshot_id: str | None,
    generated: int,
    admitted: int,
    rejected: int,
    blocked: int,
    blocked_reasons: list[str],
    lifecycle: list[dict[str, Any]],
) -> dict[str, Any]:
    reason_counts = {reason: blocked_reasons.count(reason) for reason in sorted(set(blocked_reasons))}
    next_actions = sorted({str(row.get("next_action")) for row in lifecycle if row.get("next_action")})
    return {
        "digest_kind": "qre_hypothesis_lifecycle_daily_input",
        "source": REPORT_KIND,
        "source_snapshot_id": source_snapshot_id or "unknown",
        "counts": {
            "generated": generated,
            "admitted": admitted,
            "rejected": rejected,
            "blocked": blocked,
        },
        "highlights": [
            f"Tiingo lifecycle generated={generated} admitted={admitted} rejected={rejected} blocked={blocked}."
        ],
        "blocked_reasons": reason_counts,
        "next_actions": next_actions,
        "authority_summary": dict(SAFETY),
    }


def _is_digest_ready(digest: dict[str, Any], summary: dict[str, Any]) -> bool:
    counts = digest.get("counts") if isinstance(digest.get("counts"), dict) else {}
    authority = digest.get("authority_summary") if isinstance(digest.get("authority_summary"), dict) else {}
    return (
        digest.get("digest_kind") == "qre_hypothesis_lifecycle_daily_input"
        and counts.get("generated") == summary.get("hypotheses_generated_events")
        and counts.get("admitted") == summary.get("hypotheses_admitted")
        and counts.get("rejected") == summary.get("hypotheses_rejected")
        and counts.get("blocked") == summary.get("hypotheses_blocked")
        and all(authority.get(key) is False for key in SAFETY)
    )


def build_lifecycle_report(
    *,
    repo_root: Path = Path("."),
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    source_path = input_path if input_path.is_absolute() else repo_root / input_path
    source_report_path = _source_report_path(source_path, repo_root)
    upstream, load_error = _read_json(source_path)
    blocked_reasons = _validate_upstream(upstream, load_error=load_error)
    source_snapshot_id = str(upstream.get("source_snapshot_id")) if isinstance(upstream, dict) and upstream.get("source_snapshot_id") else None

    lifecycle: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    if blocked_reasons:
        events.append(
            _blocked_event(
                reason=blocked_reasons[0],
                source_snapshot_id=source_snapshot_id,
                source_report_path=source_report_path,
            )
        )
    else:
        real = _mode(upstream or {}, "real") or {}
        hypotheses = [dict(row) for row in real.get("hypotheses") or [] if isinstance(row, dict)]
        for hypothesis in hypotheses:
            record = _lifecycle_record(hypothesis, source_snapshot_id=source_snapshot_id or "unknown", source_report_path=source_report_path)
            lifecycle.append(record)
            events.append(_event("hypothesis_generated", record))
            events.append(_event("hypothesis_admitted", record))

    generated_count = sum(1 for event in events if event["event_type"] == "hypothesis_generated")
    admitted_count = sum(1 for row in lifecycle if row["decision"] == "admitted")
    rejected_count = sum(1 for row in lifecycle if row["decision"] == "rejected")
    blocked_count = sum(1 for event in events if event["event_type"] == "hypothesis_blocked")
    summary = {
        "input_verdict": ((upstream.get("summary") or {}).get("final_verdict") if isinstance(upstream, dict) else None) or "unavailable",
        "lifecycle_verdict": "blocked" if blocked_reasons else "pass_research_only_admission_boundary",
        "hypotheses_seen": len(lifecycle),
        "hypotheses_generated_events": generated_count,
        "hypotheses_admitted": admitted_count,
        "hypotheses_rejected": rejected_count,
        "hypotheses_blocked": blocked_count,
        "operator_updates_count": 0,
        "daily_digest_ready": False,
    }
    operator_updates = [_operator_update(event) for event in events if event.get("operator_update_required") is True]
    summary["operator_updates_count"] = len(operator_updates)
    digest = _daily_digest_input(
        source_snapshot_id=source_snapshot_id,
        generated=generated_count,
        admitted=admitted_count,
        rejected=rejected_count,
        blocked=blocked_count,
        blocked_reasons=blocked_reasons,
        lifecycle=lifecycle,
    )
    summary["daily_digest_ready"] = _is_digest_ready(digest, summary)
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "source_report_kind": SOURCE_REPORT_KIND,
        "source_report_path": source_report_path,
        "source_snapshot_id": source_snapshot_id or "unknown",
        "generated_at": _utcnow(),
        "trading_authority": False,
        "summary": summary,
        "admission_policy": dict(ADMISSION_POLICY),
        "hypothesis_lifecycle": lifecycle,
        "events": events,
        "operator_updates": operator_updates,
        "daily_digest_input": digest,
        "safety": dict(SAFETY),
        "blocked_reasons": blocked_reasons,
    }


def render_operator_summary(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}
    blocked = report.get("blocked_reasons") or []
    lines = [
        "# Tiingo Hypothesis Lifecycle",
        "",
        f"- Input verdict: {summary.get('input_verdict')}",
        f"- Lifecycle verdict: {summary.get('lifecycle_verdict')}",
        f"- Hypotheses seen: {summary.get('hypotheses_seen')}",
        f"- Generated events: {summary.get('hypotheses_generated_events')}",
        f"- Admitted: {summary.get('hypotheses_admitted')}",
        f"- Rejected: {summary.get('hypotheses_rejected')}",
        f"- Blocked: {summary.get('hypotheses_blocked')}",
        f"- Daily digest ready: {str(summary.get('daily_digest_ready')).lower()}",
        f"- Trading authority: {str(safety.get('trading_authority')).lower()}",
        f"- Candidate creation: {str(safety.get('creates_candidates')).lower()}",
        f"- Screening run: {str(safety.get('runs_screening')).lower()}",
        "- Next safe action: "
        + (
            "materialize research-only candidate specs in a later PR"
            if summary.get("hypotheses_admitted")
            else "repair upstream evidence"
        ),
        "",
        "hypothesis_seed_id | source_hypothesis_id | decision | status | next_action | reason",
        "---|---|---|---|---|---",
    ]
    lifecycle = report.get("hypothesis_lifecycle") if isinstance(report.get("hypothesis_lifecycle"), list) else []
    if lifecycle:
        for row in lifecycle:
            reasons = row.get("blocked_reasons") or row.get("decision_reasons") or []
            lines.append(
                " | ".join(
                    [
                        str(row.get("hypothesis_seed_id")),
                        str(row.get("source_hypothesis_id")),
                        str(row.get("decision")),
                        str(row.get("status")),
                        str(row.get("next_action")),
                        ", ".join(str(item) for item in reasons) if reasons else "none",
                    ]
                )
            )
    else:
        lines.append(
            "none | upstream_report | blocked | blocked_missing_or_unsafe_input | repair_upstream_evidence | "
            + (", ".join(str(item) for item in blocked) if blocked else "none")
        )
    lines.extend(
        [
            "",
            "No candidates were created. No screening was run. No trading, validation, promotion, strategy registration, paper, shadow, or live authority exists.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def write_outputs(
    report: dict[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    repo_root = repo_root.resolve()
    resolved = output_dir if output_dir.is_absolute() else repo_root / output_dir
    resolved = resolved.resolve()
    allowed = (repo_root / DEFAULT_OUTPUT_DIR).resolve()
    if resolved != allowed:
        raise ValueError("output_dir_must_be_logs_qre_tiingo_hypothesis_lifecycle")
    latest = resolved / LATEST_NAME
    events_path = resolved / EVENTS_NAME
    summary_path = resolved / SUMMARY_NAME
    latest_text = json.dumps(_stable_payload(report), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    events_text = "".join(json.dumps(_stable_payload(event), sort_keys=True, ensure_ascii=True) + "\n" for event in report.get("events", []))
    _atomic_write_text(latest, latest_text)
    _atomic_write_text(events_path, events_text)
    _atomic_write_text(summary_path, render_operator_summary(report))
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "events": events_path.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.qre_tiingo_hypothesis_lifecycle")
    parser.add_argument("--input", default=str(DEFAULT_INPUT_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    report = build_lifecycle_report(repo_root=repo_root, input_path=Path(args.input))
    if args.write:
        write_outputs(report, repo_root=repo_root, output_dir=Path(args.output_dir))
    print(json.dumps(_stable_payload(report), indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
