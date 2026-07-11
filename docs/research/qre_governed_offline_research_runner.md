# QRE Governed Offline Research Runner

The governed offline research runner is an operator-invoked workflow that
orchestrates one hypothesis and one dataset boundary through:

1. single dataset governed offline replay
2. multi-window evidence closure
3. governed offline artifact persistence
4. research memory feedback
5. operator trust review

The CLI requires an explicit output directory and writes only inside that
directory. It does not fetch external data, run production research, mutate
frozen outputs, or require broker, shadow, paper, or live configuration.

Example:

```powershell
python tools/qre_governed_offline_research_run.py --hypothesis-id qre_fixture_hypothesis --dataset-id qre_fixture_dataset --output-dir tmp\qre_runner_smoke --run-id qre_runner_smoke --source-mode offline_fixture --json
```

The final payload is machine-readable and explicitly denies strategy synthesis,
shadow, paper, live, broker, risk, order, and capital-allocation authority.
