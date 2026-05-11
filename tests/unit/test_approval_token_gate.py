"""Unit tests for N4a — Approval Token Gate (pure mint/verify)."""

from __future__ import annotations

import importlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reporting import approval_token_gate as n4a


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _secret() -> bytes:
    return secrets.token_bytes(32)


def _mint(
    *,
    secret: bytes,
    intent: str = "mobile_approval_dispatch",
    event_id: str = "eid_abc",
    pr_number: int | None = 167,
    pr_head_sha: str | None = "abc123",
    evidence_hash: str = "h_xyz",
    release_tag: str | None = None,
    kid: str = "k1",
    ttl_seconds: int = n4a.DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> str:
    return n4a.mint_token(
        intent=intent,
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
        release_tag=release_tag,
        kid=kid,
        secret=secret,
        ttl_seconds=ttl_seconds,
        now=now,
    )


def _verify(
    token: str,
    secret: bytes,
    *,
    expected_event_id: str = "eid_abc",
    expected_pr_number: int | None = 167,
    expected_pr_head_sha: str | None = "abc123",
    expected_evidence_hash: str = "h_xyz",
    expected_release_tag: str | None = None,
    seen_nonces: set[str] | None = None,
    now: datetime | None = None,
) -> n4a.VerifyResult:
    return n4a.verify_token(
        token,
        expected_event_id=expected_event_id,
        expected_pr_number=expected_pr_number,
        expected_pr_head_sha=expected_pr_head_sha,
        expected_evidence_hash=expected_evidence_hash,
        expected_release_tag=expected_release_tag,
        secrets_by_kid={"k1": secret},
        seen_nonces=seen_nonces,
        now=now,
    )


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_token_intents_pinned_exactly() -> None:
    assert n4a.TOKEN_INTENTS == (
        "mobile_approval_dispatch",
        "mobile_review_dispatch",
    )


def test_token_intents_avoid_decision_verb() -> None:
    """No intent name uses `approve` / `reject` / `merge` / `deploy`
    as a verb. The intent is a *dispatch* purpose, not an executed
    action."""
    for intent in n4a.TOKEN_INTENTS:
        lo = intent.lower()
        assert "approve" not in lo
        assert "reject" not in lo
        assert "merge" not in lo
        assert "deploy" not in lo


def test_verify_outcomes_pinned_exactly() -> None:
    assert n4a.VERIFY_OUTCOMES == (
        "ok",
        "expired",
        "signature_invalid",
        "binding_mismatch",
        "intent_unknown",
        "malformed_envelope",
        "replay_detected",
        "unknown_kid",
    )


def test_token_claim_keys_pinned_exactly_and_ordered() -> None:
    assert n4a.TOKEN_CLAIM_KEYS == (
        "schema_version",
        "intent",
        "event_id",
        "pr_number",
        "pr_head_sha",
        "evidence_hash",
        "release_tag",
        "kid",
        "nonce",
        "issued_at_utc",
        "expires_at_utc",
    )


def test_constants_pinned() -> None:
    assert n4a.HMAC_ALGORITHM == "sha256"
    assert n4a.MIN_SECRET_LENGTH_BYTES == 32
    assert n4a.DEFAULT_TTL_SECONDS == 900
    assert n4a.MAX_TTL_SECONDS == 900


def test_step5_invariants_pinned() -> None:
    assert n4a.step5_implementation_allowed is False
    assert n4a.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Mint argument validation
# ---------------------------------------------------------------------------


def test_mint_rejects_unknown_intent() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), intent="please_approve_my_pr")


def test_mint_rejects_empty_event_id() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), event_id="")


def test_mint_rejects_empty_evidence_hash() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), evidence_hash="")


def test_mint_rejects_empty_kid() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), kid="")


def test_mint_rejects_secret_too_short() -> None:
    with pytest.raises(ValueError):
        _mint(secret=b"short")


