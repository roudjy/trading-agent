"""Minimal v3.16.x Adaptive Research Learning path.

This is the minimal ADR-021 reactivated learning surface. It turns
operator-provided campaign feedback records into deterministic,
read-only research context:

* campaign feedback metrics;
* evidence-backed strategy fitness scoring;
* read-only behavior-family grouping;
* read-only regime context;
* no strategy mutation, policy mutation, paper/shadow/live behavior,
  or execution authority.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.16.x-minimal-reactivated-2026-05-21"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "adaptive_research_learning_minimal_digest"


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


OUTCOMES: Final[tuple[str, ...]] = (
    "completed_with_candidates",
    "completed_no_survivor",
    "research_rejection",
    "degenerate_no_survivors",
    "technical_failure",
)

LEARNING_ACTIONS: Final[tuple[str, ...]] = (
    "prioritize_research_context",
    "maintain_watch",
    "suppress_redundant_exploration",
    "review_technical_quality",
)

INPUT_FEEDBACK_KEYS: Final[tuple[str, ...]] = (
    "campaign_id",
    "strategy_id",
    "behavior_family",
    "outcome",
    "near_pass",
    "regime_label",
    "robustness_pass",
    "evidence_count",
)

STRATEGY_METRIC_KEYS: Final[tuple[str, ...]] = (
    "strategy_id",
    "campaign_count",
    "survivor_count",
    "near_pass_count",
    "technical_failure_count",
    "robustness_pass_count",
    "evidence_count",
    "survivor_rate",
    "near_pass_rate",
    "technical_failure_rate",
    "robustness_pass_rate",
    "evidence_coverage",
    "fitness_score",
    "learning_action",
    "regime_context",
)

MAX_FEEDBACK_RECORDS: Final[int] = 512
MAX_ID_LEN: Final[int] = 64
MIN_EVIDENCE_PER_CAMPAIGN: Final[int] = 3


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------


ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "adaptive_research_learning_minimal"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/adaptive_research_learning_minimal/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "adaptive_research_learning_minimal: refusing write outside "
            f"allowlist: {path!r}"
        )


def _bounded_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value[:MAX_ID_LEN]


def _bounded_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _bounded_score(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 6)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_feedback(records: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(records, list | tuple):
        raise ValueError(
            "adaptive_research_learning_minimal: records must be a list/tuple"
        )
    if len(records) > MAX_FEEDBACK_RECORDS:
        raise ValueError(
            "adaptive_research_learning_minimal: too many records "
            f"({len(records)} > {MAX_FEEDBACK_RECORDS})"
        )
    seen_campaigns: set[str] = set()
    for i, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}] must be a mapping"
            )
        missing = set(INPUT_FEEDBACK_KEYS) - set(record.keys())
        if missing:
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}] missing fields: {sorted(missing)}"
            )
        campaign_id = record["campaign_id"]
        if not isinstance(campaign_id, str) or not campaign_id:
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}].campaign_id must be a non-empty str"
            )
        if campaign_id in seen_campaigns:
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"duplicate campaign_id {campaign_id!r}"
            )
        seen_campaigns.add(campaign_id)
        for field in ("strategy_id", "behavior_family", "regime_label"):
            if not isinstance(record[field], str) or not record[field]:
                raise ValueError(
                    "adaptive_research_learning_minimal: "
                    f"record[{i}].{field} must be a non-empty str"
                )
        if record["outcome"] not in OUTCOMES:
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}].outcome is not in the closed vocab"
            )
        if not isinstance(record["near_pass"], bool):
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}].near_pass must be bool"
            )
        if not isinstance(record["robustness_pass"], bool):
            raise ValueError(
                "adaptive_research_learning_minimal: "
                f"record[{i}].robustness_pass must be bool"
            )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _learning_action(
    *,
    fitness_score: float,
    technical_failure_rate: float,
    survivor_rate: float,
    near_pass_rate: float,
) -> str:
    if technical_failure_rate >= 0.5:
        return "review_technical_quality"
    if fitness_score >= 0.65 and survivor_rate > 0:
        return "prioritize_research_context"
    if fitness_score < 0.25 and near_pass_rate == 0:
        return "suppress_redundant_exploration"
    return "maintain_watch"


def _fitness_score(
    *,
    survivor_rate: float,
    near_pass_rate: float,
    robustness_pass_rate: float,
    evidence_coverage: float,
    technical_failure_rate: float,
) -> float:
    score = (
        0.45 * survivor_rate
        + 0.20 * near_pass_rate
        + 0.20 * robustness_pass_rate
        + 0.15 * evidence_coverage
        - 0.20 * technical_failure_rate
    )
    return _bounded_score(score)


def _strategy_metrics(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_strategy: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        strategy_id = _bounded_id(record["strategy_id"])
        by_strategy.setdefault(strategy_id, []).append(record)

    metrics: list[dict[str, Any]] = []
    for strategy_id, rows in by_strategy.items():
        campaign_count = len(rows)
        survivor_count = sum(
            1 for row in rows if row["outcome"] == "completed_with_candidates"
        )
        near_pass_count = sum(1 for row in rows if row["near_pass"])
        technical_failure_count = sum(
            1 for row in rows if row["outcome"] == "technical_failure"
        )
        robustness_pass_count = sum(
            1 for row in rows if row["robustness_pass"]
        )
        evidence_count = sum(_bounded_int(row["evidence_count"]) for row in rows)

        survivor_rate = _rate(survivor_count, campaign_count)
        near_pass_rate = _rate(near_pass_count, campaign_count)
        technical_failure_rate = _rate(
            technical_failure_count, campaign_count
        )
        robustness_pass_rate = _rate(robustness_pass_count, campaign_count)
        evidence_coverage = _bounded_score(
            evidence_count / max(1, campaign_count * MIN_EVIDENCE_PER_CAMPAIGN)
        )
        fitness_score = _fitness_score(
            survivor_rate=survivor_rate,
            near_pass_rate=near_pass_rate,
            robustness_pass_rate=robustness_pass_rate,
            evidence_coverage=evidence_coverage,
            technical_failure_rate=technical_failure_rate,
        )

        regime_counts: dict[str, int] = {}
        for row in rows:
            label = _bounded_id(row["regime_label"])
            regime_counts[label] = regime_counts.get(label, 0) + 1

        metrics.append(
            {
                "strategy_id": strategy_id,
                "campaign_count": campaign_count,
                "survivor_count": survivor_count,
                "near_pass_count": near_pass_count,
                "technical_failure_count": technical_failure_count,
                "robustness_pass_count": robustness_pass_count,
                "evidence_count": evidence_count,
                "survivor_rate": survivor_rate,
                "near_pass_rate": near_pass_rate,
                "technical_failure_rate": technical_failure_rate,
                "robustness_pass_rate": robustness_pass_rate,
                "evidence_coverage": evidence_coverage,
                "fitness_score": fitness_score,
                "learning_action": _learning_action(
                    fitness_score=fitness_score,
                    technical_failure_rate=technical_failure_rate,
                    survivor_rate=survivor_rate,
                    near_pass_rate=near_pass_rate,
                ),
                "regime_context": dict(sorted(regime_counts.items())),
            }
        )

    metrics.sort(key=lambda row: (-row["fitness_score"], row["strategy_id"]))
    return metrics


def _behavior_groups(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for record in records:
        family = _bounded_id(record["behavior_family"])
        strategy_id = _bounded_id(record["strategy_id"])
        group = groups.setdefault(
            family,
            {
                "campaign_count": 0,
                "strategy_ids": set(),
                "survivor_count": 0,
            },
        )
        group["campaign_count"] += 1
        group["strategy_ids"].add(strategy_id)
        if record["outcome"] == "completed_with_candidates":
            group["survivor_count"] += 1

    out: dict[str, dict[str, Any]] = {}
    for family, group in sorted(groups.items()):
        out[family] = {
            "campaign_count": group["campaign_count"],
            "strategy_ids": sorted(group["strategy_ids"]),
            "survivor_count": group["survivor_count"],
            "survivor_rate": _rate(
                group["survivor_count"], group["campaign_count"]
            ),
        }
    return out


def collect_snapshot(
    feedback: Sequence[Mapping[str, Any]] | None = None,
    *,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    records: Sequence[Mapping[str, Any]] = feedback or []
    validate_feedback(records)
    ts = frozen_utc or _utcnow()

    metrics = _strategy_metrics(records)
    action_counts = {action: 0 for action in LEARNING_ACTIONS}
    for row in metrics:
        action_counts[row["learning_action"]] += 1

    outcome_counts = {outcome: 0 for outcome in OUTCOMES}
    for record in records:
        outcome_counts[record["outcome"]] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "learning_effect": "advisory_read_only",
        "no_policy_mutation": True,
        "no_strategy_mutation": True,
        "no_execution_authority": True,
        "counts": {
            "campaign_feedback_records": len(records),
            "strategy_count": len(metrics),
            "by_outcome": outcome_counts,
            "by_learning_action": action_counts,
        },
        "strategy_metrics": metrics,
        "behavior_family_groups": _behavior_groups(records),
        "final_recommendation": (
            "learning_context_available" if records else "nothing_to_learn"
        ),
        "note": (
            "Minimal v3.16.x slice. Deterministic campaign feedback "
            "metrics and evidence-backed fitness scores only; regime "
            "and behavior-family data are read-only context. No Addendum "
            "activation, no paper/shadow/live behavior, and no execution "
            "authority."
        ),
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
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot(
    *, artifact_dir: Path | None = None
) -> dict[str, Any] | None:
    base = artifact_dir or ARTIFACT_DIR
    path = base / ARTIFACT_LATEST.name
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.adaptive_research_learning_minimal",
        description=(
            "Minimal v3.16.x Adaptive Research Learning. The CLI is "
            "dry-run/read-only unless writing the digest artifact."
        ),
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--mode", choices=("dry-run",), default="dry-run")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            snap = {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "final_recommendation": "not_available",
                "note": "no latest snapshot",
            }
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    snap = collect_snapshot([], frozen_utc=args.frozen_utc)
    if not args.no_write:
        snap["_artifact_paths"] = write_outputs(snap)
    print(json.dumps(snap, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
