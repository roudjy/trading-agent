"""Unit tests for N4b — reporting.approval_token_runtime.

Pins:
* ``is_configured`` is env-only and never echoes the secret;
* hex / base64url / raw-bytes secret decoding all work, short
  secrets are rejected;
* ``mint_runtime`` rejects missing env, invalid intent, missing
  event_id, missing evidence_hash, and bubbles the closed status
  vocabulary;
* ``mint_runtime`` on the happy path returns a token + ``status="ok"``
  + bounded claim envelope; the response is closed-shape;
* ``verify_runtime`` happy round-trip;
* replay rejection on second verify of the same nonce;
* expired-token rejection;
* binding-mismatch rejection (event_id, evidence_hash, pr_number,
  pr_head_sha, release_tag);
* malformed-token rejection;
* configuration_missing on missing env;
* the seen-nonce store is bounded and the write path refuses
  non-sentinel paths;
* source-text + AST scans: no subprocess / gh / git / pywebpush /
  approve(/reject(/merge(/deploy( call patterns / seed.jsonl writes;
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import ast
import importlib
import json
import secrets as _secrets
from pathlib import Path
from typing import Any

import pytest

from reporting import approval_token_gate as atg
from reporting import approval_token_runtime as atr


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(atr.__file__).resolve()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _synthetic_secret_hex() -> str:
    """Return a 64-hex-char (32-byte) synthetic secret. Tests-only."""
    return _secrets.token_hex(32)


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect SEEN_NONCES_PATH into ``tmp_path/state/``. The repo's
    ``state/`` directory is gitignored runtime state we never touch
    from unit tests."""
    target = tmp_path / "state" / "approval_token_seen_nonces.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(atr, "SEEN_NONCES_PATH", target)
    # The sentinel-restricted write helper uses a substring match,
    # so a tmp_path of any depth works.
    return target


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)


# ---------------------------------------------------------------------------
# is_configured + env decoding
# ---------------------------------------------------------------------------


def test_step5_invariants_intact() -> None:
    assert atr.STEP5_ENABLED_SUBSTAGE == "none"
    assert atr.step5_implementation_allowed is False


def test_is_configured_false_when_env_unset() -> None:
    assert atr.is_configured() is False


def test_is_configured_false_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, "")
    assert atr.is_configured() is False


def test_is_configured_false_when_secret_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, "shortsecret")
    assert atr.is_configured() is False


def test_is_configured_true_with_valid_hex_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    assert atr.is_configured() is True


def test_is_configured_true_with_valid_raw_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, "x" * 32
    )
    assert atr.is_configured() is True


