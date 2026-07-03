# Alpha Discovery Data Truth and VPS Storage

## Canonical Roots

- `data/cache/market/**` stores physical market cache partitions.
- `artifacts/cache/**` remains the canonical artifact root when cache contracts require artifact-backed materialization.
- `generated_research/data_catalog/**` stores census, catalog, reconciliation, and status artifacts.
- `generated_research/alpha_discovery/**` stores alpha-discovery planning, admission, and run artifacts.

## Path Contract

- Active dataset references must use repository-relative paths such as `data/cache/market/...`.
- Machine-specific absolute paths are retained only as historical provenance.
- Logical dataset identity is derived from semantic dataset content, not host path.

## Portable Runtime Expectations

- Windows local root: repository checkout root.
- Linux local root: repository checkout root.
- Container root: mounted repository root with writable `data/cache`, `artifacts/cache`, and `generated_research`.
- VPS persistent volume root: mounted volume backing `data/cache`, `artifacts/cache`, and `generated_research`.

## Writable Roots

- `data/cache/market/**`
- `artifacts/cache/**`
- `generated_research/**`
- `logs/qre_data_cache_manifest/**`
- `logs/qre_data_source_quality_readiness/**`

## Bootstrap and Restart

- Bootstrap begins with a census across physical files, manifests, and historical references.
- Reconciliation rebuilds canonical portable references before any acquisition plan is executed.
- Incremental restarts reuse the existing logical dataset catalog and only plan missing complete intervals.
- Partial ingestion failures remain staged and are not promoted as ready logical datasets.
