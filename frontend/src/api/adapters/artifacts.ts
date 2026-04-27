import { api } from "../client";
import type {
  PublicArtifactStatus,
  SystemArtifactIndex,
  SystemFileMeta,
} from "../client";
import type { ArtifactRow, ArtifactsModel } from "./types";

const FRESH_THRESHOLD_MIN = 4 * 60;

function ageMinutes(file: SystemFileMeta): number | null {
  if (!file.exists || file.modified_at_unix == null) return null;
  return (Date.now() / 1000 - file.modified_at_unix) / 60;
}

function classify(age: number | null, exists: boolean): "fresh" | "stale" | "missing" {
  if (!exists) return "missing";
  if (age == null) return "missing";
  return age < FRESH_THRESHOLD_MIN ? "fresh" : "stale";
}

function rowFromMeta(file: SystemFileMeta, schema: string | null = null): ArtifactRow {
  const age = ageMinutes(file);
  return {
    name: file.path || file.name,
    exists: file.exists,
    ageMin: age,
    schema,
    state: classify(age, file.exists),
    note: null,
    sizeBytes: file.size_bytes,
  };
}

export function buildArtifactsModel(input: {
  index: SystemArtifactIndex | null;
  publicStatus: PublicArtifactStatus | null;
}): ArtifactsModel {
  const { index, publicStatus } = input;
  const rows: ArtifactRow[] = [];
  if (index) {
    for (const dir of index.directories ?? []) {
      for (const file of dir.files ?? []) {
        rows.push(rowFromMeta(file));
      }
    }
  }
  // promote canonical contracts to top
  const canonical = ["research_latest.json", "strategy_matrix.csv"];
  rows.sort((a, b) => {
    const aRank = canonical.findIndex((n) => a.name.endsWith(n));
    const bRank = canonical.findIndex((n) => b.name.endsWith(n));
    if (aRank !== -1 || bRank !== -1) {
      return (aRank === -1 ? 99 : aRank) - (bRank === -1 ? 99 : bRank);
    }
    return a.name.localeCompare(b.name);
  });
  // mark public-status reported staleness on the canonical row
  if (publicStatus) {
    const canonicalRow = rows.find((r) => r.name.endsWith("research_latest.json"));
    if (canonicalRow && publicStatus.public_artifacts_stale === true) {
      canonicalRow.state = "stale";
      canonicalRow.note = publicStatus.stale_reason ?? "stale";
    }
  }
  return {
    rows,
    publicArtifactsStale: publicStatus?.public_artifacts_stale ?? null,
    staleReason: publicStatus?.stale_reason ?? null,
    totalFresh: rows.filter((r) => r.state === "fresh").length,
    totalStale: rows.filter((r) => r.state === "stale").length,
    totalMissing: rows.filter((r) => r.state === "missing").length,
  };
}

export async function loadArtifactsModel(): Promise<ArtifactsModel> {
  const [index, publicStatus] = await Promise.all([
    api.systemArtifactIndex().catch(() => null),
    api.publicArtifactStatus().catch(() => null),
  ]);
  return buildArtifactsModel({ index, publicStatus });
}
