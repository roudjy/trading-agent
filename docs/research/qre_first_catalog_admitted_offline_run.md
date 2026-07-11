# QRE First Catalog-Admitted Offline Run

The first catalog-admitted offline run command is a convenience wrapper around
the governed offline research runner. It requires an offline dataset catalog,
hypothesis id, dataset id, and caller-provided output directory.

The workflow validates the catalog entry, runs or blocks the governed offline
runner, writes artifacts only under the requested output directory, and emits a
small operator summary. Fixture and sample catalog entries are not production
empirical evidence and do not imply profitability.

Example:

```powershell
python tools/qre_first_catalog_offline_run.py --catalog docs/research/qre_offline_dataset_catalog.v1.example.json --dataset-id qre_fixture_dataset --hypothesis-id qre_fixture_hypothesis --output-dir tmp\qre_first_catalog_run --run-id qre_first_catalog_run --json
```
