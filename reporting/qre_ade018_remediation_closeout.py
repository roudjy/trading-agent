from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_ade018_common as common
from reporting import qre_campaign_portfolio_reconstruction as portfolio
from reporting import qre_evidence_reason_record_completion as completion
from reporting import qre_null_control_readiness as controls
from reporting import qre_rejected_thesis_replacement_plan as replacement
from reporting import qre_synthesis_readiness_review as readiness
from reporting import qre_validation_repro_operator_completion as validation

REPORT_KIND: Final[str] = "qre_ade018_remediation_closeout"
SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-018-closeout-2026-06-29"
ARTIFACT_DIR: Final[Path] = Path("logs/qre_ade018_remediation_closeout")
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_MARKDOWN: Final[Path] = ARTIFACT_DIR / "latest.md"
DOC_PATH: Final[Path] = Path("docs/governance/qre_ade018_remediation_closeout.md")
VALID_OUTCOMES: Final[tuple[str, ...]] = (
    "READY_FOR_SECOND_CAMPAIGN",
    "PARTIALLY_REMEDIATED",
    "CONTINUE_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
)
VALID_RECOMMENDATIONS: Final[tuple[str, ...]] = (
    "EXECUTE_SECOND_PREREGISTERED_CAMPAIGN",
    "COMPLETE_REMAINING_LINEAGE_AND_CONTROL_GAPS",
    "EXPAND_INDEPENDENT_OOS_CAPACITY",
    "RESOLVE_IDENTITY_AND_EVIDENCE_AUTHORITY",
    "STOP_FOR_OPERATOR_REVIEW",
)
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_ade018_remediation_closeout/",
    "docs/governance/qre_ade018_remediation_closeout.md",
)


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(normalized.startswith(prefix) for prefix in WRITE_PREFIXES):
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def collect_snapshot(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path.cwd()
    baseline = common.read_json(root / Path("logs/qre_synthesis_readiness_review/latest.json"))
    if baseline is None:
        baseline = readiness.collect_snapshot()
    completion_payload = completion.collect_snapshot(repo_root=root)
    validation_payload = validation.collect_snapshot(repo_root=root)
    controls_payload = controls.collect_snapshot(repo_root=root)
    replacement_payload = replacement.collect_snapshot(repo_root=root)
    portfolio_payload = portfolio.collect_snapshot(repo_root=root)

    failed_gates = common.normalize_list((baseline.get("summary") or {}).get("failed_mandatory_gates"))
    gate_rows: list[dict[str, Any]] = []
    for gate in failed_gates:
        if gate == "null_control_completeness":
            remediated = int((controls_payload.get("summary") or {}).get("complete_count") or 0) > 0
            partial = int((controls_payload.get("summary") or {}).get("specified_not_executed_count") or 0) > 0
        elif gate in {"validation_completeness", "reproducibility", "operator_decision_report_completeness", "evidence_freshness"}:
            remediated = False
            partial = int((validation_payload.get("summary") or {}).get("thesis_count") or 0) > 0
        elif gate in {"reason_record_completeness", "evidence_density_maturity", "evidence_authority_ambiguity_absent"}:
            remediated = False
            partial = int((completion_payload.get("summary") or {}).get("thesis_count") or 0) > 0
        else:
            remediated = False
            partial = gate in {
                "campaign_lineage_completeness",
                "hypothesis_lineage_completeness",
                "identity_readiness",
                "suppression_usefulness",
                "accepted_oos",
                "repeated_independent_oos",
            }
        gate_rows.append(
            {
                "criterion_id": gate,
                "remediation_state": "REMEDIATED" if remediated else "PARTIAL" if partial else "BLOCKED",
            }
        )

    ready_cells = int((portfolio_payload.get("summary") or {}).get("ready_cell_count") or 0)
    partial_count = sum(1 for row in gate_rows if row["remediation_state"] == "PARTIAL")
    remediated_count = sum(1 for row in gate_rows if row["remediation_state"] == "REMEDIATED")
    if ready_cells > 0:
        final_outcome = "READY_FOR_SECOND_CAMPAIGN"
        final_recommendation = "EXECUTE_SECOND_PREREGISTERED_CAMPAIGN"
    elif remediated_count > 0 or partial_count > 0:
        final_outcome = "PARTIALLY_REMEDIATED"
        final_recommendation = "COMPLETE_REMAINING_LINEAGE_AND_CONTROL_GAPS"
    else:
        final_outcome = "CONTINUE_BLOCKED"
        final_recommendation = "RESOLVE_IDENTITY_AND_EVIDENCE_AUTHORITY"
    if final_outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid final_outcome: {final_outcome}")
    if final_recommendation not in VALID_RECOMMENDATIONS:
        raise ValueError(f"invalid final_recommendation: {final_recommendation}")

    closeout_identity = f"qr18_{common.stable_digest({'gates': gate_rows, 'portfolio': portfolio_payload.get('portfolio_reconstruction_identity')})[:16]}"
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "remediation_closeout_identity": closeout_identity,
        "source_readiness_identity": common.text(baseline.get("synthesis_readiness_identity")),
        "failed_gate_remediation": gate_rows,
        "replacement_plan_identity": common.text(replacement_payload.get("replacement_plan_identity")),
        "portfolio_reconstruction_identity": common.text(portfolio_payload.get("portfolio_reconstruction_identity")),
        "summary": {
            "failed_gate_count": len(gate_rows),
            "remediated_gate_count": remediated_count,
            "partial_gate_count": partial_count,
            "blocked_gate_count": sum(1 for row in gate_rows if row["remediation_state"] == "BLOCKED"),
            "ready_cell_count": ready_cells,
            "replacement_proposal_state": common.text((replacement_payload.get("summary") or {}).get("proposal_state")),
            "final_outcome": final_outcome,
            "final_recommendation": final_recommendation,
            "exact_next_action": final_recommendation.lower(),
        },
        "provenance_refs": [
            common.rel(root / Path("logs/qre_synthesis_readiness_review/latest.json"), root),
            common.rel(root / Path("logs/qre_evidence_reason_record_completion/latest.json"), root),
            common.rel(root / Path("logs/qre_validation_repro_operator_completion/latest.json"), root),
            common.rel(root / Path("logs/qre_campaign_portfolio_reconstruction/latest.json"), root),
            common.rel(root / Path("logs/qre_rejected_thesis_replacement_plan/latest.json"), root),
        ],
    }


def _render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# QRE ADE-QRE-018 Remediation Closeout",
        "",
        f"- remediation_closeout_identity: `{common.text(snapshot.get('remediation_closeout_identity'))}`",
        f"- final_outcome: `{common.text((snapshot.get('summary') or {}).get('final_outcome'))}`",
        f"- final_recommendation: `{common.text((snapshot.get('summary') or {}).get('final_recommendation'))}`",
        "",
    ]
    for row in snapshot.get("failed_gate_remediation", []):
        if isinstance(row, dict):
            lines.append(f"- `{common.text(row.get('criterion_id'))}`: `{common.text(row.get('remediation_state'))}`")
    return "\n".join(lines) + "\n"


def _atomic_write(path: Path, payload: str) -> None:
    _validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_018z.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> None:
    _atomic_write(ARTIFACT_LATEST, json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    markdown = _render_markdown(snapshot)
    _atomic_write(ARTIFACT_MARKDOWN, markdown)
    _atomic_write(DOC_PATH, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m reporting.qre_ade018_remediation_closeout")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    snapshot = collect_snapshot()
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
