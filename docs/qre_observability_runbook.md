# QRE Observability Runbook (v3.15.15.2)

## Purpose

The v3.15.15.2 release introduces a read-only observability layer
that generates five sidecar artifacts under
`research/observability/` describing the health, failure
distribution, throughput, and integrity of the running trading
agent. The frontend integration (v3.15.15.3) consumes those
artifacts; without it, the artifacts are still useful for direct
inspection on the VPS.

## Hard contract

* The observability layer **never** modifies any artifact outside
  `research/observability/`.
* The observability layer **never** imports any campaign, sprint,
  policy, screening, sampling, or strategy module — verified by
  `tests/unit/test_observability_static_import_surface.py` (parses `research/diagnostics`).
* The CLI is idempotent and bounded: deterministic output for fixed
  inputs + `now_utc`; ledger reads are capped at 10 000 events / 25 MB.
* The CLI never raises on missing or corrupt input; it marks the
  affected component as `unavailable` / `corrupt` in the output and
  exits 0.

## Manual one-off snapshot (recommended first run after deploy)

```bash
ssh root@23.88.110.92
cd /root/trading-agent
docker exec jvr_dashboard python -m research.diagnostics build
docker exec jvr_dashboard ls -la /app/research/observability/
docker exec jvr_dashboard python -m research.diagnostics status
```

Expected output (status):

```
overall_status: <healthy|degraded|insufficient_evidence|unknown>
component_status_counts: {'available': N, ...}
recommended_next_human_action: <none|inspect_artifacts|investigation_required|roadmap_decision_required>
```

## Enable the systemd timer (15 min cadence) — operator decision

The unit files ship in the repo but are **not** auto-installed by
deploy. Install + enable them when ready:

```bash
sudo cp /root/trading-agent/ops/systemd/trading-agent-observability.service \
        /etc/systemd/system/
sudo cp /root/trading-agent/ops/systemd/trading-agent-observability.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-agent-observability.timer

systemctl list-timers | grep observability
journalctl -u trading-agent-observability.service -n 30 --no-pager
```

Confirm the artifacts refresh on the next quarter-hour:

```bash
docker exec jvr_dashboard ls -la /app/research/observability/
```

## Disable the timer

```bash
sudo systemctl disable --now trading-agent-observability.timer
sudo systemctl stop trading-agent-observability.service  # if mid-run
sudo rm /etc/systemd/system/trading-agent-observability.{service,timer}
sudo systemctl daemon-reload
```

The disabled timer has zero effect on campaign / sprint / launcher
behavior. Leftover artifacts under `research/observability/` are
harmless; you can `rm -f` them if you want a clean slate.

## Full revert of v3.15.15.2

```bash
cd /root/trading-agent
git revert -m 1 <merge-commit-of-feat/observability-v3-15-15-2>
git push origin main
docker compose build dashboard && docker compose up -d dashboard

# (optional) disable timer if you'd already enabled it
sudo systemctl disable --now trading-agent-observability.timer 2>/dev/null || true
```

The revert removes:

* the entire `research/observability/` package,
* the systemd unit files,
* the new test files,
* the runbook + CHANGELOG entry,
* the VERSION bump (back to `3.15.15`).

It does NOT touch any other module — the observability release is
verifiably isolated.

## Artifact catalogue

Each file under `research/observability/` carries
`schema_version: "1.0"` and `generated_at_utc` at the top level so
downstream consumers can detect schema evolution.

| Filename | Source modules | Top-level fields |
|---|---|---|
| `artifact_health_latest.v1.json` | reads frozen contracts + COL artifacts + sprint sidecars + evidence ledgers | `summary`, `artifacts[]` (per-artifact: exists, parse_ok, schema_version, age_seconds, stale, linked_ids, contract_class, …) |
| `failure_modes_latest.v1.json` | reads campaign registry + bounded JSONL ledger | `total_campaigns_observed`, `campaigns_by_outcome`, `campaigns_by_outcome_class`, `top_failure_reasons`, `repeated_failure_clusters`, `technical_vs_research_failure_counts`, `source.ledger_*` |
| `throughput_metrics_latest.v1.json` | reads campaign registry + queue + digest | `campaigns_per_day`, `meaningful_campaigns_per_day`, `runtime_minutes.{p50,p95,avg}`, `queue_wait_seconds.{p50,p95}`, `runtime_by_preset[]`, `workers.{busy,total,busy_rate}`, `queue.{depth,backpressure_flag}` |
| `system_integrity_latest.v1.json` | reads VERSION + `git rev-parse` + `/proc` + `shutil.disk_usage` | `version_file`, `git.{head,branch,dirty}`, `uptime_seconds.{process,container}`, `disk_free_bytes`, `artifact_directory_writable`, `last_observability_artifact_update_unix`, `timezone` |
| `observability_summary_latest.v1.json` | aggregates the four above | `overall_status`, `component_status_counts`, `components[]`, `critical_findings`, `warnings`, `informational_findings`, `recommended_next_human_action` |

Six additional components are reserved for the future v3.15.15.4
release and reported as `status: deferred` in the aggregator output:
`funnel_stage_summary`, `campaign_timeline`, `parameter_coverage`,
`data_freshness`, `policy_decision_trace`, `no_touch_health`.

## Troubleshooting

### Aggregator says "degraded" with a corrupt component

```bash
docker exec jvr_dashboard cat /app/research/observability/observability_summary_latest.v1.json | python -m json.tool | grep -A2 critical
```

Identify the corrupt component, then inspect its raw payload:

```bash
docker exec jvr_dashboard cat /app/research/observability/<component>_latest.v1.json
```

If the file is genuinely garbage (unlikely — atomic rename should
prevent half-writes), trigger a re-build:

```bash
docker exec jvr_dashboard python -m research.diagnostics build
```

### Systemd timer missed runs

`Persistent=true` in the timer unit means systemd fires once on the
next boot if the timer was missed during downtime. Check:

```bash
systemctl status trading-agent-observability.timer
journalctl -u trading-agent-observability.service --since "1 hour ago"
```

### CLI hung

Should be impossible — every read is `Path.read_text()` with no
network IO and the JSONL tail is byte-bounded. If it does hang, kill
the systemd job (`systemctl stop trading-agent-observability.service`)
and inspect `journalctl`. File a bug; do **not** patch in production.
