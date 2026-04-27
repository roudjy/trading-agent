import { FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { Coin, Star, XMark } from "../components/pixel/Glyphs";
import { PixelCard } from "../components/pixel/PixelCard";
import { PixelBadge } from "../components/pixel/PixelBadge";

export function Login() {
  const { authenticated, login, error } = useAuth();
  const [username, setUsername] = useState("joery");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const location = useLocation();
  const from =
    (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/";

  if (authenticated) {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username, password);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="qre-app" data-palette="sky" data-intensity="balanced" data-pixelfont="on">
      <div
        style={{
          display: "grid",
          placeItems: "center",
          minHeight: "100vh",
          padding: 16,
        }}
      >
        <PixelCard style={{ width: "100%", maxWidth: 380, padding: 22 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              marginBottom: 14,
            }}
          >
            <span className="hop">
              <Coin size={22} />
            </span>
            <div>
              <div
                className="pxd"
                style={{ fontSize: 13, letterSpacing: 1.5, color: "var(--ink)" }}
              >
                QRE · CONTROL ROOM
              </div>
              <div className="mono" style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                authentication required
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            <label className="pixel-label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              className="pixel-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
            <label className="pixel-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="pixel-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />

            <div style={{ minHeight: 28, marginTop: 8 }}>
              {error && (
                <PixelBadge kind="err" icon={<XMark size={10} />}>
                  {error}
                </PixelBadge>
              )}
            </div>

            <button
              type="submit"
              className="pixel-btn"
              disabled={submitting}
              style={{ width: "100%", marginTop: 12 }}
            >
              <Star size={10} />
              <span style={{ marginLeft: 6 }}>
                {submitting ? "Signing in…" : "Sign In"}
              </span>
            </button>
          </form>
        </PixelCard>
      </div>
    </div>
  );
}
