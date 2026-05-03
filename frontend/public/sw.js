/**
 * JvR Agent Control PWA — minimal service worker (v3.15.15.26.1).
 *
 * Hard guarantees:
 *   - Read-only. The SW never POSTs / PUTs / PATCHes / DELETEs.
 *     Only GET requests are eligible for cache-or-network handling;
 *     anything else passes through unmodified.
 *   - Network-first for /api/agent-control/* so the user always sees
 *     the latest data when online; cache-fallback when offline.
 *   - Stale-while-revalidate for the SPA shell HTML (/, /agent-control,
 *     manifest, icon) so a freshly deployed UI propagates within one
 *     refresh cycle even when the SW is already installed.
 *   - Cache-first for hashed asset bundles (/assets/index-<hash>.js
 *     etc.) — those are immutable per build.
 *   - No analytics. No external service. No remote scripts.
 *
 * Why version-stamped cache names matter:
 *   In v3.15.15.26 the operator merged a mobile-first IA rebuild but
 *   reported no visible UX change. Root cause: the v3.15.15.18 SW
 *   hard-coded ``agent-control-shell-v1`` and never bumped, so an
 *   already-installed PWA continued to serve the cached pre-26 HTML
 *   (which referenced the old asset hashes). Bumping the cache name
 *   forces the activate handler to purge old caches and the shell
 *   stale-while-revalidate path to reach for a fresh /agent-control.
 *
 *   Bump ``SW_VERSION`` on every release that materially changes the
 *   PWA shell HTML / asset wiring. The default policy is: bump it.
 *
 * Scope: this file is served from "/", so it controls the whole
 * origin. Note that v3.15.15.18 does NOT register a top-level Flask
 * route for "/sw.js" — the file is shipped via vite's public dir but
 * the production wiring step (one line in dashboard/dashboard.py)
 * is documented separately. Until that wiring lands, the SW is a
 * no-op in production; in `vite dev` it works as expected.
 */

// v3.15.15.26.1 — version-stamped cache names. Bump SW_VERSION on
// every release that materially changes the PWA shell or assets.
// v3.15.15.26.2 — bumped because /agent-control was lifted out of
// the legacy <AppShell> wrapper. The new shell HTML references a
// new asset bundle and embeds none of the dashboard sidebar /
// topbar / ticker chrome. Without this bump, an installed PWA
// would keep replaying the embedded-shell HTML.
const SW_VERSION = "v3.15.15.26.2";
const SHELL_CACHE = `agent-control-shell-${SW_VERSION}`;
const RUNTIME_CACHE = `agent-control-runtime-${SW_VERSION}`;
const KNOWN_CACHE_NAMES = new Set([SHELL_CACHE, RUNTIME_CACHE]);

const SHELL_ASSETS = ["/agent-control", "/manifest.webmanifest", "/agent-control-icon.svg"];

self.addEventListener("install", (event) => {
  // skipWaiting() makes a freshly installed SW take over without
  // waiting for every existing tab to close. Combined with
  // clients.claim() in activate, this means a deploy propagates on
  // the next page load rather than the next browser restart.
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS).catch(() => undefined))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  // Purge ANY cache whose name does not match the current
  // version-stamped pair. This is what makes a release actually
  // visible to an already-installed PWA: caches from the prior
  // SW (e.g. ``agent-control-shell-v1``) get deleted on activate.
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => !KNOWN_CACHE_NAMES.has(k))
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

  // SPA shell HTML / manifest / icon — stale-while-revalidate so a
  // deployed UI change propagates within one refresh.
  if (
    url.pathname === "/" ||
    url.pathname === "/agent-control" ||
    url.pathname === "/manifest.webmanifest" ||
    url.pathname === "/agent-control-icon.svg"
  ) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // Hashed asset bundles (Vite emits ``/assets/index-<hash>.{js,css}``)
  // are content-addressed; cache-first is safe — a new bundle
  // produces a different filename which is fetched as a cache miss.
  if (url.pathname.startsWith("/assets/")) {
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

async function staleWhileRevalidate(req) {
  // Serve cache immediately if present; in parallel fetch the
  // network and refresh the cache. The next visit will see the
  // refreshed copy. This is the right policy for shell HTML
  // because the operator wants new UI as soon as possible while
  // still having a working offline shell on next launch.
  const cache = await caches.open(SHELL_CACHE);
  const cachedPromise = cache.match(req);
  const networkPromise = fetch(req)
    .then((res) => {
      if (res && res.ok) {
        cache.put(req, res.clone()).catch(() => undefined);
      }
      return res;
    })
    .catch(() => undefined);
  const cached = await cachedPromise;
  if (cached) {
    // Kick the revalidation but do not block on it.
    networkPromise.catch(() => undefined);
    return cached;
  }
  // No cache hit — wait for the network and synthesise an offline
  // response if it fails outright.
  const networked = await networkPromise;
  if (networked) return networked;
  return new Response("offline", { status: 503, statusText: "offline" });
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
