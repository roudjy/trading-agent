import { api } from "../client";
import type { Health, SystemMetaVersion } from "../client";
import type { VersionModel } from "./types";

const DASHBOARD_VERSION = "qre-control-room";

export function buildVersionModel(input: {
  meta: SystemMetaVersion | null;
  health: Health | null;
}): VersionModel {
  const { meta, health } = input;
  const file = meta?.file_version ?? null;
  const backend = health?.version ?? null;
  const dashboard = DASHBOARD_VERSION;
  const driftDetails = [
    { check: "VERSION ↔ backend", ok: !!file && !!backend && file === backend },
  ];
  return {
    fileVersion: file,
    backendVersion: backend,
    dashboardVersion: dashboard,
    gitHead: meta?.git_head ?? null,
    imageTag: meta?.image_tag ?? null,
    host: meta?.host ?? null,
    container: meta?.container ?? null,
    versionFileMtime: meta?.version_file?.modified_at_unix ?? null,
    drift: driftDetails.some((d) => !d.ok),
    driftDetails,
  };
}

export async function loadVersionModel(): Promise<VersionModel> {
  const [meta, health] = await Promise.all([
    api.systemVersion().catch(() => null),
    api.health().catch(() => null),
  ]);
  return buildVersionModel({ meta, health });
}
