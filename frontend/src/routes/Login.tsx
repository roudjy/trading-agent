import { FormEvent, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";

export function Login() {
  const { authenticated, login, error } = useAuth();
  const [username, setUsername] = useState("joery");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname ?? "/";

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
    <div className="login-wrap">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Inloggen — JvR Trading Agent</h1>
        <p className="muted">Gebruik je bestaande dashboard credentials.</p>
        <label htmlFor="username">Gebruikersnaam</label>
        <input
          id="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
        />
        <label htmlFor="password">Wachtwoord</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        <div className="error">{error ?? ""}</div>
        <button type="submit" disabled={submitting}>
          {submitting ? "Inloggen…" : "Inloggen"}
        </button>
      </form>
    </div>
  );
}