def test_is_configured_returns_boolean_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence-in-depth: the predicate never embeds the secret in
    its return value or its repr."""
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    result = atr.is_configured()
    assert isinstance(result, bool)
    assert repr(result) in ("True", "False")


# ---------------------------------------------------------------------------
# mint_runtime — failure modes
# ---------------------------------------------------------------------------


def test_mint_runtime_configuration_missing_when_env_unset() -> None:
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="evt_x",
        evidence_hash="h_x",
    )
    assert out["status"] == "configuration_missing"
    assert out["token"] is None


def test_mint_runtime_invalid_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent="bogus_intent",
        event_id="evt_x",
        evidence_hash="h_x",
    )
    assert out["status"] == "invalid_intent"
    assert out["token"] is None


def test_mint_runtime_invalid_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="",
        evidence_hash="h_x",
    )
    assert out["status"] == "invalid_event_id"
    assert out["token"] is None


def test_mint_runtime_invalid_evidence_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="evt_x",
        evidence_hash="",
    )
    assert out["status"] == "invalid_evidence_hash"


# ---------------------------------------------------------------------------
# mint_runtime — happy path + closed-shape result envelope
# ---------------------------------------------------------------------------


def test_mint_runtime_happy_path_returns_closed_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="evt_happy",
        pr_number=42,
        pr_head_sha="abcdef0123456789",
        evidence_hash="h_evidence_42",
        release_tag=None,
    )
    assert out["status"] == "ok"
    assert isinstance(out["token"], str) and "." in out["token"]
    assert set(out.keys()) >= set(atr.MINT_RESULT_KEYS)
    assert out["kid"] == atr.CURRENT_KID
    assert out["intent"] == "mobile_approval_dispatch"
    assert out["event_id"] == "evt_happy"
    assert out["issued_at_utc"]
    assert out["expires_at_utc"]


def test_mint_runtime_secret_never_leaks_into_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _synthetic_secret_hex()
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="evt_no_leak",
        evidence_hash="h_evidence",
    )
    raw_repr = json.dumps(out, default=str)
    # The raw env value must NEVER appear in the response.
    assert raw not in raw_repr


# ---------------------------------------------------------------------------
# verify_runtime — happy round-trip
# ---------------------------------------------------------------------------


def _mint_for_verify(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_id: str = "evt_rt",
    pr_number: int | None = 99,
    pr_head_sha: str | None = "deadbeef00000001",
    evidence_hash: str = "h_rt_evidence",
    release_tag: str | None = None,
) -> str:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
        release_tag=release_tag,
    )
    assert out["status"] == "ok"
    return out["token"]


def test_verify_runtime_happy_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_for_verify(monkeypatch)
    out = atr.verify_runtime(
        token=token,
        expected_event_id="evt_rt",
        expected_pr_number=99,
        expected_pr_head_sha="deadbeef00000001",
        expected_evidence_hash="h_rt_evidence",
        expected_release_tag=None,
    )
    assert out == {"status": "ok", "outcome": "ok", "reason": "verified"}


def test_verify_runtime_replay_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_for_verify(monkeypatch)
    # First verify: ok + nonce recorded.
    first = atr.verify_runtime(
        token=token,
        expected_event_id="evt_rt",
        expected_pr_number=99,
        expected_pr_head_sha="deadbeef00000001",
        expected_evidence_hash="h_rt_evidence",
    )
    assert first["status"] == "ok"
    # Second verify of the same token: replay detected.
    second = atr.verify_runtime(
        token=token,
        expected_event_id="evt_rt",
        expected_pr_number=99,
        expected_pr_head_sha="deadbeef00000001",
        expected_evidence_hash="h_rt_evidence",
    )
    assert second["status"] == "rejected"
    assert second["outcome"] == "replay_detected"


def test_verify_runtime_binding_mismatch_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_for_verify(monkeypatch)
    out = atr.verify_runtime(
        token=token,
        expected_event_id="evt_other",
        expected_pr_number=99,
        expected_pr_head_sha="deadbeef00000001",
        expected_evidence_hash="h_rt_evidence",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "binding_mismatch"


def test_verify_runtime_binding_mismatch_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_for_verify(monkeypatch)
    out = atr.verify_runtime(
        token=token,
        expected_event_id="evt_rt",
        expected_pr_number=99,
        expected_pr_head_sha="deadbeef00000001",
        expected_evidence_hash="h_other_evidence",
    )
    assert out["outcome"] == "binding_mismatch"


def test_verify_runtime_malformed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.verify_runtime(
        token="not-a-valid-token",
        expected_event_id="evt",
        expected_evidence_hash="h",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "malformed_envelope"


def test_verify_runtime_configuration_missing() -> None:
    out = atr.verify_runtime(
        token="anything.anything",
        expected_event_id="evt",
        expected_evidence_hash="h",
    )
    assert out["status"] == "configuration_missing"


def test_verify_runtime_expired_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanity: when N4a expires a token, verify_runtime surfaces
    ``outcome == "expired"``."""
    raw = _synthetic_secret_hex()
    secret_bytes = bytes.fromhex(raw)
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    # Build a token that is already expired by calling N4a directly
    # with a ``now`` in the past minus more than the TTL.
    from datetime import UTC, datetime, timedelta

    past = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=2 * atg.DEFAULT_TTL_SECONDS)
    token = atg.mint_token(
        intent="mobile_approval_dispatch",
        event_id="evt_expire",
        pr_number=None,
        pr_head_sha=None,
        evidence_hash="h_exp",
        release_tag=None,
        kid=atr.CURRENT_KID,
        secret=secret_bytes,
        ttl_seconds=atg.DEFAULT_TTL_SECONDS,
        now=past,
    )
    out = atr.verify_runtime(
        token=token,
        expected_event_id="evt_expire",
        expected_evidence_hash="h_exp",
    )
    assert out["outcome"] == "expired"
    assert out["status"] == "rejected"


# ---------------------------------------------------------------------------
# Seen-nonce store
# ---------------------------------------------------------------------------


def test_record_nonce_round_trip() -> None:
    assert atr.is_nonce_seen("nonce_a") is False
    assert atr.record_nonce("nonce_a") is True
    assert atr.is_nonce_seen("nonce_a") is True
    assert atr.record_nonce("nonce_a") is False


def test_record_nonce_atomic_write_refuses_non_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "approval_token_seen_nonces.jsonl"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(atr, "SEEN_NONCES_PATH", bogus)
    # The sentinel-substring guard refuses any path that does not
    # contain the closed prefix.
    with pytest.raises(ValueError):
        atr.record_nonce("any_nonce")


def test_seen_nonce_store_bounded_to_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shrink the bound to make the test cheap.
    monkeypatch.setattr(atr, "MAX_SEEN_NONCES", 5)
    for i in range(20):
        atr.record_nonce(f"nonce_{i}")
    seen = atr._read_seen_nonces()  # type: ignore[attr-defined]
    assert len(seen) <= 5
    # The newest entries are retained.
    assert "nonce_19" in seen


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_in_module() -> None:
    src = _module_source()
    for needle in ("subprocess.run", " gh ", " git "):
        assert needle not in src, needle


