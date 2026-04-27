import { Fragment, useEffect, useState } from "react";
import { loadCampaignsModel } from "../api/adapters/campaigns";
import type { CampaignsModel } from "../api/adapters/types";
import { Block, Coin, Heart, Pipe, Star, Warn } from "../components/pixel/Glyphs";
import { PixelBadge } from "../components/pixel/PixelBadge";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { StatTile } from "../components/pixel/PixelStat";
import { HBar } from "../components/pixel/HBar";
import { OutcomeBadge, StateBadge } from "../components/pixel/Badges";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";
import { fmtAgo } from "../lib/time";

const STAGES = ["Tick", "Decision", "Spawn", "Run", "Outcome"];

export function Campaigns() {
  const [model, setModel] = useState<CampaignsModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const m = await loadCampaignsModel();
        if (!cancelled) setModel(m);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <EmptyStatePanel
        title="Campaigns unavailable"
        message={`Failed to load campaign artifacts: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }
  if (!model) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading campaign registry..."
        icon={<Pipe size={36} />}
      />
    );
  }
  if (model.rows.length === 0) {
    return (
      <div>
        <PixelSectionHeader title="Campaigns" icon={<Pipe size={20} />} />
        <EmptyStatePanel
          title="No Campaigns Yet"
          message="No campaigns appear in the latest registry artifact."
          icon={<Pipe size={36} />}
        />
      </div>
    );
  }

  const runtimePerPreset = model.runtimePerPreset;
  const avgRuntime =
    runtimePerPreset.length > 0
      ? (
          runtimePerPreset.reduce((s, x) => s + x.avg_min, 0) /
          runtimePerPreset.length
        ).toFixed(1)
      : "—";

  return (
    <div>
      <PixelSectionHeader
        title="Campaigns"
        icon={<Pipe size={20} />}
        right={
          <>
            <PixelBadge kind="ok">{model.completed24h ?? 0} complete</PixelBadge>
            <PixelBadge kind="err">{model.failed24h ?? 0} failed</PixelBadge>
            <PixelBadge kind="mute">{model.canceled24h ?? 0} canceled</PixelBadge>
          </>
        }
      />

      <PixelCard variant="ink" style={{ marginBottom: 18 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            justifyContent: "space-between",
            flexWrap: "wrap",
          }}
        >
          {STAGES.map((s, i) => (
            <Fragment key={s}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 22,
                    height: 22,
                    background: "var(--coin)",
                    color: "var(--ink)",
                    textAlign: "center",
                    lineHeight: "22px",
                    boxShadow:
                      "0 -2px 0 0 var(--coin-dark), 0 2px 0 0 var(--coin-dark), -2px 0 0 0 var(--coin-dark), 2px 0 0 0 var(--coin-dark)",
                  }}
                  className="pxd"
                >
                  {i + 1}
                </span>
                <span
                  className="pxd"
                  style={{
                    color: "var(--coin)",
                    fontSize: 11,
                    letterSpacing: 1,
                  }}
                >
                  {s.toUpperCase()}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <span style={{ color: "var(--coin)", fontSize: 22 }}>—▸</span>
              )}
            </Fragment>
          ))}
        </div>
      </PixelCard>

      <div className="grid-cards" style={{ marginBottom: 18 }}>
        <StatTile
          label="Queue Depth"
          value={model.queueDepth ?? "—"}
          sub="campaigns waiting"
          icon={<Block size={20} />}
        />
        <StatTile
          label="Workers"
          value={
            model.workersBusy != null && model.workersTotal != null
              ? `${model.workersBusy}/${model.workersTotal}`
              : "—"
          }
          sub="busy / total"
          icon={<Heart size={20} />}
        />
        <StatTile
          label="Avg Runtime"
          value={`${avgRuntime}${avgRuntime === "—" ? "" : "m"}`}
          sub="across reported presets"
          icon={<Coin size={20} />}
        />
        <StatTile
          label="Last 10"
          value={model.rows.length}
          sub="campaigns shown below"
          icon={<Star size={20} />}
        />
      </div>

      {runtimePerPreset.length > 0 && (
        <div className="grid-2" style={{ marginBottom: 18 }}>
          <PixelCard>
            <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
              RUNTIME PER PRESET
            </div>
            {runtimePerPreset.map((r) => (
              <HBar
                key={r.name}
                label={r.name}
                value={r.avg_min}
                max={Math.max(...runtimePerPreset.map((x) => x.avg_min), 1)}
                color="info"
                sub="m"
              />
            ))}
          </PixelCard>
          <PixelCard>
            <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
              OUTCOME MIX · LAST {model.rows.length}
            </div>
            {(() => {
              const counts: Record<string, number> = {};
              model.rows.forEach((c) => {
                counts[c.outcome] = (counts[c.outcome] ?? 0) + 1;
              });
              const max = Math.max(...Object.values(counts), 1);
              const color: Record<string, "" | "coin" | "info" | "stone" | "grass"> = {
                no_signal: "info",
                near_pass: "grass",
                failed: "",
                canceled: "stone",
                running: "coin",
              };
              return Object.entries(counts).map(([k, v]) => (
                <HBar key={k} label={k} value={v} max={max} color={color[k] ?? ""} />
              ));
            })()}
          </PixelCard>
        </div>
      )}

      <PixelCard padding={false}>
        <div
          style={{
            padding: "14px 18px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "4px solid var(--ink)",
          }}
        >
          <span className="pxd" style={{ fontSize: 11 }}>
            LAST {model.rows.length} CAMPAIGNS
          </span>
          <span className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            click row to expand
          </span>
        </div>
        <table className="pixel-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Preset</th>
              <th>Hyp</th>
              <th>Asset/TF</th>
              <th>State</th>
              <th>Outcome</th>
              <th>Runtime</th>
              <th>Finished</th>
            </tr>
          </thead>
          <tbody>
            {model.rows.map((c) => (
              <Fragment key={c.campaignId}>
                <tr
                  onClick={() =>
                    setExpanded(expanded === c.campaignId ? null : c.campaignId)
                  }
                  style={{ cursor: "pointer" }}
                >
                  <td className="mono" style={{ fontSize: 13 }}>
                    {c.campaignId}
                  </td>
                  <td>
                    {c.preset ? (
                      <PixelBadge kind="ink">{c.preset}</PixelBadge>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="mono" style={{ fontSize: 13 }}>
                    {c.hypothesisId ?? "—"}
                  </td>
                  <td className="mono" style={{ fontSize: 13 }}>
                    {c.asset ?? "—"} · {c.timeframe ?? "—"}
                  </td>
                  <td>
                    <StateBadge state={c.state} />
                  </td>
                  <td>
                    <OutcomeBadge outcome={c.outcome} />
                  </td>
                  <td className="mono" style={{ fontSize: 13 }}>
                    {c.runtimeMin != null ? `${c.runtimeMin}m` : "—"}
                  </td>
                  <td
                    className="mono"
                    style={{ fontSize: 13, color: "var(--ink-muted)" }}
                  >
                    {c.finishedAtUtc ? (
                      fmtAgo(c.finishedAtUtc)
                    ) : (
                      <span className="blink">running…</span>
                    )}
                  </td>
                </tr>
                {expanded === c.campaignId && (
                  <tr>
                    <td colSpan={8} style={{ background: "var(--panel-2)" }}>
                      <div
                        style={{
                          padding: "8px 4px",
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                          gap: 12,
                        }}
                      >
                        <div>
                          <div className="pixel-stat-label">FAMILY</div>
                          <span className="mono">{c.family ?? "—"}</span>
                        </div>
                        <div>
                          <div className="pixel-stat-label">CAMPAIGN TYPE</div>
                          <span className="mono">{c.campaignType ?? "—"}</span>
                        </div>
                        <div>
                          <div className="pixel-stat-label">STARTED</div>
                          <span className="mono">{fmtAgo(c.startedAtUtc)}</span>
                        </div>
                        <div>
                          <div className="pixel-stat-label">FINISHED</div>
                          <span className="mono">{fmtAgo(c.finishedAtUtc)}</span>
                        </div>
                        {c.failureReason && (
                          <div>
                            <div className="pixel-stat-label">FAILURE</div>
                            <PixelBadge kind="err">{c.failureReason}</PixelBadge>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </PixelCard>
    </div>
  );
}
