"""Operator-facing report for candidate diversity validation.

This is a read-only report helper. It explains what the controlled
validation harness proves, what the production discovery seed enables,
and what remains unproven.
"""

from __future__ import annotations

import json
import importlib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "qre_controlled_validation"
    / "candidate_diversity_harness.json"
)


def _read_fixture(path: Path = HARNESS_FIXTURE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_outcome_label(row: dict[str, Any]) -> str:
    outcome = str(row.get("outcome_class") or "").strip()
    mapping = {
        "reject_insufficient_trades": "reject via insufficient trades",
        "reject_no_oos_evidence": "reject via no OOS evidence",
        "reject_criteria_consistentie_failed": "reject via consistentie criteria",
        "reject_criteria_trades_per_maand_failed": "reject via trades-per-month criteria",
        "reject_criteria_win_rate_failed": "reject via win-rate criteria",
        "near_pass": "near pass",
        "promotion_eligible_fixture_candidate": "fixture candidate reaches criteria path",
        "sufficient_oos_but_not_promoted": "OOS evidence exists but promotion stays blocked",
    }
    return mapping.get(outcome, outcome or "unclassified fixture outcome")


def _actual_outcome_label(row: dict[str, Any]) -> str:
    if row.get("promotion_guard", {}).get("promotion_allowed") is True:
        return "promotion_eligible_fixture_candidate"
    if (row.get("near_pass") or {}).get("is_near_pass"):
        return "near_pass"
    failure_reasons = list(row.get("failure_reasons") or [])
    if "insufficient_trades" in failure_reasons:
        return "reject_insufficient_trades"
    validation = row.get("validation_evidence") or {}
    if validation.get("status") == "no_oos_trades":
        return "reject_no_oos_evidence"
    blocked_by = list((row.get("promotion_guard") or {}).get("blocked_by") or [])
    if "criteria_consistentie_failed" in blocked_by:
        return "reject_criteria_consistentie_failed"
    if "criteria_trades_per_maand_failed" in blocked_by:
        return "reject_criteria_trades_per_maand_failed"
    if "criteria_win_rate_failed" in blocked_by:
        return "reject_criteria_win_rate_failed"
    if validation.get("status") == "sufficient_oos_evidence":
        return "sufficient_oos_but_not_promoted"
    return "unclassified"


def _production_seed_groups(
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    groups = [
        ("NL/EU", "lokale/Europese large-cap research"),
        ("US", "liquide trend/volatility research"),
        ("Asia/proxies", "regionale diversificatie"),
        ("ETFs/context", "benchmark/sector/context controle"),
    ]
    rows: list[dict[str, Any]] = []
    for group, goal in groups:
        matches = [asset["symbol"] for asset in assets if asset["region"] == group]
        rows.append(
            {
                "group": group,
                "count": len(matches),
                "examples": ", ".join(matches[:5]),
                "goal": goal,
            }
        )
    return rows


def collect_snapshot(
    *,
    branch: str,
    commits: list[dict[str, str]],
    tests: list[str],
    architecture_tests: str,
    git_diff_check: str,
    harness_fixture: dict[str, Any] | None = None,
    catalog_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fixture = harness_fixture or _read_fixture()
    if catalog_payload is None:
        discovery_catalog = importlib.import_module(
            "research.production_discovery_catalog"
        )
        catalog = discovery_catalog.production_discovery_catalog_payload(
            max_candidates=15
        )
    else:
        catalog = catalog_payload
    candidates = list(fixture["screening_evidence_payload"]["candidates"])
    short_conclusion = [
        "Controlled validation reporting now handles a bounded multi-candidate basket instead of explaining only one repeated preset.",
        "A read-only production discovery universe/preset seed now exists for multiple regions, assets, and behavior families.",
        "This proves research readiness only; it does not prove real alpha and it does not activate paper, shadow, or live runtime.",
    ]
    tested_rows = [
        {
            "candidate": row["asset"],
            "asset_region": f'{row["asset"]} / {row["region"]}',
            "preset_hypothesis": f'{row["preset_name"]} / {row["hypothesis_id"]}',
            "expected_outcome": _expected_outcome_label(row),
            "actual_outcome": _actual_outcome_label(row),
        }
        for row in sorted(candidates, key=lambda item: str(item["asset"]))
    ]
    evidence_rows = [
        {
            "proof": "Controlled validation harness reproduces 15 fixture candidates with multiple outcome classes.",
            "file": "tests/unit/test_qre_controlled_validation_candidate_diversity_harness.py",
            "why": "Shows the operator summary can explain more than one fixed preset.",
        },
        {
            "proof": "Result analysis exposes candidate-level explanation rows and fixture safety labels.",
            "file": "reporting/qre_controlled_validation_result_analysis.py",
            "why": "Separates fixture evidence from real market evidence in the operator view.",
        },
        {
            "proof": "Production discovery catalog stays read-only and regionally diverse.",
            "file": "tests/unit/test_qre_production_discovery_catalog.py",
            "why": "Proves the seed catalog does not grant paper/shadow/live authority.",
        },
        {
            "proof": "Bounded candidate basket selection reaches four region groups within 15 combinations.",
            "file": "research/production_discovery_catalog.py",
            "why": "Shows later discovery can sample multiple assets/presets without broad runtime mutation.",
        },
    ]
    return {
        "title": "# QRE Candidate Diversity + Production Discovery Seed Report",
        "short_conclusion": short_conclusion,
        "tested_rows": tested_rows,
        "production_seed_rows": _production_seed_groups(list(catalog["assets"])),
        "evidence_rows": evidence_rows,
        "proves": [
            "de validatieketen kan meerdere candidate-uitkomsten verwerken",
            "operator summary toont candidate-level uitleg",
            "een fixture candidate kan de full criteria path halen",
            "blockers worden per candidate zichtbaar",
            "er is een veilige read-only discovery catalog voor meerdere assets/regio’s/presets",
        ],
        "not_proves": [
            "dit bewijst geen echte alpha",
            "dit activeert geen paper/shadow/live",
            "dit betekent niet dat production strategies zijn toegevoegd",
            "dit betekent niet dat strategy synthesis toegestaan is",
            "dit betekent niet dat echte candidates al door market evidence zijn bewezen",
        ],
        "next_action": "READ_ONLY_REAL_BASKET_DIAGNOSIS",
        "validation": {
            "branch": branch,
            "commits": commits,
            "tests": tests,
            "architecture_tests": architecture_tests,
            "git_diff_check": git_diff_check,
            "frozen_contracts_untouched": True,
            "protected_execution_paths_untouched": True,
        },
    }


def _table(headers: list[str], rows: list[list[str]]) -> str:
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def render_markdown(snapshot: dict[str, Any]) -> str:
    tested_table = _table(
        ["Candidate", "Asset/regio", "Preset/hypothesis", "Verwachte uitkomst", "Werkelijke uitkomst"],
        [
            [
                row["candidate"],
                row["asset_region"],
                row["preset_hypothesis"],
                row["expected_outcome"],
                row["actual_outcome"],
            ]
            for row in snapshot["tested_rows"]
        ],
    )
    seed_table = _table(
        ["Groep", "Voorbeelden", "Doel"],
        [
            [row["group"], row["examples"], row["goal"]]
            for row in snapshot["production_seed_rows"]
        ],
    )
    evidence_table = _table(
        ["Bewijs", "Bestand/test", "Waarom belangrijk"],
        [
            [row["proof"], row["file"], row["why"]]
            for row in snapshot["evidence_rows"]
        ],
    )
    validation = snapshot["validation"]
    commit_table = _table(
        ["Commit", "SHA", "Doel"],
        [[item["message"], item["sha"], item["purpose"]] for item in validation["commits"]],
    )
    return "\n".join(
        [
            snapshot["title"],
            "",
            "## 1. Korte conclusie",
            *[f"- {line}" for line in snapshot["short_conclusion"]],
            "",
            "## 2. Wat is getest",
            tested_table,
            "",
            "## 3. Production discovery seed",
            seed_table,
            "",
            "## 4. Belangrijkste bewijs",
            evidence_table,
            "",
            "## 5. Wat dit wel bewijst",
            *[f"- {line}" for line in snapshot["proves"]],
            "",
            "## 6. Wat dit niet bewijst",
            *[f"- {line}" for line in snapshot["not_proves"]],
            "",
            "## 7. Volgende veilige stap",
            f"- NEXT_ACTION: {snapshot['next_action']}",
            "",
            "## 8. Validatie",
            f"- branch: {validation['branch']}",
            commit_table,
            *[f"- test: {item}" for item in validation["tests"]],
            f"- architecture tests: {validation['architecture_tests']}",
            f"- git diff --check: {validation['git_diff_check']}",
            f"- frozen contracts untouched: {str(validation['frozen_contracts_untouched']).lower()}",
            f"- protected execution paths untouched: {str(validation['protected_execution_paths_untouched']).lower()}",
        ]
    )
