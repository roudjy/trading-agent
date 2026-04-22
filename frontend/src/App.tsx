import { Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./auth";
import { Login } from "./routes/Login";
import { Dashboard } from "./routes/Dashboard";
import { Presets } from "./routes/Presets";
import { History } from "./routes/History";
import { Reports } from "./routes/Reports";
import { Candidates } from "./routes/Candidates";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="*"
          element={
            <RequireAuth>
              <ProtectedShell />
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { authenticated, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return <div className="muted" style={{ padding: "2rem" }}>Laden…</div>;
  }
  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}

function ProtectedShell() {
  const { actor, logout } = useAuth();
  return (
    <div className="layout">
      <aside className="nav">
        <h1>JvR Trading Agent</h1>
        <div className="version">v3.10 — Research Ops</div>
        <NavLink to="/" end>Home</NavLink>
        <NavLink to="/presets">Run Presets</NavLink>
        <NavLink to="/history">Run History</NavLink>
        <NavLink to="/reports">Reports</NavLink>
        <NavLink to="/candidates">Candidates</NavLink>
        <button className="logout" onClick={() => void logout()}>
          Uitloggen{actor ? ` (${actor})` : ""}
        </button>
      </aside>
      <main className="main">
        <Routes>
          <Route index element={<Dashboard />} />
          <Route path="/presets" element={<Presets />} />
          <Route path="/history" element={<History />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/candidates" element={<Candidates />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
