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
import { AgentControl } from "./routes/AgentControl";
import { AgentControlInboxPlaceholder } from "./routes/AgentControl/InboxPlaceholder";
import { AgentControlMergeRecommendation } from "./routes/AgentControl/MergeRecommendation";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        {/*
         * v3.15.15.26.2 — /agent-control is rendered as a STANDALONE
         * mobile-first PWA surface, not inside the legacy <AppShell>
         * (which carries the dashboard sidebar / topbar / ticker).
         * The route is lifted to the top level so the only chrome
         * around it is the auth guard.
         *
         * Legacy dashboard routes continue to render inside
         * <AppShell> via the wildcard route below.
         */}
        <Route
          path="/agent-control"
          element={
            <RequireAuth>
              <AgentControl />
            </RequireAuth>
          }
        />
        {/*
         * Safe placeholder for /agent-control/inbox?event=<event_id>
         * deep-links opened from the Web Push notification click. The
         * SW already constrains open_at to the /agent-control/inbox
         * prefix; the placeholder is read-only and contains no
         * decision verbs. The real N3c inbox-detail UI is not yet
         * implemented; until then this view lets the operator land
         * safely instead of hitting Flask's catch-all JSON 404.
         */}
        <Route
          path="/agent-control/inbox"
          element={
            <RequireAuth>
              <AgentControlInboxPlaceholder />
            </RequireAuth>
          }
        />
        {/*
         * v3.15.16.N5c — read-only merge-recommendation surface backed
         * by the existing N5a /api/agent-control/merge-recommendation/{list,detail}
         * blueprint. Both routes are read-only and share the same
         * <AgentControlMergeRecommendation /> component, which picks
         * list vs detail based on the optional :recommendationId param.
         * No approve / reject / merge / deploy verbs are exposed; merge
         * execution remains N5b territory and is not implemented in
         * this stage.
         */}
        <Route
          path="/agent-control/merge-recommendation"
          element={
            <RequireAuth>
              <AgentControlMergeRecommendation />
            </RequireAuth>
          }
        />
        <Route
          path="/agent-control/merge-recommendation/:recommendationId"
          element={
            <RequireAuth>
              <AgentControlMergeRecommendation />
            </RequireAuth>
          }
        />
        <Route
          path="/agent-control/*"
          element={
            <RequireAuth>
              <AgentControlInboxPlaceholder />
            </RequireAuth>
          }
        />
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