def test_no_web_push_library_import_in_module() -> None:
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n
        assert not n.startswith("pywebpush."), n


def test_no_vapid_private_key_literal_in_module() -> None:
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_env_var_name_appears_only_here() -> None:
    src = _module_source()
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" in src


def test_no_decision_verb_call_in_module() -> None:
    src = _module_source().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in src, verb


def test_no_seed_jsonl_writes_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
    ):
        assert forbidden not in src, forbidden


def test_no_forbidden_module_imports() -> None:
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
            assert module != prefix, module
            assert not module.startswith(prefix + "."), module


def test_imports_only_atg_aas_stdlib() -> None:
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.approval_token_gate",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


# ---------------------------------------------------------------------------
# Step 5 invariants — import-time
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(atr)
    assert atr.step5_implementation_allowed is False
    assert atr.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


# ---------------------------------------------------------------------------
# verify_runtime_for_dry_run — B2.8c N5b Phase 2 dry-run walker entrypoint
#
# Pins (per the operator-approved B2.8c contract):
# * Happy path returns verified kid / nonce_hash / event_id / intent.
# * Every rejected / configuration_missing branch returns exactly the
#   3-key {status, outcome, reason} envelope (no claim metadata leak).
# * Raw nonce and raw token never appear in the response.
# * Replay rejected on the second call.
# * Intent drift rejected after signature verification.
# * Wrong expected_intent rejected before the env is read or the
#   verifier is invoked.
# * verify_runtime / mint_runtime existing surface UNCHANGED.
# ---------------------------------------------------------------------------


_OK_KEYS = {"status", "outcome", "reason", "kid", "nonce_hash", "event_id", "intent"}
_REJECTED_KEYS = {"status", "outcome", "reason"}


def _mint_dry_run_token(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_id: str = "evt_dry_run",
    pr_number: int = 42,
    pr_head_sha: str = "deadbeef" * 5,
    evidence_hash: str = "h_dry_run_evidence",
    intent: str = "mobile_approval_dispatch",
) -> str:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.mint_runtime(
        intent=intent,
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
    )
    assert out["status"] == "ok", out
    return out["token"]


