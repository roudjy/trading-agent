import { useEffect, useState } from "react";
import { api, PublicArtifactStatus } from "../api/client";

const STALE_REASON_COPY: Record<string, string> = {
  degenerate_run_no_public_write:
    "laatste run eindigde degenerate — publieke artifacts niet overschreven",
  error_no_public_write:
    "laatste run faalde met een onverwachte fout voordat de publieke write klaar was",
  public_write_never_occurred:
    "geen succesvolle publieke write gevonden — dit systeem heeft nog geen resultaten geproduceerd",
};

function formatAge(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "onbekend";
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} uur`;
  const days = Math.round(hours / 24);
  return `${days} dagen`;
}

export function StaleArtifactBanner(): JSX.Element | null {
  const [status, setStatus] = useState<PublicArtifactStatus | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const payload = await api.publicArtifactStatus();
        setStatus(payload);
      } catch {
        // endpoint unavailable — behave as absent (no banner)
        setStatus(null);
      }
    })();
  }, []);

  if (status === null) return null;
  if (status.state !== "valid") return null;
  if (status.public_artifacts_stale !== true) return null;

  const reasonCode = status.stale_reason ?? "";
  const reasonCopy =
    STALE_REASON_COPY[reasonCode] ?? "publieke artifacts zijn mogelijk verouderd";

  const attempted = status.last_attempted_run;
  const write = status.last_public_artifact_write;
  const age = formatAge(status.last_public_write_age_seconds);

  return (
    <div className="banner warn" role="alert" data-testid="stale-artifact-banner">
      <strong>De getoonde publieke research-resultaten zijn niet van de laatste run.</strong>
      <div className="banner-body">
        <div>
          <span className="muted">Reden:</span> {reasonCopy}
          {reasonCode ? <code className="banner-code">{reasonCode}</code> : null}
        </div>
        {attempted ? (
          <div>
            <span className="muted">Laatste run:</span>{" "}
            <code>{attempted.run_id ?? "—"}</code>
            {attempted.failure_stage ? (
              <> — failure stage <code>{attempted.failure_stage}</code></>
            ) : null}
          </div>
        ) : null}
        {write ? (
          <div>
            <span className="muted">Laatste publieke write:</span>{" "}
            <code>{write.run_id ?? "—"}</code>
            {write.written_at_utc ? (
              <> op <code>{write.written_at_utc}</code> ({age} geleden)</>
            ) : null}
          </div>
        ) : null}
        {status.stale_since_utc ? (
          <div>
            <span className="muted">Stale sinds:</span>{" "}
            <code>{status.stale_since_utc}</code>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default StaleArtifactBanner;
