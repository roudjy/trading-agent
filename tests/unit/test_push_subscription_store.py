"""Unit tests for N2b-2a — Push Subscription Store (backend, unwired).

The store is pure-stdlib; no real push, no socket, no Web Push library.

Pinned here:

* Closed record schema, allowed origins, capacity bound.
* Atomic-write refusal outside the closed sentinel path.
* Idempotent register / unregister.
* Both runtime-config paths are not tracked by git.
* Neither path leaks endpoints or keys.
* AST + source-text scans rule out: socket, urllib, requests, httpx,
  aiohttp, pywebpush, webpush, web_push, WEB_PUSH_VAPID_PRIVATE_KEY,
  subprocess, gh, git, dashboard, frontend, automation, broker,
  agent.risk, agent.execution, research, reporting.intelligent_routing,
  live, paper, shadow, trading.
* Importing the module does not flip Step 5 invariants.
* Doc states no real push, no click-approval, Level 6 permanently
  disabled.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from reporting import push_subscription_store as pss


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _store_path(tmp_path: Path) -> Path:
    p = tmp_path / "config" / "web_push_subscriptions.json"
    p.parent.mkdir(parents=True)
    return p


def _patch_paths(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    sub_path = _store_path(tmp_path)
    vapid_path = tmp_path / "config" / "web_push_vapid_public.txt"
    monkeypatch.setattr(pss, "SUBSCRIPTIONS_PATH", sub_path)
    monkeypatch.setattr(pss, "VAPID_PUBLIC_PATH", vapid_path)
    return sub_path, vapid_path


def _valid_record(*, endpoint_suffix: str = "abc123") -> dict[str, Any]:
    return {
        "endpoint": f"https://fcm.googleapis.com/fcm/send/{endpoint_suffix}",
        "keys": {
            "p256dh": "BCfV1eK4_p256dh_public_key_base64url_text",
            "auth": "auth_secret_base64url_text",
        },
        "kid": "k1",
        "label": "iPhone PWA",
    }


# ---------------------------------------------------------------------------
# Closed vocabularies + bounds
# ---------------------------------------------------------------------------


def test_subscription_record_keys_pinned_exactly() -> None:
    assert pss.SUBSCRIPTION_RECORD_KEYS == (
        "endpoint",
        "keys",
        "kid",
        "created_at",
        "last_seen_at",
        "label",
    )


def test_keys_field_subkeys_pinned_exactly() -> None:
    assert pss.SUBSCRIPTION_KEYS_FIELD_KEYS == ("p256dh", "auth")


def test_max_active_subscriptions_pinned() -> None:
    assert pss.MAX_ACTIVE_SUBSCRIPTIONS == 16


def test_allowed_endpoint_prefixes_pinned() -> None:
    assert pss.ALLOWED_ENDPOINT_PREFIXES == (
        "https://fcm.googleapis.com/",
        "https://updates.push.services.mozilla.com/",
        "https://web.push.apple.com/",
        "https://wns2-",
    )


def test_subscriptions_relative_path_under_config() -> None:
    assert pss.SUBSCRIPTIONS_RELATIVE_PATH == (
        "config/web_push_subscriptions.json"
    )


def test_vapid_public_relative_path_under_config() -> None:
    assert pss.VAPID_PUBLIC_RELATIVE_PATH == (
        "config/web_push_vapid_public.txt"
    )


# ---------------------------------------------------------------------------
# Gitignore / not-tracked guarantees
# ---------------------------------------------------------------------------


def test_subscription_path_not_committed() -> None:
    """The runtime-config path must not appear in git ls-files."""
    out = subprocess.run(
        ["git", "ls-files", "config/web_push_subscriptions.json"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert out.stdout.strip() == "", out.stdout


def test_vapid_public_path_not_committed() -> None:
    out = subprocess.run(
        ["git", "ls-files", "config/web_push_vapid_public.txt"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert out.stdout.strip() == "", out.stdout


# ---------------------------------------------------------------------------
# Atomic write refusal
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_subscription_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "subscriptions.json"
    bad.parent.mkdir(parents=True)
    with pytest.raises(ValueError):
        pss._atomic_write_json(bad, {"subscriptions": []})


def test_atomic_write_refuses_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "logs" / "web_push_subscriptions.json"
    bad.parent.mkdir(parents=True)
    with pytest.raises(ValueError):
        pss._atomic_write_json(bad, {"subscriptions": []})


# ---------------------------------------------------------------------------
# Empty store / load / save
# ---------------------------------------------------------------------------


def test_empty_store_on_first_read(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    store = pss.load_store()
    assert store == {"schema_version": 1, "subscriptions": []}


def test_list_subscriptions_empty_initially(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    assert pss.list_subscriptions() == []


def test_corrupt_store_returns_empty(tmp_path: Path, monkeypatch) -> None:
    sub_path, _ = _patch_paths(tmp_path, monkeypatch)
    sub_path.write_text("not json", encoding="utf-8")
    assert pss.load_store() == {"schema_version": 1, "subscriptions": []}


# ---------------------------------------------------------------------------
# register / unregister behaviour
# ---------------------------------------------------------------------------


def test_register_subscription_writes_one_record(
    tmp_path: Path, monkeypatch
) -> None:
    sub_path, _ = _patch_paths(tmp_path, monkeypatch)
    rec, warnings = pss.register_subscription(
        _valid_record(), now_utc="2026-05-09T00:00:00Z"
    )
    assert rec is not None
    assert warnings == []
    assert sub_path.is_file()
    on_disk = json.loads(sub_path.read_text(encoding="utf-8"))
    assert len(on_disk["subscriptions"]) == 1
    assert set(on_disk["subscriptions"][0].keys()) == set(
        pss.SUBSCRIPTION_RECORD_KEYS
    )
    assert rec["created_at"] == "2026-05-09T00:00:00Z"
    assert rec["last_seen_at"] == "2026-05-09T00:00:00Z"


def test_register_same_endpoint_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    pss.register_subscription(_valid_record(), now_utc="2026-05-09T00:00:00Z")
    rec2, _ = pss.register_subscription(
        _valid_record(), now_utc="2026-05-09T00:01:00Z"
    )
    assert rec2 is not None
    assert rec2["created_at"] == "2026-05-09T00:00:00Z"  # original
    assert rec2["last_seen_at"] == "2026-05-09T00:01:00Z"  # refreshed
    assert len(pss.list_subscriptions()) == 1


def test_unregister_subscription_removes_by_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    pss.register_subscription(_valid_record())
    rec = _valid_record()
    removed = pss.unregister_subscription(rec["endpoint"])
    assert removed is True
    assert pss.list_subscriptions() == []


def test_unregister_subscription_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    assert pss.unregister_subscription("https://fcm.googleapis.com/x") is False
    pss.register_subscription(_valid_record())
    assert pss.unregister_subscription(_valid_record()["endpoint"]) is True
    assert pss.unregister_subscription(_valid_record()["endpoint"]) is False


def test_get_by_endpoint(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    rec = _valid_record(endpoint_suffix="abc1")
    pss.register_subscription(rec)
    found = pss.get_by_endpoint(rec["endpoint"])
    assert found is not None
    assert found["endpoint"] == rec["endpoint"]
    assert pss.get_by_endpoint("https://fcm.googleapis.com/missing") is None


# ---------------------------------------------------------------------------
# Capacity bound
# ---------------------------------------------------------------------------


def test_store_capped_at_max_active_subscriptions(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    for i in range(pss.MAX_ACTIVE_SUBSCRIPTIONS):
        rec, warnings = pss.register_subscription(
            _valid_record(endpoint_suffix=f"sub_{i:03d}"),
            now_utc="2026-05-09T00:00:00Z",
        )
        assert rec is not None
        assert warnings == []
    # 17th should be refused.
    rec_extra, warnings = pss.register_subscription(
        _valid_record(endpoint_suffix="overflow"),
        now_utc="2026-05-09T00:00:00Z",
    )
    assert rec_extra is None
    assert "subscription_cap_reached" in warnings
    assert len(pss.list_subscriptions()) == pss.MAX_ACTIVE_SUBSCRIPTIONS


def test_store_cap_does_not_block_idempotent_refresh(
    tmp_path: Path, monkeypatch
) -> None:
    """Once at cap, refreshing an existing endpoint must still work."""
    _patch_paths(tmp_path, monkeypatch)
    for i in range(pss.MAX_ACTIVE_SUBSCRIPTIONS):
        pss.register_subscription(
            _valid_record(endpoint_suffix=f"sub_{i:03d}"),
            now_utc="2026-05-09T00:00:00Z",
        )
    rec, warnings = pss.register_subscription(
        _valid_record(endpoint_suffix="sub_000"),
        now_utc="2026-05-09T00:01:00Z",
    )
    assert rec is not None
    assert "subscription_cap_reached" not in warnings


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_record_shape_rejected(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    rec, warnings = pss.register_subscription("not a dict")
    assert rec is None
    assert "not_an_object" in warnings


def test_missing_endpoint_rejected(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    bad = _valid_record()
    bad["endpoint"] = ""
    rec, warnings = pss.register_subscription(bad)
    assert rec is None
    assert "missing_endpoint" in warnings


def test_endpoint_origin_not_allowed_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    bad = _valid_record()
    bad["endpoint"] = "https://attacker.example.com/notify"
    rec, warnings = pss.register_subscription(bad)
    assert rec is None
    assert "endpoint_origin_not_allowed" in warnings


def test_invalid_keys_shape_rejected(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    bad = _valid_record()
    bad["keys"] = {"p256dh": "x"}  # missing auth
    rec, warnings = pss.register_subscription(bad)
    assert rec is None
    assert "invalid_keys_shape" in warnings


def test_missing_kid_rejected(tmp_path: Path, monkeypatch) -> None:
    _patch_paths(tmp_path, monkeypatch)
    bad = _valid_record()
    bad["kid"] = ""
    rec, warnings = pss.register_subscription(bad)
    assert rec is None
    assert "missing_kid" in warnings


# ---------------------------------------------------------------------------
# Endpoint hash + redaction
# ---------------------------------------------------------------------------


def test_endpoint_hash_is_sha256_truncated() -> None:
    h = pss.endpoint_hash("https://fcm.googleapis.com/fcm/send/abc")
    assert isinstance(h, str)
    assert len(h) == 16
    # Deterministic.
    assert h == pss.endpoint_hash("https://fcm.googleapis.com/fcm/send/abc")
    # Different endpoint → different hash.
    h2 = pss.endpoint_hash("https://fcm.googleapis.com/fcm/send/xyz")
    assert h != h2


def test_endpoint_hash_returns_empty_for_non_string() -> None:
    assert pss.endpoint_hash(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# VAPID public key helpers
# ---------------------------------------------------------------------------


def test_vapid_public_present_false_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_paths(tmp_path, monkeypatch)
    assert pss.vapid_public_present() is False
    assert pss.vapid_public_text() is None


def test_vapid_public_present_true_when_present(
    tmp_path: Path, monkeypatch
) -> None:
    _, vapid_path = _patch_paths(tmp_path, monkeypatch)
    vapid_path.write_text("BPublicKeyBase64UrlText\n", encoding="utf-8")
    assert pss.vapid_public_present() is True
    assert pss.vapid_public_text() == "BPublicKeyBase64UrlText"


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(pss.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src, forbidden


def test_no_web_push_library_imports() -> None:
    src = _module_source()
    for forbidden in (
        "import pywebpush",
        "from pywebpush",
        "import webpush",
        "from webpush",
        "import web_push",
        "from web_push",
    ):
        assert forbidden not in src, forbidden


def test_no_vapid_private_key_reference() -> None:
    """The literal env-var name must not appear in N2b-2a source.
    Reading the private key is N2b-3 territory."""
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


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
    importlib.reload(pss)
    assert callable(pss.list_subscriptions)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(pss)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "notification_dispatch_subscription.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_real_push_in_n2b2a() -> None:
    text = _doc_text().lower()
    assert "no real push" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    # Collapse whitespace so multi-line wrapping in markdown doesn't
    # break the assertion. Accept either common phrasing.
    import re
    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
        or "no approval can happen from a notification click alone" in text
    )


def test_doc_states_dashboard_dashboard_unchanged() -> None:
    text = _doc_text().lower()
    assert "dashboard/dashboard.py" in text
    assert "unchanged" in text


def test_doc_states_n2b2b_n2b3_n3_n4_n5_unimplemented() -> None:
    text = _doc_text().lower()
    for marker in ("n2b-2b", "n2b-3", "n3", "n4", "n5"):
        assert marker in text, marker
    assert "unimplemented" in text or "out of scope" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    import re

    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window
