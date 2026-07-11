# QRE Offline Dataset Admission Catalog

The offline dataset admission catalog is a static JSON manifest for governed
offline research only. It admits or blocks operator-selected fixture, sample,
or cached datasets before the governed offline runner can use them.

The catalog does not fetch external data, does not require broker, shadow,
paper, or live configuration, and does not grant execution authority.

Each admitted entry must include a source identity, quality status of `passed`,
and a deterministic dataset fingerprint. Blocked and review-required entries
must carry explicit block reasons so the runner can produce a governed blocked
artifact instead of silently treating the dataset as usable.