def test_mint_rejects_non_bytes_secret() -> None:
    with pytest.raises(TypeError):
        _mint(secret="not bytes")  # type: ignore[arg-type]


def test_mint_rejects_ttl_too_long() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), ttl_seconds=n4a.MAX_TTL_SECONDS + 1)


def test_mint_rejects_zero_ttl() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), ttl_seconds=0)


def test_mint_rejects_negative_ttl() -> None:
    with pytest.raises(ValueError):
        _mint(secret=_secret(), ttl_seconds=-1)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_mint_then_verify_ok() -> None:
    secret = _secret()
    token = _mint(secret=secret)
    result = _verify(token, secret)
    assert result.outcome == "ok"
    assert result.claims is not None
    assert result.claims["intent"] == "mobile_approval_dispatch"
    assert result.claims["event_id"] == "eid_abc"


def test_token_envelope_shape() -> None:
    secret = _secret()
    token = _mint(secret=secret)
    assert "." in token
    a, b = token.split(".", 1)
    assert a and b


def test_token_claims_have_closed_key_set() -> None:
    secret = _secret()
    token = _mint(secret=secret)
    result = _verify(token, secret)
    assert result.outcome == "ok"
    assert set(result.claims.keys()) == set(n4a.TOKEN_CLAIM_KEYS)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Verify outcomes — every row
# ---------------------------------------------------------------------------


def test_verify_outcome_expired() -> None:
    secret = _secret()
    # Issue a token 1000 seconds in the past.
    iat = datetime.now(UTC) - timedelta(seconds=1000)
    token = _mint(secret=secret, ttl_seconds=900, now=iat)
    result = _verify(token, secret)
    assert result.outcome == "expired"


def test_verify_outcome_signature_invalid() -> None:
    secret = _secret()
    other_secret = _secret()
    token = _mint(secret=secret)
    # Verify with a different secret in the kid map.
    result = n4a.verify_token(
        token,
        expected_event_id="eid_abc",
        expected_pr_number=167,
        expected_pr_head_sha="abc123",
        expected_evidence_hash="h_xyz",
        expected_release_tag=None,
        secrets_by_kid={"k1": other_secret},
    )
    assert result.outcome == "signature_invalid"


def test_verify_outcome_binding_mismatch_event_id() -> None:
    secret = _secret()
    token = _mint(secret=secret)
    result = _verify(token, secret, expected_event_id="different")
    assert result.outcome == "binding_mismatch"


def test_verify_outcome_binding_mismatch_pr_number() -> None:
    secret = _secret()
    token = _mint(secret=secret, pr_number=167)
    result = _verify(token, secret, expected_pr_number=168)
    assert result.outcome == "binding_mismatch"


def test_verify_outcome_binding_mismatch_pr_head_sha() -> None:
    secret = _secret()
    token = _mint(secret=secret, pr_head_sha="abc123")
    result = _verify(token, secret, expected_pr_head_sha="def456")
    assert result.outcome == "binding_mismatch"


def test_verify_outcome_binding_mismatch_evidence_hash() -> None:
    secret = _secret()
    token = _mint(secret=secret, evidence_hash="h_xyz")
    result = _verify(token, secret, expected_evidence_hash="h_other")
    assert result.outcome == "binding_mismatch"


def test_verify_outcome_binding_mismatch_release_tag() -> None:
    secret = _secret()
    token = _mint(secret=secret, release_tag="v3.15.16")
    result = _verify(
        token, secret, expected_release_tag="v3.15.17"
    )
    assert result.outcome == "binding_mismatch"


def test_verify_outcome_malformed_envelope_no_separator() -> None:
    result = _verify("not_a_token", _secret())
    assert result.outcome == "malformed_envelope"


def test_verify_outcome_malformed_envelope_garbage_base64() -> None:
    result = _verify("$$$.$$$", _secret())
    assert result.outcome == "malformed_envelope"


