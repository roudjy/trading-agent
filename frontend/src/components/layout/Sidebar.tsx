import { NavLink } from "react-router-dom";
import { Arrow, Block, Chip, Coin, Dot, Flag, Heart, Pipe, Skull, Star } from "../pixel/Glyphs";

const NAV_ITEMS = [
  { path: "/", label: "Overview", Icon: Block, end: true },
  { path: "/sprint", label: "Discovery Sprint", Icon: Flag, end: false },
  { path: "/campaigns", label: "Campaigns", Icon: Pipe, end: false },
  { path: "/failures", label: "Failure Modes", Icon: Skull, end: false },
  { path: "/artifacts", label: "Artifacts", Icon: Chip, end: false },
  { path: "/observability", label: "Observability", Icon: Coin, end: false },
  { path: "/health", label: "System Health", Icon: Heart, end: false },
  { path: "/version", label: "Version / Deploy", Icon: Star, end: false },
];

interface SidebarProps {
  actor: string | null;
  onLogout: () => void;
}

export function Sidebar({ actor, onLogout }: SidebarProps) {
  return (
    <aside className="shell__sidebar">
      <div style={{ padding: "6px 8px 12px" }}>
        <div
          className="pxd"
          style={{
            fontSize: 9,
            color: "var(--ink-muted)",
            letterSpacing: 1.5,
            marginBottom: 6,
          }}
        >
          ▸ NAVIGATION
        </div>
      </div>
      <nav>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end}
            className={({ isActive }) =>
              `nav-item ${isActive ? "nav-item--active" : ""}`.trim()
            }
          >
            {({ isActive }) => (
              <>
                <item.Icon size={16} />
                <span>{item.label}</span>
                {isActive && (
                  <span style={{ marginLeft: "auto" }}>
                    <Arrow size={10} dir="right" />
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div style={{ padding: "14px 8px", marginTop: 16 }}>
        <div
          className="pxd"
          style={{
            fontSize: 9,
            color: "var(--ink-muted)",
            letterSpacing: 1.5,
            marginBottom: 10,
          }}
        >
          ▸ LEGEND
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            <Dot color="var(--grass)" /> healthy
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            <Dot color="var(--coin)" /> warning
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            <Dot color="var(--brick)" /> error
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            <Dot color="var(--info)" /> info
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}>
            <Dot color="var(--stone)" /> inactive
          </div>
        </div>
      </div>

      <div style={{ padding: "10px 8px", marginTop: "auto" }}>
        <div
          className="pixel-card"
          style={{ background: "var(--ink)", color: "var(--coin)", padding: "10px 12px" }}
        >
          <div
            className="pxd"
            style={{
              fontSize: 8,
              letterSpacing: 1.5,
              marginBottom: 6,
              color: "var(--coin)",
            }}
          >
            READ-ONLY MODE
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--panel)" }}>
            UI cannot mutate state. Frozen contracts protected.
          </div>
        </div>
        <button
          type="button"
          className="pixel-btn"
          onClick={onLogout}
          style={{ marginTop: 12, width: "100%" }}
        >
          Logout{actor ? ` · ${actor}` : ""}
        </button>
      </div>
    </aside>
  );
}
