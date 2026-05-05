# Bootstrap template — wiring `dashboard/dashboard.py`

> Template shape used by `reporting.governance_bootstrap`
> (v3.15.16.9) when the v3.15.16.8 `human_needed` detector finds
> a `register_*_routes` definition in `dashboard/api_*.py` that is
> NOT called in `dashboard/dashboard.py`.

## Canonical case (v3.15.16.5)

`dashboard/api_roadmap_priority.py` defines
`register_roadmap_priority_routes` but `dashboard/dashboard.py`
does not import or call it, so the
`/api/agent-control/next-up` endpoint returns 404 on the VPS.

The synthesized template:

```
branch_name:    governance-bootstrap/<event_id>
commit_message: governance-bootstrap: register_roadmap_priority_routes
file_diff:
    # Add to dashboard/dashboard.py imports section:
    from dashboard.api_roadmap_priority import register_roadmap_priority_routes

    # Add to the route-registration block:
    register_roadmap_priority_routes(app)
pr_title:       governance-bootstrap: register_roadmap_priority_routes
```

## Why the operator merges this manually

`dashboard/dashboard.py` is on the no-touch list per
`.claude/hooks/deny_no_touch.py:80`. Even when the operator
authorises the wiring in chat, the hook blocks the file-level
write. The bootstrap PR is therefore intentionally
operator-authored — the synthesizer prepares the diff, the
operator commits and merges.

## Validation checklist (operator)

- [ ] PR diff contains EXACTLY the two added lines (one import, one
      call). Nothing else.
- [ ] CI green on every required check.
- [ ] Frozen-contract sha256 unchanged.
- [ ] No additional `register_*_routes` lines added.
- [ ] No `register_execute_safe_routes` line added (forbidden by
      v3.15.15.27 invariant; pinned by
      `tests/unit/test_observability_security_invariants.py::test_dashboard_does_not_wire_execute_safe_routes`).

## After merge

Next deploy tick:

1. recurring_maintenance refresh runs.
2. human_needed re-scans dashboard.py, no longer detects the gap.
3. human_needed event clears.
4. governance_bootstrap drops the template.
5. PWA Inbox card row clears on the operator's next refresh.
