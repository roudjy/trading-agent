"""v3.15.5 outcome-emission invariant — precise static guard.

The precision rule (§correction-3 in the v3.15.5 brief): we test the
*launcher production-emission path*, NOT a broad string grep on
``worker_crashed``. The deprecated alias must remain in the
:class:`CampaignOutcome` ``Literal`` and the ``CAMPAIGN_OUTCOMES``
tuple for historical record reading. So we walk the AST instead and
check that no ``Assign`` / ``AnnAssign`` to a name called ``outcome``
inside ``research/campaign_launcher.py`` uses the literal
``"worker_crashed"``.

We also assert that the launcher imports ``LAUNCHER_EMITTABLE_OUTCOMES``
and uses it in an ``Assert`` statement — the runtime invariant.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

LAUNCHER_PATH = Path("research/campaign_launcher.py")


def _parse_module() -> ast.AST:
    return ast.parse(LAUNCHER_PATH.read_text(encoding="utf-8"))


def test_launcher_does_not_assign_outcome_worker_crashed():
    tree = _parse_module()
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Plain assignments: outcome = "..."
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "outcome":
                    if isinstance(node.value, ast.Constant) and \
                            node.value.value == "worker_crashed":
                        offenders.append((node.lineno, ast.unparse(node)))
        # Annotated assignments: outcome: str = "..."
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "outcome":
                if isinstance(node.value, ast.Constant) and \
                        node.value.value == "worker_crashed":
                    offenders.append((node.lineno, ast.unparse(node)))
    assert offenders == [], (
        "v3.15.5 launcher invariant violated — found `outcome = "
        "\"worker_crashed\"` assignment(s):\n" +
        "\n".join(f"  line {lno}: {src}" for lno, src in offenders)
    )


def test_launcher_imports_emittable_outcomes_set():
    tree = _parse_module()
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == \
                "research.campaign_registry":
            for alias in node.names:
                if alias.name == "LAUNCHER_EMITTABLE_OUTCOMES":
                    found = True
    assert found, (
        "campaign_launcher.py must import LAUNCHER_EMITTABLE_OUTCOMES "
        "from research.campaign_registry"
    )


def test_launcher_asserts_outcome_invariant():
    """Assert there is at least one `assert outcome in
    LAUNCHER_EMITTABLE_OUTCOMES` and one `assert outcome != "worker_crashed"`.
    """
    src = LAUNCHER_PATH.read_text(encoding="utf-8")
    assert "assert outcome in LAUNCHER_EMITTABLE_OUTCOMES" in src, (
        "campaign_launcher.py must assert outcome ∈ LAUNCHER_EMITTABLE_OUTCOMES "
        "before record_outcome()."
    )
    assert "assert outcome != \"worker_crashed\"" in src, (
        "campaign_launcher.py must assert outcome != 'worker_crashed' "
        "as a defensive backstop."
    )
