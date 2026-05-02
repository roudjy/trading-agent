import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles.css";
import "./styles/retro.css";

// PWA service-worker registration (v3.15.15.18). Best-effort: if the
// production server does not yet expose /sw.js (the wiring step in
// dashboard/dashboard.py is intentionally out of scope for this
// release), the registration silently fails and the SPA continues
// to function. The SW is read-only and only handles GET requests
// (see frontend/public/sw.js).
if (
  typeof window !== "undefined" &&
  "serviceWorker" in navigator &&
  window.location.protocol !== "file:"
) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .catch(() => {
        // Swallow: SW is opportunistic; failure is not fatal.
      });
  });
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
