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
