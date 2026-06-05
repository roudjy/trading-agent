# QRE Controlled 328 Discovery Grid VPS Runbook

## 1. Doel

Deze run evalueert alle 328 instrument x behavior-preset combinations uit de read-only discovery catalog.
Dit is research evidence generation.
Dit activeert geen paper/shadow/live.

Huidige nuance:
- de planner, chunking, resume en sidecar-only artifacts zijn klaar voor VPS-gebruik;
- directe controlled execution integration is nog deferred;
- de huidige runner markeert dat expliciet in de artifacts in plaats van echte market evidence te faken.

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
python -m reporting.qre_controlled_discovery_grid_runner --run --start 1 --end 50 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001
python -m reporting.qre_controlled_discovery_grid_runner --run --start 51 --end 100 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 101 --end 150 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 151 --end 200 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 201 --end 250 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 251 --end 300 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
python -m reporting.qre_controlled_discovery_grid_runner --run --start 301 --end 328 --output-dir research/controlled_discovery_grid_runs --run-id vps-grid-001 --resume
```

De huidige runner schrijft per chunk sidecar-only artifacts en houdt expliciet bij dat execution integration nog deferred is.

## 5. Samenvatting maken

```bash
python -m reporting.qre_controlled_discovery_grid_analysis --input-dir research/controlled_discovery_grid_runs/vps-grid-001 --write-summary
```

## 6. Output ophalen

Kijk hier:

```text
research/controlled_discovery_grid_runs/<run_id>/operator_summary.md
research/controlled_discovery_grid_runs/<run_id>/summary_latest.v1.json
research/controlled_discovery_grid_runs/<run_id>/combination_results.v1.jsonl
```

## 7. Wat de operator moet terugplakken

Plak alleen deze outputs terug:

```text
operator_summary.md
summary_latest.v1.json
eventuele failed/unknown rows
```

## 8. Stopcondities

Stop de VPS-run bij:

```text
paper_activation_allowed true
shadow_activation_allowed true
live_activation_allowed true
broker/risk/execution path touched
frozen contract mutation
unexpected generated file outside output-dir
unknown error rate > 20%
data coverage failures > 80%
runtime crash loop
```

## 9. Wat deze scan wel/niet bewijst

Wel:

```text
distribution of blockers/outcomes across 328 combinations
which assets/presets deserve follow-up
which failure modes dominate
whether the discovery catalog is useful enough for routing/sampling
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
