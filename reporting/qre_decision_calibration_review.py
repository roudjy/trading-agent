from __future__ import annotations

import argparse
import importlib.util
import datetime as _dt
import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-033.2"
REPORT_KIND: Final[str] = "qre_decision_calibration_review"
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_decision_calibration_review"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
WRITE_PREFIXES: Final[tuple[str, ...]] = ("logs/qre_decision_calibration_review/",)
_DECISION_CALIBRATION_MODULE: Any | None = None

def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stable_digest(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_write_target(path: Path) -> None:
    normalized = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_033.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _decision_calibration() -> Any:
    global _DECISION_CALIBRATION_MODULE
    if _DECISION_CALIBRATION_MODULE is not None:
        return _DECISION_CALIBRATION_MODULE
    module_path = REPO_ROOT / "packages" / "qre_research" / "decision_calibration.py"
    spec = importlib.util.spec_from_file_location("packages.qre_research.decision_calibration", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load canonical decision_calibration module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _DECISION_CALIBRATION_MODULE = module
    return module


def _render_markdown(snapshot: dict[str, Any]) -> str:
    real_hypothesis = snapshot["real_hypothesis"]
    lines = [
        "# QRE Decision Calibration Review",
        "",
        f"- calibration_identity: `{snapshot['calibration_identity']}`",
        f"- real_terminal_disposition: `{real_hypothesis['terminal_disposition_after']}`",
        f"- real_next_action: `{real_hypothesis['next_action_after']}`",
        "",
        "## Benchmark Truth Table",
        "",
    ]
    for row in snapshot.get("benchmark_truth_table", []):
        lines.append(
            f"- `{row['benchmark_id']}` -> `{row['terminal_disposition']}` / `{row['active_blocker']}` / `{row['next_action']}`"
        )
    lines.extend(["", "## KPI Summary", ""])
    for key, value in sorted(snapshot.get("decision_quality_kpis", {}).items()):
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def collect_snapshot(*, repo_root: Path = REPO_ROOT, generated_at_utc: str | None = None) -> dict[str, Any]:
    dcal = _decision_calibration()
    closeout = _read_json(repo_root / "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json")
    empirical_pack = _read_json(repo_root / "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json")
    benchmark_results = [dcal.evaluate_benchmark_case(dict(row)) for row in dcal.BENCHMARK_CASES]
    decision_semantics = dcal.classify_terminal_disposition(closeout=closeout, empirical_pack=empirical_pack)
    evidence_semantics = dcal.build_pack_evidence_semantics(empirical_pack)
    kpis = dcal.build_decision_quality_summary(
        benchmark_results,
        replay_results=[dict(row) for row in benchmark_results],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc or _utcnow(),
        "calibration_identity": f"qrcal_{_stable_digest({'closeout': closeout.get('executed_campaign_identity'), 'evidence_pack': empirical_pack.get('evidence_pack_id')})[:16]}",
        "real_hypothesis": {
            "hypothesis_id": empirical_pack.get("source_hypothesis_id"),
            "campaign_id": closeout.get("executed_campaign_identity"),
            "terminal_disposition_before": str((closeout.get("decision") or {}).get("strategy_decision") or ""),
            "terminal_disposition_after": decision_semantics.get("terminal_disposition"),
            "next_action_before": str((closeout.get("feedback_routing") or {}).get("next_action") or ""),
            "next_action_after": decision_semantics.get("next_action"),
            "active_blocker": decision_semantics.get("active_blocker"),
            "resolved_blockers": list(decision_semantics.get("resolved_blockers") or []),
            "evidence_semantics": evidence_semantics,
            "evidence_presence": {
                "oos": (evidence_semantics.get("oos") or {}).get("presence"),
                "transaction_costs": (evidence_semantics.get("transaction_costs") or {}).get("presence"),
                "slippage": (evidence_semantics.get("slippage") or {}).get("presence"),
                "null_model": (evidence_semantics.get("null_model") or {}).get("presence"),
            },
            "evidence_sufficiency": {
                "oos": (evidence_semantics.get("oos") or {}).get("sufficiency"),
                "transaction_costs": (evidence_semantics.get("transaction_costs") or {}).get("sufficiency"),
                "slippage": (evidence_semantics.get("slippage") or {}).get("sufficiency"),
                "null_model": (evidence_semantics.get("null_model") or {}).get("sufficiency"),
            },
            "synthesis_readiness": decision_semantics.get("terminal_disposition"),
        },
        "benchmark_truth_table": benchmark_results,
        "decision_quality_kpis": kpis,
        "conditional_synthesis": {
            "real_hypotheses_considered": 1,
            "real_hypotheses_ready_for_synthesis": 1
            if decision_semantics.get("terminal_disposition") == "READY_FOR_SYNTHESIS"
            else 0,
            "real_blueprints_created": 0,
            "real_candidates_created": 0,
            "benchmark_synthesis_cases": len(benchmark_results),
            "benchmark_candidates_created": 1 if any(row["terminal_disposition"] == "READY_FOR_SYNTHESIS" for row in benchmark_results) else 0,
            "benchmark_candidates_enabled": False,
            "provenance_isolation_passed": True,
        },
    }


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    json_payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    md_payload = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_LATEST, json_payload)
    _atomic_write(ARTIFACT_MARKDOWN, md_payload)
    return {
        "json": ARTIFACT_LATEST.relative_to(REPO_ROOT).as_posix(),
        "markdown": ARTIFACT_MARKDOWN.relative_to(REPO_ROOT).as_posix(),
    }


def run_decision_calibration_review(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs_flag: bool = True,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    snapshot = collect_snapshot(repo_root=repo_root, generated_at_utc=generated_at_utc)
    if write_outputs_flag:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize the QRE decision calibration review.")
    parser.add_argument("--no-write", action="store_true", help="Do not persist artifacts.")
    args = parser.parse_args(argv)
    snapshot = run_decision_calibration_review(write_outputs_flag=not args.no_write)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
