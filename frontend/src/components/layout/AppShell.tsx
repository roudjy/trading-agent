import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../../auth";
import { api, type Health } from "../../api/client";
import type { SystemMetaVersion } from "../../api/system";
import type { SystemStatus } from "../pixel/StatusPill";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { Ticker, type TickerItem } from "./Ticker";

interface AppShellProps {
  children: ReactNode;
}

const POLL_MS = 60_000;

export function AppShell({ children }: AppShellProps) {
  const { actor, logout } = useAuth();
  const [health, setHealth] = useState<Health | null>(null);
  const [version, setVersion] = useState<SystemMetaVersion | null>(null);
  const [tickerItems, setTickerItems] = useState<TickerItem[]>([]);

  useEffect(() => {
    let canceled = false;
    async function refresh() {
      try {
        const h = await api.health();
        if (!canceled) setHealth(h);
      } catch {
        if (!canceled) setHealth(null);
      }
      try {
        const v = await api.systemVersion();
        if (!canceled) setVersion(v);
      } catch {
        if (!canceled) setVersion(null);
      }
    }
    void refresh();
    const id = window.setInterval(refresh, POLL_MS);
    return () => {
      canceled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!health) {
      setTickerItems([]);
      return;
    }
    const items: TickerItem[] = [];
    const stamp = new Date().toISOString().slice(11, 19) + "Z";
    items.push({
      t: stamp,
      kind: "tick",
      msg: `service ${health.status} · v${health.version}`,
    });
    if (health.last_run_age_seconds != null) {
      items.push({
        t: stamp,
        kind: "campaign",
        msg: `last run ${Math.round(health.last_run_age_seconds / 60)}m ago`,
      });
    }
    if (health.scheduler_next_fire_utc) {
      items.push({
        t: stamp,
        kind: "deploy",
        msg: `next fire ${new Date(health.scheduler_next_fire_utc).toUTCString()}`,
      });
    }
    setTickerItems(items);
  }, [health]);

  const status: SystemStatus =
    health?.status === "ok" ? "HEALTHY" : health == null ? "IDLE" : "WARNING";

  return (
    <div className="qre-app" data-palette="sky" data-intensity="balanced" data-pixelfont="on">
      <div className="shell">
        <TopBar
          status={status}
          fileVersion={version?.file_version ?? health?.version ?? null}
          gitHead={version?.git_head ?? null}
          uptimeHours={null}
          lastUpdateMin={null}
          lastRunAgeSeconds={health?.last_run_age_seconds ?? null}
        />
        <Sidebar actor={actor} onLogout={() => void logout()} />
        <main className="shell__main">
          <Ticker items={tickerItems} />
          <div style={{ marginTop: 18 }}>{children}</div>
        </main>
      </div>
    </div>
  );
}
