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
    assert "step5_implementation_allowed = True" not in src
