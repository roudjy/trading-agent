import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build output goes to frontend/dist and is copied into the Python runtime
// image by the multi-stage Dockerfile. Flask serves it on "/" and
// "/assets/*"; nginx terminates :8050 and proxies to dashboard:8050 (ADR-011
// §2–3).
//
// resolve.extensions: .ts / .tsx come BEFORE .js so any untracked tsc-emit
// artifacts that exist alongside source files (frontend/src/**/*.js is
// not gitignored) never shadow a source .tsx/.ts. tsconfig.json has
// `noEmit: true` so .js siblings are not regenerated; this resolution
// order makes the bundler robust against any that still exist on disk.
export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: [".mts", ".ts", ".mtsx", ".tsx", ".jsx", ".mjs", ".js", ".json"],
  },
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
