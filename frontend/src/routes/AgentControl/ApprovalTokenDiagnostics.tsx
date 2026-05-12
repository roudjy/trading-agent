/**
 * AgentControlApprovalTokenDiagnostics
 * ------------------------------------
 *
 * N4c — read-only diagnostic surface over the already-wired N4b
 * approval-token runtime gate.
 *
 *   * Shows token-gate status (configured / unconfigured /
 *     current_kid / step5 invariants).
 *   * Mints a sample diagnostic token from bounded operator-typed
 *     fields (intent, event_id, evidence_hash).
 *   * Verifies the minted token immediately (expected outcome:
 *     ``ok``).
 *   * Replays the same verify call (expected outcome:
 *     ``replay_detected`` — backend returns HTTP 400 + the
 *     closed-vocab outcome envelope).
 *   * Sends a deliberate binding-mismatch verify with a drifted
 *     ``expected_event_id`` (expected outcome:
 *     ``binding_mismatch`` — also HTTP 400 + outcome envelope).
 *   * Discards the in-state token so the operator can run a
 *     fresh diagnostic cycle.
 *
 * Hard guarantees enforced by the unit tests:
 *
 *   * **Claim-only**: the surface contains no approve / reject /
 *     merge / deploy / execute button or action verb. Token
 *     verification performs no underlying action.
 *   * **No persistence**: the minted token lives in a single
 *     React ``useState`` cell. The component never writes to
 *     ``localStorage``, ``sessionStorage``, ``document.cookie``,
 *     the URL (no ``pushState`` / ``replaceState``), the
 *     service-worker cache, or ``navigator.sendBeacon``. The token
 *     bytes never appear in the rendered DOM.
 *   * **No console leakage**: the token bytes never appear in
 *     ``console.log`` / ``warn`` / ``error`` output.
 *   * **Endpoint isolation**: every fetch from this surface goes
 *     to ``/api/agent-control/approval-token/(status|mint|verify)``
 *     only. No merge-recommendation, mobile-inbox, merge-execution,
 *     deploy, or push endpoint is contacted.
 *   * **Bounded inputs**: ``event_id`` is sanitised to charset
 *     ``[A-Za-z0-9_-]`` and truncated to 64 chars before any
 *     fetch; ``evidence_hash`` similarly truncated to 128 chars.
 *     ``intent`` is constrained to the closed N4b token-intent
 *     vocabulary.
 *   * **Verify body shape**: every verify request carries
 *     ``token`` + ``expected_intent`` + ``expected_event_id`` +
 *     ``expected_evidence_hash``, mirroring the operator's
 *     Phase B VPS smoke contract. The backend currently ignores
 *     ``expected_intent`` (intent is bound by signature), but the
 *     diagnostic UI sends it verbatim so the contract is forward-
 *     compatible if the backend ever validates it.
 *   * **Banner always rendered**: "Diagnostic only. Token
 *     verification is claim-only and performs no approve, merge,
 *     deploy, or execution action."
 *   * **Re-affirms re-auth requirement**: a final reminder that
 *     approval still requires re-authentication in the PWA, never
 *     a notification tap.
 *
 * The destination of the diagnostic — i.e. *what the operator
 * does with a verified token outside this surface* — is N5b
 * territory and is not implemented in this stage.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  agentControlApi,
  type AgentControlApprovalTokenMintResponse,
  type AgentControlApprovalTokenStatus,
  type AgentControlApprovalTokenVerifyResponse,
} from "../../api/agent_control";

// ---------------------------------------------------------------------------
// Closed-vocab + bounding constants
// ---------------------------------------------------------------------------

//: Maximum length of the operator-supplied ``event_id`` before
//: truncation. Matches the bound used in the N3b inbox detail
//: route (defense in depth at every UI boundary).
const MAX_EVENT_ID_LEN = 64;

//: Maximum length of the operator-supplied ``evidence_hash``
//: before truncation. The actual hash is typically 64 hex chars
//: but the diagnostic accepts any bounded string.
const MAX_EVIDENCE_HASH_LEN = 128;

//: Closed N4b token-intent vocabulary. Matches
//: ``reporting.approval_token_gate.TOKEN_INTENTS``.
const TOKEN_INTENTS = [
  "mobile_approval_dispatch",
  "mobile_review_dispatch",
] as const;
type TokenIntent = (typeof TOKEN_INTENTS)[number];

const DEFAULT_INTENT: TokenIntent = "mobile_approval_dispatch";
const DEFAULT_EVENT_ID = "evt_diagnostic_001";
const DEFAULT_EVIDENCE_HASH = "diag_evidence_001";

const READ_ONLY_BANNER =
  "Diagnostic only. Token verification is claim-only and performs no approve, merge, deploy, or execution action.";

// ---------------------------------------------------------------------------
// Bounded-input helpers
// ---------------------------------------------------------------------------

function boundedEventId(raw: string): string {
  const safe = raw.trim().replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_EVENT_ID_LEN);
}

function boundedEvidenceHash(raw: string): string {
  const safe = raw.trim().replace(/[^A-Za-z0-9_\-]/g, "");
  return safe.slice(0, MAX_EVIDENCE_HASH_LEN);
}

function isTokenIntent(value: string): value is TokenIntent {
  return (TOKEN_INTENTS as readonly string[]).includes(value);
}

// ---------------------------------------------------------------------------
// State shapes
// ---------------------------------------------------------------------------

type StatusState =
  | { phase: "loading" }
  | { phase: "ok"; envelope: AgentControlApprovalTokenStatus }
  | { phase: "unauthenticated" }
  | { phase: "unconfigured"; reason: string }
  | { phase: "error"; reason: string };

//: Minted-token envelope plus the bindings the operator used at
//: mint time. The raw token string is held here in memory but
//: never rendered into the DOM, never logged, never persisted.
type MintedTokenState = {
  envelope: AgentControlApprovalTokenMintResponse;
  intent: TokenIntent;
  event_id: string;
  evidence_hash: string;
};

//: Verify-result history entry. Tagged with the kind of verify
//: that produced it so the UI can label outcomes accurately.
type VerifyKind = "verify" | "replay" | "binding_mismatch";
type VerifyEntry = {
  kind: VerifyKind;
  envelope: AgentControlApprovalTokenVerifyResponse;
  expected_event_id: string;
  at_iso: string;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ApprovalTokenDiagnostics() {
  const [status, setStatus] = useState<StatusState>({ phase: "loading" });

  const [intent, setIntent] = useState<TokenIntent>(DEFAULT_INTENT);
  const [eventIdInput, setEventIdInput] = useState<string>(DEFAULT_EVENT_ID);
  const [evidenceHashInput, setEvidenceHashInput] = useState<string>(
    DEFAULT_EVIDENCE_HASH,
  );

  const [minted, setMinted] = useState<MintedTokenState | null>(null);
  const [mintError, setMintError] = useState<string | null>(null);
  const [verifyHistory, setVerifyHistory] = useState<VerifyEntry[]>([]);

  const [busy, setBusy] = useState<boolean>(false);

  const refreshStatus = useCallback(async () => {
    setStatus({ phase: "loading" });
    const env = await agentControlApi.approvalTokenStatus();
    if (env.status === "ok") {
      if (env.is_configured === false) {
        setStatus({
          phase: "unconfigured",
          reason: "is_configured=false",
        });
        return;
      }
      setStatus({ phase: "ok", envelope: env });
      return;
    }
    if (env.error === "operator_session_required") {
      setStatus({ phase: "unauthenticated" });
      return;
    }
    if (env.error === "configuration_missing") {
      setStatus({ phase: "unconfigured", reason: "configuration_missing" });
      return;
    }
    setStatus({
      phase: "error",
      reason: env.error || env.reason || "unknown_error",
    });
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const handleMint = useCallback(async () => {
    setBusy(true);
    setMintError(null);
    const eventId = boundedEventId(eventIdInput);
    const evidenceHash = boundedEvidenceHash(evidenceHashInput);
    if (!eventId || !evidenceHash) {
      setMintError("event_id and evidence_hash must be non-empty");
      setBusy(false);
      return;
    }
    const env = await agentControlApi.approvalTokenMint({
      intent,
      event_id: eventId,
      evidence_hash: evidenceHash,
    });
    if (env.status === "ok" && typeof env.token === "string" && env.token) {
      setMinted({
        envelope: env,
        intent,
        event_id: eventId,
        evidence_hash: evidenceHash,
      });
      setVerifyHistory([]);
    } else {
      setMinted(null);
      setMintError(
        env.error ||
          env.reason ||
          env.status ||
          "mint_failed",
      );
    }
    setBusy(false);
  }, [intent, eventIdInput, evidenceHashInput]);

  const runVerify = useCallback(
    async (kind: VerifyKind) => {
      if (!minted) return;
      setBusy(true);
      const expectedEventId =
        kind === "binding_mismatch"
          ? boundedEventId(minted.event_id + "_drift")
          : minted.event_id;
      const env = await agentControlApi.approvalTokenVerify({
        token: minted.envelope.token as string,
        expected_intent: minted.intent,
        expected_event_id: expectedEventId,
        expected_evidence_hash: minted.evidence_hash,
      });
      setVerifyHistory((prev) => [
        ...prev,
        {
          kind,
          envelope: env,
          expected_event_id: expectedEventId,
          at_iso: new Date().toISOString(),
        },
      ]);
      setBusy(false);
    },
    [minted],
  );

  const handleDiscardToken = useCallback(() => {
    setMinted(null);
    setVerifyHistory([]);
    setMintError(null);
  }, []);

  return (
    <main
      data-testid="approval-token-diagnostics-root"
      style={{
        padding: "1.25rem",
        maxWidth: "720px",
        margin: "0 auto",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <h1 style={{ fontSize: "1.4rem", margin: "0 0 0.75rem 0" }}>
        Approval Token Diagnostics
      </h1>
      <div
        data-testid="approval-token-diagnostics-banner"
        style={{
          margin: "0 0 0.85rem 0",
          padding: "0.55rem 0.7rem",
          borderRadius: "0.4rem",
          background: "rgba(0,0,0,0.05)",
          fontSize: "0.85rem",
          lineHeight: 1.4,
        }}
      >
        {READ_ONLY_BANNER}
      </div>

      <StatusPanel state={status} onRefresh={refreshStatus} />

      <section
        data-testid="approval-token-diagnostics-mint-section"
        style={{
          marginTop: "1.1rem",
          padding: "0.75rem",
          border: "1px solid rgba(0,0,0,0.08)",
          borderRadius: "0.5rem",
          background: "rgba(0,0,0,0.02)",
        }}
      >
        <h2 style={{ fontSize: "1.0rem", margin: "0 0 0.5rem 0" }}>
          Diagnostic mint
        </h2>
        <p
          data-testid="approval-token-diagnostics-mint-explainer"
          style={{
            margin: "0 0 0.6rem 0",
            fontSize: "0.85rem",
            color: "rgba(0,0,0,0.7)",
          }}
        >
          Mint a short-TTL diagnostic token with bounded operator-supplied
          bindings. The minted token is held in component state only and
          is never persisted, never copied to the clipboard, never written
          to the URL.
        </p>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            columnGap: "0.6rem",
            rowGap: "0.45rem",
            alignItems: "center",
            fontSize: "0.85rem",
          }}
        >
          <label htmlFor="atd-intent">intent</label>
          <select
            id="atd-intent"
            data-testid="approval-token-diagnostics-intent-select"
            value={intent}
            disabled={busy || minted !== null}
            onChange={(e) => {
              const v = e.target.value;
              if (isTokenIntent(v)) setIntent(v);
            }}
            style={{ padding: "0.35rem 0.45rem" }}
          >
            {TOKEN_INTENTS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <label htmlFor="atd-event-id">event_id</label>
          <input
            id="atd-event-id"
            data-testid="approval-token-diagnostics-event-id-input"
            value={eventIdInput}
            disabled={busy || minted !== null}
            onChange={(e) => setEventIdInput(e.target.value)}
            maxLength={MAX_EVENT_ID_LEN}
            style={{ padding: "0.35rem 0.45rem" }}
          />
          <label htmlFor="atd-evidence-hash">evidence_hash</label>
          <input
            id="atd-evidence-hash"
            data-testid="approval-token-diagnostics-evidence-hash-input"
            value={evidenceHashInput}
            disabled={busy || minted !== null}
            onChange={(e) => setEvidenceHashInput(e.target.value)}
            maxLength={MAX_EVIDENCE_HASH_LEN}
            style={{ padding: "0.35rem 0.45rem" }}
          />
        </div>
        <div style={{ marginTop: "0.7rem" }}>
          <button
            type="button"
            data-testid="approval-token-diagnostics-mint-button"
            disabled={busy || minted !== null}
            onClick={() => void handleMint()}
            style={{
              padding: "0.4rem 0.85rem",
              fontSize: "0.85rem",
              cursor: minted !== null ? "not-allowed" : "pointer",
            }}
          >
            Mint diagnostic token
          </button>
        </div>
        {mintError ? (
          <p
            data-testid="approval-token-diagnostics-mint-error"
            style={{
              marginTop: "0.55rem",
              fontSize: "0.8rem",
              color: "#a4232f",
            }}
          >
            mint failed: {mintError}
          </p>
        ) : null}
      </section>

      {minted ? (
        <MintedTokenPanel
          minted={minted}
          busy={busy}
          onVerify={() => void runVerify("verify")}
          onReplay={() => void runVerify("replay")}
          onBindingMismatch={() => void runVerify("binding_mismatch")}
          onDiscard={handleDiscardToken}
        />
      ) : null}

      {verifyHistory.length > 0 ? (
        <VerifyHistoryPanel entries={verifyHistory} />
      ) : null}

      <p
        data-testid="approval-token-diagnostics-reauth-reminder"
        style={{
          margin: "1.1rem 0 0 0",
          lineHeight: 1.45,
          fontSize: "0.85rem",
          color: "rgba(0,0,0,0.7)",
        }}
      >
        Approval still requires re-authentication in the PWA, never a
        notification tap. Token verification is claim-only and produces
        no underlying action.
      </p>

      <p style={{ margin: "1rem 0 0 0" }}>
        <Link
          to="/agent-control"
          data-testid="approval-token-diagnostics-back-link"
          style={{ color: "var(--ink, #1a73e8)" }}
        >
          Back to agent control
        </Link>
      </p>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Status panel
// ---------------------------------------------------------------------------

function StatusPanel({
  state,
  onRefresh,
}: {
  state: StatusState;
  onRefresh: () => void | Promise<void>;
}) {
  return (
    <section
      data-testid="approval-token-diagnostics-status-section"
      style={{
        marginTop: "0.5rem",
        padding: "0.75rem",
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: "0.5rem",
        background: "rgba(0,0,0,0.02)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "0.5rem",
        }}
      >
        <h2 style={{ fontSize: "1.0rem", margin: 0 }}>Status</h2>
        <button
          type="button"
          data-testid="approval-token-diagnostics-status-refresh"
          onClick={() => void onRefresh()}
          style={{
            padding: "0.3rem 0.65rem",
            fontSize: "0.8rem",
            cursor: "pointer",
          }}
        >
          Refresh status
        </button>
      </div>

      {state.phase === "loading" ? (
        <p
          data-testid="approval-token-diagnostics-status-loading"
          style={{ marginTop: "0.55rem", fontSize: "0.85rem" }}
        >
          Loading status…
        </p>
      ) : null}

      {state.phase === "unauthenticated" ? (
        <p
          data-testid="approval-token-diagnostics-status-unauthenticated"
          style={{ marginTop: "0.55rem", fontSize: "0.85rem" }}
        >
          Operator session required. Re-authenticate at{" "}
          <Link
            to="/login?next=/agent-control/approval-token-diagnostics"
            style={{ color: "var(--ink, #1a73e8)" }}
          >
            /login
          </Link>
          .
        </p>
      ) : null}

      {state.phase === "unconfigured" ? (
        <p
          data-testid="approval-token-diagnostics-status-unconfigured"
          style={{ marginTop: "0.55rem", fontSize: "0.85rem" }}
        >
          Runtime not configured ({state.reason}). The operator must
          export <code>ADE_APPROVAL_TOKEN_HMAC_SECRET</code> on the VPS
          per <code>docs/governance/n4b_runtime_activation.md</code>.
        </p>
      ) : null}

      {state.phase === "error" ? (
        <p
          data-testid="approval-token-diagnostics-status-error"
          style={{ marginTop: "0.55rem", fontSize: "0.85rem" }}
        >
          Status fetch error: {state.reason}
        </p>
      ) : null}

      {state.phase === "ok" ? (
        <dl
          data-testid="approval-token-diagnostics-status-fields"
          style={{
            marginTop: "0.55rem",
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            columnGap: "0.6rem",
            rowGap: "0.25rem",
            fontSize: "0.85rem",
          }}
        >
          <dt>is_configured</dt>
          <dd data-testid="approval-token-diagnostics-status-is-configured">
            {state.envelope.is_configured === true ? "true" : "false"}
          </dd>
          <dt>current_kid</dt>
          <dd data-testid="approval-token-diagnostics-status-current-kid">
            <code>{state.envelope.current_kid || "—"}</code>
          </dd>
          <dt>step5_implementation_allowed</dt>
          <dd
            data-testid="approval-token-diagnostics-status-step5-allowed"
          >
            {String(state.envelope.step5_implementation_allowed ?? false)}
          </dd>
          <dt>step5_enabled_substage</dt>
          <dd
            data-testid="approval-token-diagnostics-status-step5-substage"
          >
            <code>{state.envelope.step5_enabled_substage || "—"}</code>
          </dd>
        </dl>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Minted-token panel
//
// Renders only the closed-envelope scalars. The raw token byte string
// is intentionally NOT rendered — the test pins its absence from the
// DOM. The operator can inspect it via the browser network tab if they
// truly need to; the surface stays minimal.
// ---------------------------------------------------------------------------

function MintedTokenPanel({
  minted,
  busy,
  onVerify,
  onReplay,
  onBindingMismatch,
  onDiscard,
}: {
  minted: MintedTokenState;
  busy: boolean;
  onVerify: () => void;
  onReplay: () => void;
  onBindingMismatch: () => void;
  onDiscard: () => void;
}) {
  const env = minted.envelope;
  return (
    <section
      data-testid="approval-token-diagnostics-minted-section"
      style={{
        marginTop: "1.1rem",
        padding: "0.75rem",
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: "0.5rem",
        background: "rgba(0,0,0,0.02)",
      }}
    >
      <h2 style={{ fontSize: "1.0rem", margin: "0 0 0.5rem 0" }}>
        Minted diagnostic token (in-memory only)
      </h2>
      <p
        style={{
          margin: "0 0 0.55rem 0",
          fontSize: "0.8rem",
          color: "rgba(0,0,0,0.6)",
        }}
      >
        The raw token bytes are not rendered. Only the closed-envelope
        scalars are displayed for diagnostic confirmation.
      </p>
      <dl
        data-testid="approval-token-diagnostics-minted-fields"
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          columnGap: "0.6rem",
          rowGap: "0.25rem",
          fontSize: "0.85rem",
          margin: 0,
        }}
      >
        <dt>kid</dt>
        <dd data-testid="approval-token-diagnostics-minted-kid">
          <code>{env.kid || "—"}</code>
        </dd>
        <dt>intent</dt>
        <dd data-testid="approval-token-diagnostics-minted-intent">
          <code>{env.intent || minted.intent}</code>
        </dd>
        <dt>event_id</dt>
        <dd data-testid="approval-token-diagnostics-minted-event-id">
          <code>{env.event_id || minted.event_id}</code>
        </dd>
        <dt>issued_at_utc</dt>
        <dd data-testid="approval-token-diagnostics-minted-issued-at">
          <code>{env.issued_at_utc || "—"}</code>
        </dd>
        <dt>expires_at_utc</dt>
        <dd data-testid="approval-token-diagnostics-minted-expires-at">
          <code>{env.expires_at_utc || "—"}</code>
        </dd>
      </dl>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.45rem",
          marginTop: "0.7rem",
        }}
      >
        <button
          type="button"
          data-testid="approval-token-diagnostics-verify-button"
          disabled={busy}
          onClick={onVerify}
          style={{
            padding: "0.4rem 0.85rem",
            fontSize: "0.85rem",
            cursor: "pointer",
          }}
        >
          Verify token
        </button>
        <button
          type="button"
          data-testid="approval-token-diagnostics-replay-button"
          disabled={busy}
          onClick={onReplay}
          style={{
            padding: "0.4rem 0.85rem",
            fontSize: "0.85rem",
            cursor: "pointer",
          }}
        >
          Replay verify (expect replay_detected)
        </button>
        <button
          type="button"
          data-testid="approval-token-diagnostics-binding-mismatch-button"
          disabled={busy}
          onClick={onBindingMismatch}
          style={{
            padding: "0.4rem 0.85rem",
            fontSize: "0.85rem",
            cursor: "pointer",
          }}
        >
          Verify with drifted event_id (expect binding_mismatch)
        </button>
        <button
          type="button"
          data-testid="approval-token-diagnostics-discard-button"
          disabled={busy}
          onClick={onDiscard}
          style={{
            padding: "0.4rem 0.85rem",
            fontSize: "0.85rem",
            cursor: "pointer",
          }}
        >
          Discard token
        </button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Verify-history panel
// ---------------------------------------------------------------------------

function VerifyHistoryPanel({ entries }: { entries: VerifyEntry[] }) {
  return (
    <section
      data-testid="approval-token-diagnostics-verify-history"
      style={{
        marginTop: "1.1rem",
        padding: "0.75rem",
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: "0.5rem",
        background: "rgba(0,0,0,0.02)",
      }}
    >
      <h2 style={{ fontSize: "1.0rem", margin: "0 0 0.5rem 0" }}>
        Verify history (this session only)
      </h2>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
          fontSize: "0.85rem",
        }}
      >
        {entries.map((e, idx) => {
          const outcome = e.envelope.outcome || "—";
          const status = e.envelope.status || "—";
          const reason = e.envelope.reason || "";
          return (
            <li
              key={`${e.kind}-${idx}`}
              data-testid={`approval-token-diagnostics-verify-entry-${idx}`}
              style={{
                padding: "0.5rem 0.6rem",
                borderRadius: "0.4rem",
                background: "rgba(0,0,0,0.03)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "0.5rem",
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: "0.8rem",
                  color: "rgba(0,0,0,0.7)",
                  marginBottom: "0.25rem",
                }}
              >
                <span data-testid={`approval-token-diagnostics-verify-entry-${idx}-kind`}>
                  {e.kind}
                </span>
                <span>{e.at_iso}</span>
              </div>
              <div
                data-testid={`approval-token-diagnostics-verify-entry-${idx}-outcome`}
              >
                <strong>outcome:</strong> <code>{outcome}</code>{" "}
                <span style={{ color: "rgba(0,0,0,0.6)" }}>
                  (status: <code>{status}</code>
                  {reason ? (
                    <>
                      {" "}
                      / reason: <code>{reason}</code>
                    </>
                  ) : null}
                  )
                </span>
              </div>
              <div
                data-testid={`approval-token-diagnostics-verify-entry-${idx}-expected-event-id`}
                style={{
                  fontSize: "0.78rem",
                  color: "rgba(0,0,0,0.55)",
                  marginTop: "0.2rem",
                }}
              >
                expected_event_id: <code>{e.expected_event_id}</code>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
