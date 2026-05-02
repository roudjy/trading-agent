import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// resolve.extensions ordering matches vite.config.ts so vitest never
// resolves a stale tsc-emit .js sibling ahead of the source .ts/.tsx.
export default defineConfig({
  plugins: [react()],
  resolve: {
    extensions: [".mts", ".ts", ".mtsx", ".tsx", ".jsx", ".mjs", ".js", ".json"],
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
