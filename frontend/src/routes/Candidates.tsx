import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StaleArtifactBanner } from "../components/StaleArtifactBanner";
import { Chip, Warn } from "../components/pixel/Glyphs";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelSectionHeader } from "../components/pixel/PixelSectionHeader";
import { EmptyStatePanel } from "../components/pixel/EmptyStatePanel";

export function Candidates() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.candidatesLatest();
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "unknown error");
      }
    })();
  }, []);

  if (error) {
    return (
      <EmptyStatePanel
        title="Candidates unavailable"
        message={`Failed to load candidates: ${error}`}
        icon={<Warn size={36} />}
      />
    );
  }

  if (!data) {
    return (
      <EmptyStatePanel
        title="Loading"
        message="Reading candidate artifact..."
        icon={<Chip size={36} />}
      />
    );
  }

  if (data.artifact_state === "missing") {
    return (
      <div>
        <PixelSectionHeader title="Candidate Inspector" icon={<Chip size={20} />} />
        <StaleArtifactBanner />
        <EmptyStatePanel
          title="No Candidates"
          message="No candidate artifacts present. Start a preset and wait for the run to complete."
          icon={<Chip size={36} />}
        />
      </div>
    );
  }

  return (
    <div>
      <PixelSectionHeader title="Candidate Inspector" icon={<Chip size={20} />} />
      <StaleArtifactBanner />
      <PixelCard>
        <div className="pixel-stat-label" style={{ marginBottom: 10 }}>
          run_candidates_latest.v1.json
        </div>
        <pre
          className="mono"
          style={{
            background: "var(--panel-2)",
            padding: 12,
            fontSize: 12,
            maxHeight: "70vh",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      </PixelCard>
    </div>
  );
}
