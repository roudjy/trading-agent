export function fmtAge(min: number | null | undefined): string {
  if (min == null) return "—";
  if (min < 1) return `${Math.round(min * 60)}s`;
  if (min < 60) return `${Math.round(min)}m`;
  if (min < 60 * 24) return `${(min / 60).toFixed(1)}h`;
  return `${Math.round(min / (60 * 24))}d`;
}

export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const now = Date.now();
  const diffMin = (now - t) / 60000;
  if (diffMin < 0) return `in ${fmtAge(-diffMin)}`;
  return `${fmtAge(diffMin)} ago`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toISOString().slice(11, 19) + "Z";
}

export function fmtAgeSeconds(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  return fmtAge(seconds / 60);
}
