import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to frontend/dist and is copied into the Python runtime
// image by the multi-stage Dockerfile. Flask serves it on "/" and
// "/assets/*"; nginx terminates :8050 and proxies to dashboard:8050 (ADR-011
// §2–3).
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8050",
      "/legacy": "http://localhost:8050",
    },
  },
});