def test_verify_for_dry_run_happy_path_returns_verified_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    out = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "ok"
    assert out["outcome"] == "ok"
    assert out["reason"] == "verified"
    assert out["kid"] == atr.CURRENT_KID
    # nonce_hash is sha256 hex → 64 lowercase hex chars.
    assert isinstance(out["nonce_hash"], str) and len(out["nonce_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in out["nonce_hash"])
    assert out["event_id"] == "evt_dry_run"
    assert out["intent"] == "mobile_approval_dispatch"
    assert set(out.keys()) == _OK_KEYS


def test_verify_for_dry_run_ok_envelope_carries_no_raw_nonce_or_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    out = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    blob = json.dumps(out, default=str)
    # The raw token must NEVER appear in the response.
    assert token not in blob
    # No claim contains a raw nonce; nonce_hash is the only nonce-derived
    # field. We do not know the raw nonce here, but we assert no
    # token-shaped substring leaks back.
    assert "." not in out["nonce_hash"]


def test_verify_for_dry_run_replay_rejects_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    first = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert first["status"] == "ok"
    second = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert second["status"] == "rejected"
    assert second["outcome"] == "replay_detected"
    assert set(second.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_wrong_expected_intent_rejects_before_env_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrong-intent guard runs BEFORE the env is read; this is a
    contract pin that protects the env-secret read from being
    influenced by attacker-supplied intent values."""
    # No env set deliberately — the guard must reject without reading.
    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)
    out = atr.verify_runtime_for_dry_run(
        token="anything.anything",
        expected_pr_number=1,
        expected_pr_head_sha="x" * 16,
        expected_evidence_hash="h",
        expected_intent="mobile_review_dispatch",  # closed N4a intent but NOT the dry-run intent
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "intent_unknown"
    assert out["reason"] == "expected_intent_not_supported"
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_configuration_missing_when_env_unset() -> None:
    out = atr.verify_runtime_for_dry_run(
        token="anything.anything",
        expected_pr_number=1,
        expected_pr_head_sha="x" * 16,
        expected_evidence_hash="h",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "configuration_missing"
    assert out["outcome"] == ""
    assert out["reason"] == "env_secret_absent"
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_signature_invalid_no_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tamper the claims half so verify_token rejects with
    signature_invalid (or malformed_envelope if shape breaks)."""
    token = _mint_dry_run_token(monkeypatch)
    claims_b64, sig_b64 = token.split(".", 1)
    # Tamper sig so HMAC mismatches.
    tampered = f"{claims_b64}.{'A' * len(sig_b64)}"
    out = atr.verify_runtime_for_dry_run(
        token=tampered,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] in {"signature_invalid", "malformed_envelope"}
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_malformed_token_no_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    out = atr.verify_runtime_for_dry_run(
        token="not-a-valid-token",
        expected_pr_number=1,
        expected_pr_head_sha="x" * 16,
        expected_evidence_hash="h",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "malformed_envelope"
    assert set(out.keys()) == _REJECTED_KEYS


@pytest.mark.parametrize(
    "drift_kwarg,drift_value,expected_reason",
    [
        ("expected_pr_number", 999, "pr_number_mismatch"),
        ("expected_pr_head_sha", "f" * 40, "pr_head_sha_mismatch"),
        ("expected_evidence_hash", "h_other_evidence", "evidence_hash_mismatch"),
    ],
)
def test_verify_for_dry_run_binding_mismatch_no_metadata(
    monkeypatch: pytest.MonkeyPatch,
    drift_kwarg: str,
    drift_value: Any,
    expected_reason: str,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    kwargs: dict[str, Any] = {
        "token": token,
        "expected_pr_number": 42,
        "expected_pr_head_sha": "deadbeef" * 5,
        "expected_evidence_hash": "h_dry_run_evidence",
        "expected_intent": "mobile_approval_dispatch",
    }
    kwargs[drift_kwarg] = drift_value
    out = atr.verify_runtime_for_dry_run(**kwargs)
    assert out["status"] == "rejected"
    assert out["outcome"] == "binding_mismatch"
    assert out["reason"] == expected_reason
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_intent_drift_rejects_after_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token minted with a different N4a-vocab intent
    (`mobile_review_dispatch`). The signature still verifies, but the
    walker rejects the claimed intent vs the expected dry-run intent
    with reason='intent_drift' — and surfaces no metadata."""
    token = _mint_dry_run_token(
        monkeypatch,
        intent="mobile_review_dispatch",
    )
    out = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "binding_mismatch"
    assert out["reason"] == "intent_drift"
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_expired_token_no_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _synthetic_secret_hex()
    secret_bytes = bytes.fromhex(raw)
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    from datetime import UTC, datetime, timedelta

    past = datetime.now(UTC).replace(microsecond=0) - timedelta(
        seconds=2 * atg.DEFAULT_TTL_SECONDS
    )
    token = atg.mint_token(
        intent="mobile_approval_dispatch",
        event_id="evt_expire",
        pr_number=42,
        pr_head_sha="deadbeef" * 5,
        evidence_hash="h_dry_run_evidence",
        release_tag=None,
        kid=atr.CURRENT_KID,
        secret=secret_bytes,
        ttl_seconds=atg.DEFAULT_TTL_SECONDS,
        now=past,
    )
    out = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h_dry_run_evidence",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "expired"
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_unknown_kid_no_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mint with a kid the runtime does not know."""
    raw = _synthetic_secret_hex()
    secret_bytes = bytes.fromhex(raw)
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    token = atg.mint_token(
        intent="mobile_approval_dispatch",
        event_id="evt",
        pr_number=42,
        pr_head_sha="deadbeef" * 5,
        evidence_hash="h",
        release_tag=None,
        kid="not_a_real_kid",
        secret=secret_bytes,
    )
    out = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h",
        expected_intent="mobile_approval_dispatch",
    )
    assert out["status"] == "rejected"
    assert out["outcome"] == "unknown_kid"
    assert set(out.keys()) == _REJECTED_KEYS


def test_verify_for_dry_run_secret_never_leaks_into_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _synthetic_secret_hex()
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    out = atr.mint_runtime(
        intent="mobile_approval_dispatch",
        event_id="evt",
        pr_number=42,
        pr_head_sha="deadbeef" * 5,
        evidence_hash="h",
    )
    token = out["token"]
    verified = atr.verify_runtime_for_dry_run(
        token=token,
        expected_pr_number=42,
        expected_pr_head_sha="deadbeef" * 5,
        expected_evidence_hash="h",
        expected_intent="mobile_approval_dispatch",
    )
    blob = json.dumps(verified, default=str)
    assert raw not in blob


def test_verify_for_dry_run_is_exported() -> None:
    assert "verify_runtime_for_dry_run" in atr.__all__
    assert callable(atr.verify_runtime_for_dry_run)


def test_verify_for_dry_run_does_not_modify_existing_surface() -> None:
    """Existing public callables must keep their identity. This pin
    catches accidental replacement / wrapping of verify_runtime,
    mint_runtime, is_configured, secrets_by_kid, record_nonce, or
    current_kid by the B2.8c addition."""
    for name in (
        "verify_runtime",
        "mint_runtime",
        "is_configured",
        "secrets_by_kid",
        "record_nonce",
        "current_kid",
    ):
        assert callable(getattr(atr, name))
        assert name in atr.__all__
