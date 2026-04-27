import { Chip, Coin, Heart, Star } from "../pixel/Glyphs";
import { PixelBadge } from "../pixel/PixelBadge";
import { StatusPill, type SystemStatus } from "../pixel/StatusPill";
import { fmtAge, fmtAgeSeconds } from "../../lib/time";

interface TopBarProps {
  status: SystemStatus;
  fileVersion: string | null;
  gitHead: string | null;
  uptimeHours: number | null;
  lastUpdateMin: number | null;
  lastRunAgeSeconds: number | null;
}

export function TopBar({
  status,
  fileVersion,
  gitHead,
  uptimeHours,
  lastUpdateMin,
  lastRunAgeSeconds,
}: TopBarProps) {
  const updatedLabel =
    lastUpdateMin != null
      ? `UPDATED ${fmtAge(lastUpdateMin)} AGO`
      : lastRunAgeSeconds != null
      ? `LAST RUN ${fmtAgeSeconds(lastRunAgeSeconds)} AGO`
      : "UPDATED —";
  return (
    <header className="shell__topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span className="hop">
          <Coin size={22} />
        </span>
        <div>
          <div
            className="pxd"
            style={{ fontSize: 12, letterSpacing: 1.5, color: "var(--coin)" }}
          >
            QRE · CONTROL ROOM
          </div>
          <div
            className="mono"
            style={{ fontSize: 11, color: "var(--ink-muted)", marginTop: 2 }}
          >
            QUANT RESEARCH ENGINE / DASHBOARD
          </div>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <PixelBadge kind="ink" icon={<Star size={10} />}>
          VER {fileVersion ?? "—"}
        </PixelBadge>
        {gitHead && (
          <PixelBadge kind="info" icon={<Chip size={10} />}>
            GIT {gitHead.slice(0, 7)}
          </PixelBadge>
        )}
        {uptimeHours != null && (
          <PixelBadge kind="mute" icon={<Heart size={10} />}>
            UPTIME {Math.round(uptimeHours)}h
          </PixelBadge>
        )}
        <PixelBadge kind="mute">{updatedLabel}</PixelBadge>
        <StatusPill status={status} />
      </div>
    </header>
  );
}
