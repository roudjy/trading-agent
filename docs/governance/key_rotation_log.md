# Key Rotation Log

Append-only log of credential rotations. **Never record the credential value
itself** — only timestamp, service, version-id, operator, and rationale.

Format:

```
| date_utc | service | rotation_id | operator | rationale | verified |
```

Where:
- `date_utc` — ISO-8601 timestamp.
- `service` — one of `anthropic | bitvavo | alchemy | polymarket | ibkr`.
- `rotation_id` — opaque identifier (e.g. internal counter, never the key
  itself, never a partial fingerprint).
- `operator` — GitHub handle or initials.
- `rationale` — `scheduled | suspected_leak | live_enable_prep | post_history_rewrite`.
- `verified` — `yes` (smoke-test against the service ran successfully) or `no`.

---

## Log

| date_utc | service | rotation_id | operator | rationale | verified |
|---|---|---|---|---|---|
| 2026-04-30T00:00:00Z | (none) | — | — | live trading disabled; rotation deferred per [manual_blockers.md](manual_blockers.md) | n/a |

---

## Rules

1. Append-only. Never edit prior rows.
2. No credential values, ever. Not in cells, not in commit messages, not in PR
   bodies.
3. One row per rotation. If a single rotation event touches multiple services,
   write one row per service.
4. The `rotation_id` is operator-chosen; its only purpose is to disambiguate
   reruns of the same service.
5. Linked to [`SECURITY.md`](../../SECURITY.md) §"Credential inventory &
   rotation order" — the order constraint must be respected.
