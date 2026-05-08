"""Determinism pin for Step 5.0 artefacts.

Per ``docs/governance/step5_design.md`` §10 (test matrix) and
§A14 of ``docs/roadmap/autonomous_development.txt``: the pure
Step 5.0 scorer must produce byte-identical output given the same
inputs and an injected ``generated_at_utc``. This regression test
locks that property so future changes to
``reporting.development_step5_loop`` cannot accidentally introduce
non-determinism (random ordering, time-of-day leak, hash randomisation).

Step 5 implementation remains BLOCKED. This pin only verifies the
output stability of the dry-run / planner-only Step 5.0 surface.
"""

from __future__ import annotations

import json
from pathlib import Path

from reporting import development_step5_loop as s5l


def test_step5_no_op_snapshot_is_byte_identical_under_same_timestamp(tmp_path: Path) -> None:
    """Pure-scorer determinism: same upstream paths + same injected
    ``generated_at_utc`` produce byte-identical sorted-key JSON."""
    kw = dict(
        delegation_path=tmp_path / "miss_d.json",
        bugfix_path=tmp_path / "miss_b.json",
        queue_path=tmp_path / "miss_q.json",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_a = s5l.collect_snapshot(**kw)
    snap_b = s5l.collect_snapshot(**kw)
    serialized_a = json.dumps(snap_a, indent=2, sort_keys=True)
    serialized_b = json.dumps(snap_b, indent=2, sort_keys=True)
    assert serialized_a == serialized_b


def test_step5_auto_allowed_snapshot_is_byte_identical_under_same_timestamp(tmp_path: Path) -> None:
    """AUTO_ALLOWED bugfix-path determinism."""
    bug_path = tmp_path / "logs" / "development_bugfix_loop" / "latest.json"
    bug_path.parent.mkdir(parents=True, exist_ok=True)
    bug_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "candidate_id": "syn_auto_allowed_001",
                        "execution_authority": "AUTO_ALLOWED",
                        "acceptance_criteria": ["criterion-1", "criterion-2"],
                        "target_paths": ["tests/unit/test_x.py", "tests/unit/test_y.py"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    kw = dict(
        delegation_path=tmp_path / "miss_d.json",
        bugfix_path=bug_path,
        queue_path=tmp_path / "miss_q.json",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_a = s5l.collect_snapshot(**kw)
    snap_b = s5l.collect_snapshot(**kw)
    a = json.dumps(snap_a, indent=2, sort_keys=True)
    b = json.dumps(snap_b, indent=2, sort_keys=True)
    assert a == b
    # Sanity: confirm the snapshot did pick up the synthetic AUTO_ALLOWED item.
    assert snap_a["plan"]["execution_authority_decision"] == "AUTO_ALLOWED"
    assert snap_a["plan"]["outcome"] == "plan_emitted"
    assert snap_a["plan"]["source_id"] == "syn_auto_allowed_001"


def test_step5_cycle_id_is_stable_across_runs() -> None:
    """The deterministic cycle_id derivation must not vary across
    Python process invocations or hash-randomisation seeds."""
    item = {"delegation_id": "ade_e2e_synthetic_001"}
    cid_first = s5l._cycle_id_from("delegation", item)
    cid_second = s5l._cycle_id_from("delegation", item)
    assert cid_first == cid_second
    assert (
        cid_first
        == "f4cdcd5e15b56af7c2eef6c6acf7e7e8e7c5b1a3a4e8b1a3a4e8b1a3a4e8b1a3"
        or len(cid_first) == 64
    )
    # The exact digest is implementation-derived; we only require that
    # it is the sha256 of the byte representation of "delegation|<id>".
    import hashlib  # local import keeps top-level import surface clean
    expected = hashlib.sha256(b"delegation|ade_e2e_synthetic_001").hexdigest()
    assert cid_first == expected


def test_step5_no_op_cycle_id_is_constant() -> None:
    """The "no eligible item" cycle_id is the sha256 of
    ``"no_eligible_item|"`` and must not drift."""
    plan = s5l._build_no_op_plan_payload(generated_at_utc="2026-05-08T00:00:00Z")
    import hashlib
    expected = hashlib.sha256(b"no_eligible_item|").hexdigest()
    assert plan["cycle_id"] == expected
