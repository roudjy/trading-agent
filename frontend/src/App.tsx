import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./auth";
import { AppShell } from "./components/layout/AppShell";
import { Login } from "./routes/Login";
import { Dashboard } from "./routes/Dashboard";
import { Sprint } from "./routes/Sprint";
import { Campaigns } from "./routes/Campaigns";
import { Failures } from "./routes/Failures";
import { Artifacts } from "./routes/Artifacts";
import { Observability } from "./routes/Observability";
import { Health } from "./routes/Health";
import { Version } from "./routes/Version";
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
              <AppShell>
                <Routes>
                  <Route index element={<Dashboard />} />
                  <Route path="/sprint" element={<Sprint />} />
                  <Route path="/campaigns" element={<Campaigns />} />
                  <Route path="/failures" element={<Failures />} />
                  <Route path="/artifacts" element={<Artifacts />} />
                  <Route path="/observability" element={<Observability />} />
                  <Route path="/health" element={<Health />} />
                  <Route path="/version" element={<Version />} />
                  <Route path="/presets" element={<Presets />} />
                  <Route path="/history" element={<History />} />
                  <Route path="/reports" element={<Reports />} />
                  <Route path="/candidates" element={<Candidates />} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </AppShell>
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
    return (
      <div
        className="qre-app"
        data-palette="sky"
        data-intensity="balanced"
        data-pixelfont="on"
        style={{ display: "grid", placeItems: "center", minHeight: "100vh" }}
      >
        <div className="pxd" style={{ fontSize: 14, color: "var(--ink)" }}>
          LOADING…
        </div>
      </div>
    );
  }
  if (!authenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
