"""v3.15.4 — paper_readiness sidecar carries the COL ownership stamp.

The launcher reads ``paper_readiness_latest.v1.json`` after the
``run_research`` subprocess exits to classify the campaign outcome.
Without an ownership stamp a previous campaign's verdict could be
mis-attributed to the current run if the subprocess crashed before
overwriting the sidecar. v3.15.4 adds a nullable ``col_campaign_id``
field; these tests pin its presence and shape on both the payload
builder and the façade writer.
"""

from __future__ import annotations

import json
from pathlib import Path

from research.paper_readiness import build_paper_readiness_payload
from research.paper_validation_sidecars import (
    PaperValidationBuildContext,
    build_and_write_paper_validation_sidecars,
)


def _payload(col_campaign_id: str | None) -> dict:
    return build_paper_readiness_payload(
        entries=[],
        generated_at_utc="2026-04-26T00:00:00+00:00",
        run_id="run-xyz",
        git_revision="deadbeef",
        col_campaign_id=col_campaign_id,
    )


def test_payload_carries_col_campaign_id_when_set() -> None:
    payload = _payload("col-2026-04-26-1200-abc")
    assert "col_campaign_id" in payload
    assert payload["col_campaign_id"] == "col-2026-04-26-1200-abc"


def test_payload_carries_null_col_campaign_id_when_absent() -> None:
    """Direct CLI invocations must keep the field present and null so
    legacy readers always see a stable schema."""
    payload = _payload(None)
    assert "col_campaign_id" in payload
    assert payload["col_campaign_id"] is None


def test_payload_field_order_is_stable_for_byte_reproducibility() -> None:
    """col_campaign_id sits next to run_id; stable ordering matters
    because every other v3.15 sidecar is byte-reproducible."""
    payload = _payload("cid")
    keys = list(payload.keys())
    assert keys.index("run_id") + 1 == keys.index("col_campaign_id")


def test_facade_writes_col_campaign_id_into_sidecar(tmp_path: Path) -> None:
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    ctx = PaperValidationBuildContext(
        run_id="run-1",
        generated_at_utc="2026-04-26T00:00:00+00:00",
        git_revision="abc",
        registry_v2={"entries": []},
        sleeve_registry=None,
        evaluations=[],
        col_campaign_id="col-test-1",
    )
    build_and_write_paper_validation_sidecars(
        ctx,
        timestamped_returns_path=tmp_path / "ts.json",
        paper_ledger_path=tmp_path / "ledger.json",
        paper_divergence_path=tmp_path / "div.json",
        paper_readiness_path=sidecar,
    )
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    assert raw["col_campaign_id"] == "col-test-1"


def test_facade_default_col_campaign_id_is_null(tmp_path: Path) -> None:
    """Direct (non-COL) callers omit the kwarg → field is null in the
    sidecar (preserves byte-identity guarantee for non-COL callers)."""
    sidecar = tmp_path / "paper_readiness_latest.v1.json"
    ctx = PaperValidationBuildContext(
        run_id="run-1",
        generated_at_utc="2026-04-26T00:00:00+00:00",
        git_revision="abc",
        registry_v2={"entries": []},
        sleeve_registry=None,
        evaluations=[],
    )
    build_and_write_paper_validation_sidecars(
        ctx,
        timestamped_returns_path=tmp_path / "ts.json",
        paper_ledger_path=tmp_path / "ledger.json",
        paper_divergence_path=tmp_path / "div.json",
        paper_readiness_path=sidecar,
    )
    raw = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "col_campaign_id" in raw
    assert raw["col_campaign_id"] is None
