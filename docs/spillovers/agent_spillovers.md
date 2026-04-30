# Agent Spillovers

Items deferred from one version window to a later one. The Product Owner
agent moves an item here when it is `open` at the close of a version and
the operator decides it is not blocking.

| from_version | to_version | item_id (in agent_backlog.md) | reason | next_window |
|---|---|---|---|---|

---

## Conventions

- Append-only by row.
- **Always reference the original row** in `docs/backlog/agent_backlog.md`
  via `item_id`; do not duplicate content.
- `next_window` is the version window in which the item is expected to
  re-surface (e.g. `v3.15.15.13`, or `v3.16+` for "after live trading
  starts").
- **No secrets.**

## Why a separate file

An item can be `open` for many version windows; we want the "this is
explicitly spilled into the next window" decision recorded as its own
event so future operators can see at a glance why they inherited it.
