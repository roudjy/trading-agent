from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import qre_controlled_validation_learning_proposal as learning

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_controlled_validation_research_action_queue_gate"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "qre_controlled_validation_research_action_queue_gate"
)
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_controlled_validation_research_action_queue_gate/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

REQUIRED_QUEUE_GO_PHRASE: Final[str] = (
    "I authorize QRE research action queue mutation"
)

QUEUE_BLOCKED_LEARNING_NOT_READY: Final[str] = "queue_blocked_learning_not_ready"
QUEUE_BLOCKED_WRITE_NOT_REQUESTED: Final[str] = "queue_blocked_write_not_requested"
QUEUE_BLOCKED_OPERATOR_GO_MISSING: Final[str] = "queue_blocked_operator_go_missing"
QUEUE_BLOCKED_OPERATOR_GO_MISMATCH: Final[str] = "queue_blocked_operator_go_mismatch"
QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED: Final[str] = "queue_authorized_writer_not_connected"

QUEUE_STATUSES: Final[tuple[str, ...]] = (
    QUEUE_BLOCKED_LEARNING_NOT_READY,
    QUEUE_BLOCKED_WRITE_NOT_REQUESTED,
    QUEUE_BLOCKED_OPERATOR_GO_MISSING,
    QUEUE_BLOCKED_OPERATOR_GO_MISMATCH,
    QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED,
)


def _utcnow() -> str:
    return (
        dt.datetime.now(dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _queue_status(
    *,
    learning_snapshot: dict[str, Any],
    write_research_action_queue: bool,
    operator_go: str | None,
) -> str:
    if learning_snapshot.get("learning_status") != "learning_ready_for_operator_review":
        return QUEUE_BLOCKED_LEARNING_NOT_READY
    if not write_research_action_queue:
        return QUEUE_BLOCKED_WRITE_NOT_REQUESTED
    if operator_go is None or operator_go.strip() == "":
        return QUEUE_BLOCKED_OPERATOR_GO_MISSING
    if operator_go.strip() != REQUIRED_QUEUE_GO_PHRASE:
        return QUEUE_BLOCKED_OPERATOR_GO_MISMATCH
    return QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED


def _counts(status: str) -> dict[str, Any]:
    return {
        "total": 1,
        "authorized": 1 if status == QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED else 0,
        "blocked": 0 if status == QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED else 1,
        "by_queue_status": {
            candidate: 1 if candidate == status else 0
            for candidate in QUEUE_STATUSES
        },
    }


def _final_recommendation(status: str) -> str:
    if status == QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED:
        return "research_action_queue_mutation_authorized_writer_not_connected"
    return "research_action_queue_mutation_blocked"


def _candidate_queue_item(learning_snapshot: dict[str, Any], status: str) -> dict[str, Any] | None:
    proposal = learning_snapshot.get("learning_proposal") or {}
    if status != QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED:
        return None
    return {
        "source": REPORT_KIND,
        "selection_profile_name": learning_snapshot.get("selection_profile_name"),
        "next_research_action": proposal.get("next_research_action"),
        "hypothesis_action": proposal.get("hypothesis_action"),
        "outcome": proposal.get("outcome"),
        "primary_failure_class": proposal.get("primary_failure_class"),
        "evidence_refs": list(proposal.get("evidence_refs") or []),
        "requires_operator_review": True,
    }


def collect_snapshot(
    *,
    profile_name: str | None = None,
    learning_snapshot: dict[str, Any] | None = None,
    write_research_action_queue: bool = False,
    operator_go: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_learning = learning_snapshot or learning.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )

    status = _queue_status(
        learning_snapshot=active_learning,
        write_research_action_queue=write_research_action_queue,
        operator_go=operator_go,
    )
    authorized = status == QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "selection_profile_name": (
            profile_name or active_learning.get("selection_profile_name")
        ),
        "safe_to_execute": False,
        "read_only": True,
        "eligible_for_direct_execution": False,
        "launches_subprocess": False,
        "launches_codex": False,
        "executed_anything": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "writes_research_action_queue": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "queue_mutation_authorized": authorized,
        "queue_writer_adapter_status": "not_connected",
        "queue_status": status,
        "final_recommendation": _final_recommendation(status),
        "counts": _counts(status),
        "operator_authorization": {
            "required": True,
            "provided": operator_go is not None and operator_go.strip() != "",
            "matched": operator_go is not None
            and operator_go.strip() == REQUIRED_QUEUE_GO_PHRASE,
            "required_phrase": REQUIRED_QUEUE_GO_PHRASE,
        },
        "learning_summary": {
            "report_kind": active_learning.get("report_kind"),
            "learning_status": active_learning.get("learning_status"),
            "final_recommendation": active_learning.get("final_recommendation"),
            "proposal_available": (
                (active_learning.get("learning_proposal") or {}).get("available")
                is True
            ),
        },
        "candidate_queue_item": _candidate_queue_item(active_learning, status),
        "next_required_step": (
            "complete learning proposal before queue mutation"
            if status == QUEUE_BLOCKED_LEARNING_NOT_READY
            else (
                "request queue mutation explicitly after learning proposal review"
                if status == QUEUE_BLOCKED_WRITE_NOT_REQUESTED
                else (
                    "provide exact operator-go phrase for queue mutation"
                    if status
                    in {
                        QUEUE_BLOCKED_OPERATOR_GO_MISSING,
                        QUEUE_BLOCKED_OPERATOR_GO_MISMATCH,
                    }
                    else "connect bounded queue writer adapter"
                )
            )
        ),
        "validation_warnings": [],
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(
            f"refusing write outside QRE research action queue gate dir: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_controlled_validation_research_action_queue_gate.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with open(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        Path(tmp_name).replace(path)
    finally:
        tmp_path = Path(tmp_name)
        if tmp_path.exists():
            tmp_path.unlink()


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_controlled_validation_research_action_queue_gate",
        description="Gate QRE research action queue mutation after learning proposal review.",
    )
    parser.add_argument("--profile", default=None)
    parser.add_argument("--write-research-action-queue", action="store_true")
    parser.add_argument("--operator-go", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        write_research_action_queue=bool(args.write_research_action_queue),
        operator_go=args.operator_go,
        generated_at_utc=args.frozen_utc,
    )
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    if not args.no_write:
        write_outputs(snapshot)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_LATEST",
    "QUEUE_AUTHORIZED_WRITER_NOT_CONNECTED",
    "QUEUE_BLOCKED_LEARNING_NOT_READY",
    "QUEUE_BLOCKED_OPERATOR_GO_MISMATCH",
    "QUEUE_BLOCKED_OPERATOR_GO_MISSING",
    "QUEUE_BLOCKED_WRITE_NOT_REQUESTED",
    "REPORT_KIND",
    "REQUIRED_QUEUE_GO_PHRASE",
    "collect_snapshot",
    "main",
    "write_outputs",
]
