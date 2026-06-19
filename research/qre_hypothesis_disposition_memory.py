from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_hypothesis_disposition_memory"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_hypothesis_disposition_memory")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_hypothesis_disposition_memory/"
DEFAULT_CAMPAIGN_REPORT: Final[Path] = Path("logs/qre_preregistered_multiwindow_evidence_run/latest.json")
DEFAULT_CLOSURE_REPORT: Final[Path] = Path("logs/qre_multiwindow_evidence_closure/latest.json")
DEFAULT_APPROVAL_REF: Final[str] = (
    "research/operator_approvals/qre_preregistered_multiwindow_validation_approval.v1.json"
    "#qre_preregistered_multiwindow_validation_001"
)
DEFAULT_TESTED_HYPOTHESIS: Final[str] = "trend_pullback_behavior_v1"
DEFAULT_TESTED_PRESET: Final[str] = "trend_pullback_continuation_daily_v1"
DEFAULT_TESTED_TIMEFRAME: Final[str] = "daily_v1"
DEFAULT_TESTED_SCOPE: Final[str] = "AAPL/NVDA preregistered multi-window local bounded basket"
MATERIAL_CHANGE_KEYS: Final[tuple[str, ...]] = (
    "hypothesis_rationale",
    "behavior_family",
    "behavior_id",
    "preset_family",
    "preset_id",
    "universe_or_basket_scope",
    "region",
    "timeframe",
    "regime_rationale",
    "data_period",
    "new_research_rationale",
    "operator_approved_new_research_rationale",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return out


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _window_refs(window_results: Sequence[Any], *, campaign_id: str) -> list[str]:
    refs: list[str] = []
    for index, window in enumerate(window_results):
        if not isinstance(window, Mapping):
            continue
        window_ref = f"logs/qre_preregistered_multiwindow_evidence_run/latest.json#window_results[{index}]"
        window_label = _text(window.get("regime_label")) or f"window_{index + 1:02d}"
        refs.append(f"{campaign_id}#{window_label}:{window_ref}")
    return refs


def _regime_refs(window_results: Sequence[Any]) -> list[str]:
    return _unique_in_order(
        _text(window.get("regime_label"))
        for window in window_results
        if isinstance(window, Mapping)
    )


def _accepted_lineage_refs(window_results: Sequence[Any]) -> list[str]:
    refs: list[str] = []
    for window_index, window in enumerate(window_results):
        if not isinstance(window, Mapping):
            continue
        symbol_results = window.get("symbol_results")
        if not isinstance(symbol_results, Sequence) or isinstance(symbol_results, (str, bytes)):
            continue
        for symbol_index, symbol_result in enumerate(symbol_results):
            if not isinstance(symbol_result, Mapping):
                continue
            lineage_records = symbol_result.get("lineage_records")
            if not isinstance(lineage_records, Sequence) or isinstance(lineage_records, (str, bytes)):
                continue
            for lineage_index, lineage_record in enumerate(lineage_records):
                if not isinstance(lineage_record, Mapping):
                    continue
                verifier_ref = _text(lineage_record.get("verifier_ref"))
                if verifier_ref:
                    refs.append(verifier_ref)
                else:
                    refs.append(
                        "logs/qre_preregistered_multiwindow_evidence_run/latest.json"
                        f"#window_results[{window_index}].symbol_results[{symbol_index}].lineage_records[{lineage_index}]"
                    )
    return _unique_in_order(refs)


def _accepted_oos_refs(window_results: Sequence[Any]) -> list[str]:
    refs: list[str] = []
    for window_index, window in enumerate(window_results):
        if not isinstance(window, Mapping):
            continue
        symbol_results = window.get("symbol_results")
        if not isinstance(symbol_results, Sequence) or isinstance(symbol_results, (str, bytes)):
            continue
        for symbol_index, symbol_result in enumerate(symbol_results):
            if not isinstance(symbol_result, Mapping):
                continue
            oos_records = symbol_result.get("oos_records")
            if not isinstance(oos_records, Sequence) or isinstance(oos_records, (str, bytes)):
                continue
            for oos_index, oos_record in enumerate(oos_records):
                if not isinstance(oos_record, Mapping):
                    continue
                verifier_ref = _text(oos_record.get("verifier_ref"))
                if verifier_ref:
                    refs.append(verifier_ref)
                else:
                    refs.append(
                        "logs/qre_preregistered_multiwindow_evidence_run/latest.json"
                        f"#window_results[{window_index}].symbol_results[{symbol_index}].oos_records[{oos_index}]"
                    )
    return _unique_in_order(refs)


def _failure_classes(
    campaign_report: Mapping[str, Any],
    closure_report: Mapping[str, Any],
) -> list[str]:
    classes: list[str] = []
    classes.extend(_unique_in_order(campaign_report.get("rejection_reasons") or []))
    classes.append(_text(campaign_report.get("campaign_outcome")))
    classes.extend(_unique_in_order(closure_report.get("blockers_remaining") or []))
    classes.append(_text(closure_report.get("closure_status")))
    classes.extend(
        _unique_in_order(
            reason_code
            for record in closure_report.get("reason_records") or []
            if isinstance(record, Mapping)
            for reason_code in record.get("reason_codes") or []
        )
    )
    return _unique_in_order(classes)


def _reason_record_refs(closure_report: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for index, record in enumerate(closure_report.get("reason_records") or []):
        if not isinstance(record, Mapping):
            continue
        record_id = _text(record.get("record_id"))
        if record_id:
            refs.append(
                f"logs/qre_multiwindow_evidence_closure/latest.json#reason_records[{index}]::{record_id}"
            )
        else:
            refs.append(f"logs/qre_multiwindow_evidence_closure/latest.json#reason_records[{index}]")
    return _unique_in_order(refs)


def _disposition_scope(
    *,
    hypothesis_id: str,
    behavior_id: str,
    preset_id: str,
    timeframe: str,
    universe_or_basket_scope: str,
    campaign_id: str,
    sampling_plan_id: str,
    window_refs: Sequence[str],
    regime_refs: Sequence[str],
) -> dict[str, Any]:
    return {
        "hypothesis_id": hypothesis_id,
        "behavior_id": behavior_id,
        "preset_id": preset_id,
        "timeframe": timeframe,
        "universe_or_basket_scope": universe_or_basket_scope,
        "campaign_id": campaign_id,
        "sampling_plan_id": sampling_plan_id,
        "window_count": len(list(window_refs)),
        "regime_labels": list(regime_refs),
    }


def _scope_signature(scope: Mapping[str, Any]) -> str:
    payload = {
        "hypothesis_id": _text(scope.get("hypothesis_id")),
        "behavior_id": _text(scope.get("behavior_id")),
        "preset_id": _text(scope.get("preset_id")),
        "timeframe": _text(scope.get("timeframe")),
        "universe_or_basket_scope": _text(scope.get("universe_or_basket_scope")),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _materially_new_scope(
    disposition_scope: Mapping[str, Any],
    proposed_scope: Mapping[str, Any],
) -> bool:
    if not proposed_scope:
        return False
    for key in MATERIAL_CHANGE_KEYS:
        left = _text(disposition_scope.get(key))
        right = _text(proposed_scope.get(key))
        if left and right and left != right:
            return True
        if not left and right:
            return True
    return False


def evaluate_revisit_eligibility(
    memory: Mapping[str, Any],
    *,
    proposed_scope: Mapping[str, Any],
) -> dict[str, Any]:
    record = memory.get("record") if isinstance(memory.get("record"), Mapping) else {}
    disposition_scope = (
        record.get("disposition_scope") if isinstance(record.get("disposition_scope"), Mapping) else {}
    )
    if not disposition_scope:
        return {
            "eligible": False,
            "reason": "missing_disposition_scope",
            "can_reuse_scope": False,
            "can_revisit": False,
        }
    if _scope_signature(disposition_scope) == _scope_signature(proposed_scope):
        return {
            "eligible": False,
            "reason": "same_failed_scope_suppressed",
            "can_reuse_scope": False,
            "can_revisit": False,
        }
    if _materially_new_scope(disposition_scope, proposed_scope):
        return {
            "eligible": True,
            "reason": "materially_new_research_scope",
            "can_reuse_scope": False,
            "can_revisit": True,
        }
    return {
        "eligible": False,
        "reason": "insufficient_scope_novelty",
        "can_reuse_scope": False,
        "can_revisit": False,
    }


def build_hypothesis_disposition_memory(
    *,
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    campaign_report_path: Path = DEFAULT_CAMPAIGN_REPORT,
    closure_report_path: Path = DEFAULT_CLOSURE_REPORT,
    approval_ref: str = DEFAULT_APPROVAL_REF,
) -> dict[str, Any]:
    campaign_report = _read_json(repo_root / campaign_report_path)
    closure_report = _read_json(repo_root / closure_report_path)
    if campaign_report is None or closure_report is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": generated_at_utc or "",
            "status": "blocked_missing_source_artifacts",
            "summary": {
                "hypothesis_disposition_memory_ready": False,
                "entry_count": 0,
                "final_recommendation": "hypothesis_disposition_memory_missing",
            },
            "safety_invariants": {
                "read_only": True,
                "uses_network": False,
                "uses_subprocess": False,
                "paper_shadow_live_forbidden": True,
                "broker_risk_execution_forbidden": True,
                "can_authorize_execution": False,
                "can_clear_evidence_blockers": False,
                "can_promote_candidate": False,
            },
        }

    window_results = list(campaign_report.get("window_results") or [])
    campaign_id = _text(campaign_report.get("campaign_id"))
    sampling_plan_ref = _text(campaign_report.get("sampling_plan_id"))
    accepted_lineage_refs = _accepted_lineage_refs(window_results)
    accepted_oos_refs = _accepted_oos_refs(window_results)
    regime_refs = _regime_refs(window_results)
    window_refs = _window_refs(window_results, campaign_id=campaign_id)
    failure_classes = _failure_classes(campaign_report, closure_report)
    reason_record_refs = _reason_record_refs(closure_report)
    disposition_timestamp = generated_at_utc or _text(closure_report.get("generated_at_utc")) or _text(
        campaign_report.get("generated_at_utc")
    )
    disposition_scope = _disposition_scope(
        hypothesis_id=DEFAULT_TESTED_HYPOTHESIS,
        behavior_id="pullback_continuation",
        preset_id=DEFAULT_TESTED_PRESET,
        timeframe=DEFAULT_TESTED_TIMEFRAME,
        universe_or_basket_scope=DEFAULT_TESTED_SCOPE,
        campaign_id=campaign_id,
        sampling_plan_id=sampling_plan_ref,
        window_refs=window_refs,
        regime_refs=regime_refs,
    )

    record = {
        "memory_record_id": "",
        "hypothesis_id": DEFAULT_TESTED_HYPOTHESIS,
        "behavior_id": "pullback_continuation",
        "preset_id": DEFAULT_TESTED_PRESET,
        "timeframe": DEFAULT_TESTED_TIMEFRAME,
        "universe_or_basket_scope": DEFAULT_TESTED_SCOPE,
        "sampling_plan_ref": sampling_plan_ref,
        "campaign_ref": campaign_id,
        "approval_ref": approval_ref,
        "window_refs": window_refs,
        "regime_refs": regime_refs,
        "accepted_lineage_refs": accepted_lineage_refs,
        "accepted_oos_refs": accepted_oos_refs,
        "failure_classes": failure_classes,
        "reason_record_refs": reason_record_refs,
        "closure_ref": str(closure_report_path).replace("\\", "/"),
        "hypothesis_disposition": "not_supported",
        "disposition_scope": disposition_scope,
        "disposition_timestamp": disposition_timestamp,
        "retry_policy": {
            "same_scope_suppressed": True,
            "same_scope_retry_allowed": False,
            "material_change_required": True,
            "material_change_keys": list(MATERIAL_CHANGE_KEYS),
        },
        "revisit_requirements": [
            "new hypothesis rationale",
            "materially different behavior mechanism",
            "materially different preset family",
            "materially different universe or basket scope",
            "new preregistered regime rationale",
            "new data period not selected because of observed result",
            "operator-approved research rationale",
        ],
        "authority": {
            "non_authoritative": True,
            "evidence_authority": "context_only",
            "can_authorize_execution": False,
            "can_clear_evidence_blockers": False,
            "can_promote_candidate": False,
        },
    }
    canonical = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "hypothesis_id": record["hypothesis_id"],
        "behavior_id": record["behavior_id"],
        "preset_id": record["preset_id"],
        "timeframe": record["timeframe"],
        "universe_or_basket_scope": record["universe_or_basket_scope"],
        "sampling_plan_ref": record["sampling_plan_ref"],
        "campaign_ref": record["campaign_ref"],
        "approval_ref": record["approval_ref"],
        "window_refs": list(record["window_refs"]),
        "regime_refs": list(record["regime_refs"]),
        "accepted_lineage_refs": list(record["accepted_lineage_refs"]),
        "accepted_oos_refs": list(record["accepted_oos_refs"]),
        "failure_classes": list(record["failure_classes"]),
        "reason_record_refs": list(record["reason_record_refs"]),
        "closure_ref": record["closure_ref"],
        "hypothesis_disposition": record["hypothesis_disposition"],
        "disposition_scope": dict(record["disposition_scope"]),
        "disposition_timestamp": record["disposition_timestamp"],
        "retry_policy": dict(record["retry_policy"]),
        "revisit_requirements": list(record["revisit_requirements"]),
        "authority": dict(record["authority"]),
    }
    record["hash"] = _digest(canonical)
    record["memory_record_id"] = "qhm_" + record["hash"].split(":", 1)[1][:16]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": disposition_timestamp,
        "status": "ready",
        "summary": {
            "hypothesis_disposition_memory_ready": True,
            "entry_count": 1,
            "accepted_lineage_ref_count": len(accepted_lineage_refs),
            "accepted_oos_ref_count": len(accepted_oos_refs),
            "failure_class_count": len(failure_classes),
            "hypothesis_disposition": record["hypothesis_disposition"],
            "final_recommendation": "hypothesis_disposition_memory_ready",
            "operator_summary": (
                "The rejected hypothesis disposition is captured as durable, local-only research memory "
                "with exact-scope suppression and explicit material-change requirements."
            ),
        },
        "record": record,
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "can_authorize_execution": False,
            "can_clear_evidence_blockers": False,
            "can_promote_candidate": False,
        },
    }


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    record = report.get("record") if isinstance(report.get("record"), Mapping) else {}
    tmp_md.write_text(
        "\n".join(
            [
                "# QRE Hypothesis Disposition Memory",
                "",
                f"- hypothesis_disposition: {report.get('summary', {}).get('hypothesis_disposition', '')}",
                f"- accepted_lineage_ref_count: {report.get('summary', {}).get('accepted_lineage_ref_count', 0)}",
                f"- accepted_oos_ref_count: {report.get('summary', {}).get('accepted_oos_ref_count', 0)}",
                f"- memory_record_id: {record.get('memory_record_id', '')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def read_hypothesis_disposition_memory_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_hypothesis_disposition_memory",
            "hypothesis_disposition_memory_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_hypothesis_disposition_memory",
            "hypothesis_disposition_memory_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    ready = bool(summary.get("hypothesis_disposition_memory_ready")) if isinstance(summary, Mapping) else False
    return {
        "status": "ready" if ready else "not_ready",
        "hypothesis_disposition_memory_ready": ready,
        "path": latest.relative_to(repo_root).as_posix(),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_hypothesis_disposition_memory",
        description="Persist a rejected hypothesis disposition as read-only research memory.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    parser.add_argument("--campaign-report", type=str, default=str(DEFAULT_CAMPAIGN_REPORT))
    parser.add_argument("--closure-report", type=str, default=str(DEFAULT_CLOSURE_REPORT))
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_hypothesis_disposition_memory_status(), indent=2, sort_keys=True))
        return 0

    report = build_hypothesis_disposition_memory(
        generated_at_utc=args.frozen_utc,
        campaign_report_path=Path(args.campaign_report),
        closure_report_path=Path(args.closure_report),
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
