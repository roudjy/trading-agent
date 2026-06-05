# QRE Controlled 328 Discovery Grid VPS Runbook

## 1. Doel

Deze run evalueert alle 328 instrument x behavior-preset combinations uit de read-only discovery catalog.
Dit is research evidence generation.
Dit activeert geen paper/shadow/live.
De runner doet nu echte per-combination attempts via bestaande research/validation codepaden waar een executable mapping bestaat.
Niet-uitvoerbare combinations worden niet gecrasht maar expliciet als `skipped` met een concrete blocker weggeschreven.

## 2. VPS voorbereiding

```bash
cd /root/trading-agent
git fetch origin
git switch main
git pull --ff-only
python --version
git status --short
```

## 3. Plan controleren

```bash
python -m reporting.qre_controlled_discovery_grid_runner --plan-only
```

Verwachte output:

```text
total_combinations: 328
paper_activation_allowed: false
shadow_activation_allowed: false
live_activation_allowed: false
```

## 4. Scan starten

Bij voorkeur chunked:

```bash
RUN_ID="vps-grid-$(date -u +%Y%m%d-%H%M%S)"
OUT="research/controlled_discovery_grid_runs/$RUN_ID"

python -m reporting.qre_controlled_discovery_grid_runner --run --start 1 --end 50 --output-dir "$OUT"
python -m reporting.qre_controlled_discovery_grid_runner --run --start 51 --end 100 --output-dir "$OUT" --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 101 --end 150 --output-dir "$OUT" --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 151 --end 200 --output-dir "$OUT" --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 201 --end 250 --output-dir "$OUT" --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 251 --end 300 --output-dir "$OUT" --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 301 --end 328 --output-dir "$OUT" --resume
```

Volledige one-shot resume is ook mogelijk:

```bash
python -m reporting.qre_controlled_discovery_grid_runner --run --start 1 --end 328 --output-dir "$OUT" --resume
```

## 5. Samenvatting maken

```bash
python -m reporting.qre_controlled_discovery_grid_runner --summarize --output-dir "$OUT"
cat "$OUT/operator_summary.md"
```

## 6. Live volgen

```bash
tail -f "$OUT/combination_results.v1.jsonl"
```

Of periodiek de summary verversen:

```bash
watch -n 10 "python -m reporting.qre_controlled_discovery_grid_runner --summarize --output-dir '$OUT' && cat '$OUT/operator_summary.md'"
```

## 7. Output ophalen

Kijk hier:

```text
research/controlled_discovery_grid_runs/<run_id>/operator_summary.md
research/controlled_discovery_grid_runs/<run_id>/summary_latest.v1.json
research/controlled_discovery_grid_runs/<run_id>/combination_results.v1.jsonl
```

Vanaf Windows:

```powershell
$KEY = "$HOME\.ssh\github_actions_vps_deploy"
$HOSTNAME = "root@23.88.110.92"
$RUN = "<run_id>"

ssh -i $KEY $HOSTNAME "cd /root/trading-agent && cat research/controlled_discovery_grid_runs/$RUN/operator_summary.md"
ssh -i $KEY $HOSTNAME "cd /root/trading-agent && cat research/controlled_discovery_grid_runs/$RUN/summary_latest.v1.json"
```

## 8. Wat de operator moet terugplakken

Plak alleen deze outputs terug:

```text
operator_summary.md
summary_latest.v1.json
eventuele failed/unknown rows
```

## 9. Stopcondities

Stop de VPS-run bij:

```text
paper_activation_allowed true
shadow_activation_allowed true
live_activation_allowed true
broker/risk/execution path touched
frozen contract mutation
unexpected generated file outside output-dir
unknown_execution_error > 20%
runtime crash loop
disk usage risk
```

## 10. Wat deze scan wel/niet bewijst

Wel:

```text
328 per-combination research/validation attempts
outcome distribution
blocker distribution
near-pass candidates
candidate follow-up list
region/preset/asset diagnostics
```

Niet:

```text
real alpha
paper readiness
shadow readiness
live readiness
strategy synthesis approval
capital allocation approval
```
