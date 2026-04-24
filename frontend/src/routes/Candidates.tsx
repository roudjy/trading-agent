import { useEffect, useState } from "react";
import { api } from "../api/client";
import { StaleArtifactBanner } from "../components/StaleArtifactBanner";

export function Candidates() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await api.candidatesLatest();
        setData(res);
      } catch (e) {
        setError(e instanceof Error ? e.message : "onbekende fout");
      }
    })();
  }, []);

  if (error) {
    return (
      <>
        <h2 style={{ marginTop: 0 }}>Candidate inspector</h2>
        <StaleArtifactBanner />
        <div className="card danger">Fout: {error}</div>
      </>
    );
  }

  if (!data) {
    return (
      <>
        <h2 style={{ marginTop: 0 }}>Candidate inspector</h2>
        <StaleArtifactBanner />
        <div className="muted">Laden…</div>
      </>
    );
  }

  if (data.artifact_state === "missing") {
    return (
      <>
        <h2 style={{ marginTop: 0 }}>Candidate inspector</h2>
        <StaleArtifactBanner />
        <div className="card muted">
          Geen candidate artifacts aanwezig. Start een preset en wacht tot de
          run klaar is.
        </div>
      </>
    );
  }

  return (
    <>
      <h2 style={{ marginTop: 0 }}>Candidate inspector</h2>
      <StaleArtifactBanner />
      <section className="card">
        <h2>run_candidates_latest.v1.json</h2>
        <pre className="markdown">{JSON.stringify(data, null, 2)}</pre>
      </section>
    </>
  );
}
