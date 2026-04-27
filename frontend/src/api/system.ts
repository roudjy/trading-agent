// Read-only system metadata types served by `dashboard/api_system_meta.py`.

export interface SystemFileMeta {
  name: string;
  path: string;
  exists: boolean;
  size_bytes: number | null;
  modified_at_unix: number | null;
}

export interface SystemMetaVersion {
  file_version: string | null;
  git_head: string | null;
  image_tag: string | null;
  host: string | null;
  container: string | null;
  version_file: SystemFileMeta | null;
}

export interface SystemArtifactDirectory {
  path: string;
  files: SystemFileMeta[];
}

export interface SystemArtifactIndex {
  directories: SystemArtifactDirectory[];
  file_count: number;
}

export interface SprintRegistry {
  sprint_id?: string;
  profile?: string;
  state?: string;
  started_at_utc?: string;
  expected_completion_utc?: string;
  target_campaigns?: number;
  max_days?: number;
  [key: string]: unknown;
}

export interface SprintProgress {
  observed_campaigns?: number;
  target_campaigns?: number;
  by_preset?: { name: string; count: number }[];
  by_hypothesis?: { name: string; count: number }[];
  by_outcome?: { name: string; count: number }[];
  [key: string]: unknown;
}

export interface SprintReport {
  outcome?: string;
  finished_at_utc?: string;
  [key: string]: unknown;
}

export interface SystemSprintStatus {
  available: boolean;
  registry: SprintRegistry | null;
  progress: SprintProgress | null;
  report: SprintReport | null;
  registry_file: SystemFileMeta;
  progress_file: SystemFileMeta;
  report_file: SystemFileMeta;
}
