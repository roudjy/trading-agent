# Trading Agent — React Frontend (v3.10)

Vite + React 18 + TypeScript SPA voor de v3.10 research control surface.
Wordt in productie gebouwd via de multi-stage `Dockerfile` (stage
`frontend_build` op `node:20-alpine`) en als statische bundle door
Flask geserveerd op `:8050`. Nginx reverse-proxyt de host-port en
injecteert anti-indexing headers (zie `ops/nginx/nginx.conf`).

## Schermen

- `/login` — inlogformulier (POST naar `/api/session/login`)
- `/` — Home (health + run-status + laatste report)
- `/presets` — preset cards met Run-knop (POST `/api/presets/<name>/run`)
- `/history` — run-status payload + archieflijst reports
- `/reports` — laatste `research/report_latest.md` + JSON samenvatting
- `/candidates` — `run_candidates_latest.v1.json` inspector

Legacy Flask dashboards blijven bereikbaar op `/legacy/dashboard` en
`/legacy/research-control` gedurende één release.

## Local dev

```
cd frontend
npm install
npm run dev   # Vite dev server op :5173; proxy /api -> :8050
```

In productie serveert Flask `frontend/dist/index.html` en
`frontend/dist/assets/*`. Vite schrijft naar `frontend/dist/` (zie
`vite.config.ts`).

## Anti-indexing

- `<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">`
  in `index.html`.
- `public/robots.txt` = `User-agent: * / Disallow: /`.
- Nginx `X-Robots-Tag` header en UA-block op crawler/AI user agents
  (zie `ops/nginx/nginx.conf`).
- Flask zet `X-Robots-Tag` op de SPA index als dubbele garantie.

## Geen business logic in frontend

De SPA bevat geen strategy-, preset- of promotion-logica. Alle
beslissingen gebeuren backend-side (Flask + research/). De React app
toont enkel wat `/api/*` teruggeeft.
