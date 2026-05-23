"""Read-only reason-record evidence-density reporter.

ADE-QRE-014B sidecar. The module inspects existing reason/evidence
surfaces and reports whether operator-readable reason records carry
bounded evidence references. It never appends reason records, mutates
campaigns, enables synthesis, or touches frozen research outputs.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from reporting import failure_action_mapping_minimal as _fam
from reporting import intelligent_routing_minimal as _routing
from reporting import reason_records as _rr
from reporting import sampling_intelligence_minimal as _sampling

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-014b-2026-05-24"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "reason_record_evidence_density"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "reason_record_evidence_density"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/reason_record_evidence_density/"

SYNTHESIS_GATE_LATEST: Final[Path] = (
    REPO_ROOT / "research" / "synthesis_gate_latest.v1.json"
)
MAX_THIN_RECORDS: Final[int] = 16


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "reason_record_evidence_density: refusing write outside "
            f"allowlist: {path!r}"
        )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _bounded_refs(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        ref = item.strip()
        if ref and ref not in refs:
            refs.append(ref[:160])
    return refs[:16]


def _reason_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:300]


def _reason_codes(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    codes: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in codes:
            codes.append(item[:80])
    return codes[:16]


def _short_hash(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _normalised_record(
    *,
    source_id: str,
    record_family: str,
    record_id: str,
    subject_id: str,
    reason_codes: Sequence[str],
    reason_text: str,
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    refs = _bounded_refs(evidence_refs)
    text = _reason_text(reason_text)
    codes = _reason_codes(reason_codes)
    return {
        "source_id": source_id,
        "record_family": record_family,
        "record_id": record_id[:96],
        "subject_id": subject_id[:96],
        "reason_codes": codes,
        "reason_text": text,
        "evidence_refs": refs,
        "operator_summary": _operator_summary(
            record_family=record_family,
            subject_id=subject_id,
            reason_codes=codes,
            reason_text=text,
            evidence_refs=refs,
        ),
    }


def _operator_summary(
    *,
    record_family: str,
    subject_id: str,
    reason_codes: Sequence[str],
    reason_text: str,
    evidence_refs: Sequence[str],
) -> str:
    code_text = ", ".join(reason_codes) if reason_codes else "no reason codes"
    evidence_text = (
        f"{len(evidence_refs)} evidence refs"
        if evidence_refs
        else "missing evidence refs"
    )
    detail = reason_text or "no readable reason text"
    return f"{record_family}:{subject_id} -> {code_text}; {evidence_text}; {detail}"[:300]


def _records_from_reason_jsonls(
    *,
    artifact_dir: Path | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for kind in _rr.DECISION_KINDS:
        for record in _rr.read_kind(kind, artifact_dir=artifact_dir):
            records.append(
                _normalised_record(
                    source_id="reason_records_jsonl",
                    record_family=f"{kind}_reason_record",
                    record_id=str(record.get("record_id") or ""),
                    subject_id=str(record.get("subject_id") or ""),
                    reason_codes=_reason_codes(record.get("reason_codes")),
                    reason_text=_reason_text(record.get("reason_text")),
                    evidence_refs=_bounded_refs(record.get("evidence_refs")),
                )
            )
    return records


def _records_from_routing(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload is None:
        return []
    records: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        records.append(
            _normalised_record(
                source_id="intelligent_routing_minimal",
                record_family="routing_sidecar",
                record_id=str(item.get("record_id") or ""),
                subject_id=str(item.get("campaign_id") or ""),
                reason_codes=_reason_codes(item.get("reason_codes")),
                reason_text=_reason_text(item.get("reason_text")),
                evidence_refs=_bounded_refs(item.get("evidence_refs")),
            )
        )
    return records


def _records_from_sampling(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload is None:
        return []
    records: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        records.append(
            _normalised_record(
                source_id="sampling_intelligence_minimal",
                record_family="sampling_sidecar",
                record_id=str(item.get("record_id") or ""),
                subject_id=str(item.get("stratum_id") or ""),
                reason_codes=_reason_codes(item.get("reason_codes")),
                reason_text=_reason_text(item.get("reason_text")),
                evidence_refs=_bounded_refs(item.get("evidence_refs")),
            )
        )
    return records


def _records_from_failure_actions(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload is None:
        return []
    records: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        record = item.get("reason_record")
        if not isinstance(record, Mapping):
            continue
        records.append(
            _normalised_record(
                source_id="failure_action_mapping_minimal",
                record_family=str(record.get("record_kind") or "failure_action"),
                record_id=str(record.get("record_id") or ""),
                subject_id=str(record.get("subject_id") or item.get("subject_id") or ""),
                reason_codes=_reason_codes(record.get("reason_codes")),
                reason_text=_reason_text(record.get("reason_text")),
                evidence_refs=_bounded_refs(record.get("evidence_refs")),
            )
        )
    return records


def _records_from_synthesis_gate(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if payload is None:
        return []
    artifact_inputs = (
        payload.get("supporting_evidence", {}).get("artifact_inputs", {})
        if isinstance(payload.get("supporting_evidence"), Mapping)
        else {}
    )
    refs: list[str] = []
    if isinstance(artifact_inputs, Mapping):
        for name, status in sorted(artifact_inputs.items()):
            if isinstance(status, Mapping):
                refs.append(f"artifact_inputs.{name}:{status.get('path')}")
    for item in payload.get("required_missing_evidence") or []:
        refs.append(f"required_missing_evidence.{item}")
    record_id = "synth_" + _short_hash(
        {
            "state": payload.get("synthesis_gate_state"),
            "reason_codes": payload.get("reason_codes"),
            "missing": payload.get("required_missing_evidence"),
        }
    )
    return [
        _normalised_record(
            source_id="synthesis_gate",
            record_family="synthesis_gate_sidecar",
            record_id=record_id,
            subject_id=str(payload.get("synthesis_gate_state") or "unknown"),
            reason_codes=_reason_codes(payload.get("reason_codes")),
            reason_text=str(payload.get("synthesis_gate_state") or ""),
            evidence_refs=refs,
        )
    ]


def _density(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(records)
    with_codes = sum(1 for r in records if r.get("reason_codes"))
    with_text = sum(1 for r in records if r.get("reason_text"))
    with_refs = sum(1 for r in records if r.get("evidence_refs"))
    total_refs = sum(len(r.get("evidence_refs") or []) for r in records)
    by_family: dict[str, int] = {}
    thin: list[dict[str, Any]] = []
    for record in records:
        family = str(record.get("record_family") or "unknown")
        by_family[family] = by_family.get(family, 0) + 1
        missing = []
        if not record.get("reason_codes"):
            missing.append("reason_codes")
        if not record.get("reason_text"):
            missing.append("reason_text")
        if not record.get("evidence_refs"):
            missing.append("evidence_refs")
        if missing and len(thin) < MAX_THIN_RECORDS:
            thin.append(
                {
                    "record_id": record.get("record_id"),
                    "record_family": family,
                    "missing_fields": missing,
                }
            )
    return {
        "record_count": total,
        "records_with_reason_codes": with_codes,
        "records_with_reason_text": with_text,
        "records_with_evidence_refs": with_refs,
        "records_missing_evidence_refs": total - with_refs,
        "total_evidence_refs": total_refs,
        "evidence_ref_density": round(total_refs / total, 6) if total else None,
        "by_family": dict(sorted(by_family.items())),
        "thin_records_top": thin,
    }


def _merge_by_record_id(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("record_id") or f"anonymous_{len(merged)}")
        if record_id not in merged:
            merged[record_id] = dict(record)
            continue
        current = merged[record_id]
        current["source_id"] = "+".join(
            sorted({
                str(current.get("source_id") or ""),
                str(record.get("source_id") or ""),
            })
        ).strip("+")
        current["reason_codes"] = _reason_codes(
            list(current.get("reason_codes") or [])
            + list(record.get("reason_codes") or [])
        )
        if not current.get("reason_text") and record.get("reason_text"):
            current["reason_text"] = record.get("reason_text")
        current["evidence_refs"] = _bounded_refs(
            list(current.get("evidence_refs") or [])
            + list(record.get("evidence_refs") or [])
        )
        current["operator_summary"] = _operator_summary(
            record_family=str(current.get("record_family") or "unknown"),
            subject_id=str(current.get("subject_id") or ""),
            reason_codes=current.get("reason_codes") or [],
            reason_text=str(current.get("reason_text") or ""),
            evidence_refs=current.get("evidence_refs") or [],
        )
    return sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("record_family") or ""),
            str(row.get("record_id") or ""),
        ),
    )


def _final_recommendation(metrics: Mapping[str, Any]) -> str:
    total = int(metrics.get("record_count") or 0)
    missing_refs = int(metrics.get("records_missing_evidence_refs") or 0)
    if total == 0:
        return "not_ready_no_reason_records"
    if missing_refs:
        return "not_ready_missing_evidence_refs"
    return "evidence_density_ready"


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    reason_records_artifact_dir: Path | None = None,
    routing_minimal_path: Path | None = None,
    sampling_minimal_path: Path | None = None,
    failure_action_mapping_path: Path | None = None,
    synthesis_gate_path: Path | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    rr_records = _records_from_reason_jsonls(
        artifact_dir=reason_records_artifact_dir
    )
    sidecar_records: list[dict[str, Any]] = []
    sidecar_records.extend(
        _records_from_routing(routing_minimal_path or _routing.ARTIFACT_LATEST)
    )
    sidecar_records.extend(
        _records_from_sampling(sampling_minimal_path or _sampling.ARTIFACT_LATEST)
    )
    sidecar_records.extend(
        _records_from_failure_actions(
            failure_action_mapping_path or _fam.ARTIFACT_LATEST
        )
    )
    sidecar_records.extend(
        _records_from_synthesis_gate(synthesis_gate_path or SYNTHESIS_GATE_LATEST)
    )
    all_records = _merge_by_record_id(rr_records + sidecar_records)
    metrics = _density(all_records)
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "metrics": metrics,
        "baseline_without_sidecars": _density(rr_records),
        "after_with_sidecars": metrics,
        "records_top": all_records[:MAX_THIN_RECORDS],
        "final_recommendation": _final_recommendation(metrics),
        "safety_invariants": {
            "read_only": True,
            "emits_reason_records": False,
            "mutates_campaign_queue": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "strategy_synthesis_enabled": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    json_now = base / f"{ts}.json"
    json_latest = base / ARTIFACT_LATEST.name
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)
    _validate_write_target(json_now)
    _validate_write_target(json_latest)
    _validate_write_target(history)
    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)
    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)
    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")
    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot(
    *, artifact_dir: Path | None = None
) -> dict[str, Any] | None:
    base = artifact_dir or ARTIFACT_DIR
    return _read_json(base / ARTIFACT_LATEST.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.reason_record_evidence_density",
        description="Read-only reason-record evidence-density inspector.",
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        snapshot = read_latest_snapshot()
        if snapshot is None:
            snapshot = {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "report_kind": REPORT_KIND,
                "final_recommendation": "not_available",
            }
        print(json.dumps(snapshot, sort_keys=True, indent=2))
        return 0

    snapshot = collect_snapshot(frozen_utc=args.frozen_utc)
    if not args.no_write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