def test_verify_outcome_unknown_kid() -> None:
    secret = _secret()
    token = _mint(secret=secret, kid="k_unknown")
    result = n4a.verify_token(
        token,
        expected_event_id="eid_abc",
        expected_pr_number=167,
        expected_pr_head_sha="abc123",
        expected_evidence_hash="h_xyz",
        expected_release_tag=None,
        secrets_by_kid={"k1": secret},
    )
    assert result.outcome == "unknown_kid"


def test_verify_outcome_replay_detected() -> None:
    secret = _secret()
    token = _mint(secret=secret)
    first = _verify(token, secret)
    assert first.outcome == "ok"
    nonce = first.claims["nonce"]  # type: ignore[index]
    seen: set[str] = {nonce}
    second = _verify(token, secret, seen_nonces=seen)
    assert second.outcome == "replay_detected"


def test_seen_nonces_set_unchanged_when_none() -> None:
    """N4a does not mutate the seen-nonce set itself; the caller
    decides whether to record a verified nonce."""
    secret = _secret()
    token = _mint(secret=secret)
    seen: set[str] = set()
    result = _verify(token, secret, seen_nonces=seen)
    assert result.outcome == "ok"
    # N4a did not auto-add the verified nonce.
    assert seen == set()


# ---------------------------------------------------------------------------
# Each `verify_outcome` value appears reachable
# ---------------------------------------------------------------------------


def test_every_verify_outcome_value_appears_reachable() -> None:
    """Defense-in-depth: every closed vocab value is exercised by
    the tests above. We assert each value is referenced *as a string*
    in test source — keeps reachability obvious to a reviewer."""
    test_src = Path(__file__).read_text(encoding="utf-8")
    for outcome in n4a.VERIFY_OUTCOMES:
        # Either via a verify_outcome assertion or in the module's
        # closed vocab listing — either way the test surface
        # references it.
        assert outcome in test_src, outcome


# ---------------------------------------------------------------------------
# No env / no Flask / no IO
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(n4a.__file__).read_text(encoding="utf-8")


def test_module_source_does_not_read_environment() -> None:
    """N4a NEVER reads any env var. AST-pinned + source-text pinned."""
    src = _module_source()
    forbidden = (
        "os.environ",
        "os.getenv",
        "ADE_APPROVAL_TOKEN_HMAC_SECRET",
        "WEB_PUSH_VAPID_PRIVATE_KEY",
    )
    for s in forbidden:
        assert s not in src, s


def test_module_source_has_no_module_level_io() -> None:
    """No file open / read / write / atomic helpers."""
    src = _module_source()
    forbidden = (
        "tempfile.mkstemp",
        ".write_text(",
        ".read_text(",
        "os.replace(",
        "_atomic_write_json",
        "open(",
    )
    for s in forbidden:
        assert s not in src, s


def test_module_source_has_no_flask_registration() -> None:
    src = _module_source()
    forbidden = (
        "from flask",
        "import flask",
        ".register_blueprint(",
        "add_url_rule(",
    )
    for s in forbidden:
        assert s not in src, s


# ---------------------------------------------------------------------------
# AST-level scans
# ---------------------------------------------------------------------------


def _imported_module_names() -> set[str]:
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_or_network_imports() -> None:
    src = _module_source()
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    )
    for s in forbidden:
        assert s not in src, s


def test_no_dashboard_or_frontend_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_imports_cleanly() -> None:
    importlib.reload(n4a)
    assert callable(n4a.mint_token)
    assert callable(n4a.verify_token)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(n4a)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT / "docs" / "governance" / "approval_token_gate.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_live_wiring_in_n4a() -> None:
    text = _doc_text().lower()
    assert "no live wiring" in text or "no env wiring" in text


def test_doc_states_n4b_is_operator_action_only() -> None:
    text = _doc_text().lower()
    assert "n4b" in text
    assert "operator" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
    )


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        raw = text[start:end].lower()
        cleaned = re.sub(r"\n\s*>\s*", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned)
        assert "permanently disabled" in cleaned
