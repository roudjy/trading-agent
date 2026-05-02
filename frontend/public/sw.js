/**
 * JvR Agent Control PWA — minimal service worker (v3.15.15.18).
 *
 * Hard guarantees:
 *   - Read-only. The SW never POSTs / PUTs / PATCHes / DELETEs.
 *     Only GET requests are eligible for cache-or-network handling;
 *     anything else passes through unmodified.
 *   - Network-first for /api/agent-control/* so the user always sees
 *     the latest data when online; cache-fallback when offline.
 *   - Cache-first for the SPA shell so the UI is installable and
 *     usable offline.
 *   - No analytics. No external service. No remote scripts.
 *
 * Scope: this file is served from "/", so it controls the whole
 * origin. Note that v3.15.15.18 does NOT register a top-level Flask
 * route for "/sw.js" — the file is shipped via vite's public dir but
 * the production wiring step (one line in dashboard/dashboard.py)
 * is documented separately. Until that wiring lands, the SW is a
 * no-op in production; in `vite dev` it works as expected.
 */

const SHELL_CACHE = "agent-control-shell-v1";
const RUNTIME_CACHE = "agent-control-runtime-v1";

const SHELL_ASSETS = ["/agent-control", "/manifest.webmanifest", "/agent-control-icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k)),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Hard guarantee: only GET requests are eligible for SW handling.
  if (req.method !== "GET") return;

  const url = new URL(req.url);

  // /api/agent-control/* — network-first, cache fallback for offline.
  if (url.pathname.startsWith("/api/agent-control/")) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Static SPA shell — cache-first.
  if (
    url.pathname === "/" ||
    url.pathname === "/agent-control" ||
    url.pathname.startsWith("/assets/") ||
    url.pathname === "/manifest.webmanifest" ||
    url.pathname === "/agent-control-icon.svg"
  ) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Anything else: pass through to the network. Never invent data,
  // never substitute on errors — fail visibly.
});

async function cacheFirst(req) {
  const cache = await caches.open(SHELL_CACHE);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && res.ok) {
      cache.put(req, res.clone()).catch(() => undefined);
    }
    return res;
  } catch (err) {
    return new Response("offline", { status: 503, statusText: "offline" });
  }
}

async function networkFirst(req) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const res = await fetch(req);
    if (res && res.ok) {
      cache.put(req, res.clone()).catch(() => undefined);
    }
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (hit) return hit;
    return new Response(
      JSON.stringify({ status: "not_available", reason: "offline" }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  }
}
