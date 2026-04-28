# systemd-timer voor de daily default research run (v3.10)

Volgens ADR-011 §5 draait de daily default preset
(`trend_equities_4h_baseline`) **op de VPS host**, niet in een container,
via een systemd-timer. Dezelfde execution path als UI-triggered runs:
`docker exec jvr_dashboard python /app/researchctl.py run trend_equities_4h_baseline`.

De crypto-diagnostic preset is expliciet **niet** ingepland (flag
`excluded_from_daily_scheduler=True` in `research/presets.py`).

## Installeren (één keer per host)

```bash
sudo cp ops/systemd/trading-agent-daily-research.service /etc/systemd/system/
sudo cp ops/systemd/trading-agent-daily-research.timer   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-agent-daily-research.timer
```

## Status checken

```bash
systemctl list-timers trading-agent-daily-research.timer
journalctl -u trading-agent-daily-research.service -n 100 --no-pager
```

## Ad-hoc één keer starten

```bash
sudo systemctl start trading-agent-daily-research.service
```

## Uitschakelen (bij incidenten of maintenance window)

```bash
sudo systemctl disable --now trading-agent-daily-research.timer
```

`scripts/deploy.sh` rapporteert na elke deploy of de timer actief is.
Failures zijn zichtbaar in `journalctl` en via `/api/report/history` +
`/api/research/run-status` in het dashboard.

---

# trading-agent-observability — read-only observability snapshotter (v3.15.15.2)

Every 15 min, runs `python -m research.diagnostics build` inside
the existing `jvr_dashboard` container. Writes ONLY to
`research/observability/*`. Reads existing artifacts passively.

The observability layer is verified read-only by two contractual
tests:

* `tests/unit/test_observability_static_import_surface.py` — refuses
  any import of campaign / sprint / strategy / runtime modules
  inside `research/diagnostics/`.
* `tests/unit/test_observability_no_other_artifacts_mutated.py` — an
  end-to-end mtime snapshot test proving only `research/observability/*`
  changes during a build.

## NOT auto-installed during the v3.15.15.2 deploy

The v3.15.15.2 release ships the unit files in the repo but does
**not** install or enable them automatically. The operator decides
when to enable, after a manual one-off CLI run has been verified.

### Manual install

```bash
sudo cp /root/trading-agent/ops/systemd/trading-agent-observability.service \
        /etc/systemd/system/
sudo cp /root/trading-agent/ops/systemd/trading-agent-observability.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-agent-observability.timer

# Verify
systemctl status trading-agent-observability.timer
systemctl list-timers | grep observability
```

### Trigger one snapshot immediately

```bash
sudo systemctl start trading-agent-observability.service
docker exec jvr_dashboard ls -la /app/research/observability/
```

### Manual one-off run without systemd

```bash
docker exec jvr_dashboard python -m research.diagnostics build
docker exec jvr_dashboard python -m research.diagnostics status
```

CLI exit codes: 0 = clean, 3 = partial (a component raised), 4 = fatal,
2 = argparse error.

### Disable / rollback

```bash
sudo systemctl disable --now trading-agent-observability.timer
sudo systemctl stop trading-agent-observability.service  # if mid-run
sudo rm /etc/systemd/system/trading-agent-observability.{service,timer}
sudo systemctl daemon-reload
```

Timer being down has zero effect on campaign / sprint / launcher
behavior — observability is purely additive.
