# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Groove Grind — a Beatport browser that uses the official Beatport v4 API to
search artists/labels and surface an artist's top 10, their labels by first
release date, and their full track history grouped by label. It is a **pure
static Svelte SPA with no server**: each user signs in with their own Beatport
account in the browser (popup OAuth, with a manual-token fallback), and every API
call goes directly from that browser to `api.beatport.com/v4`. Running the calls
client-side, on residential IPs, sidesteps the datacenter-IP 403 that blocked the
previous Flask-on-Azure build.

## Commands

```bash
npm install
npm run build        # production bundle (terser minified) -> public/bundle.{js,css}
npm run autobuild    # rebuild on change (dev)
npm start            # serve public/ statically (sirv --single)
npm test             # Vitest (no network)
npx tsc --noEmit     # type check
```

Rollup compiles `src/main.js` (+ the imported `.ts` modules, via
`@rollup/plugin-typescript`) into `public/bundle.js`; Svelte component CSS is
extracted to `public/bundle.css`. Test files (`*.test.ts`) are excluded from the
browser bundle and run only under Vitest.

## Architecture

### The browser-side Beatport package (`src/beatport/`)

A TypeScript port of what used to be the Flask `beatport/` package + the
`get_artist` route:

- `errors.ts` — typed errors (`BeatportError`, `BeatportUnavailable`,
  `BeatportRateLimited`, `BeatportAuthError`) carrying `code` + `userMessage`.
- `models.ts` — `artistFromApi` / `labelFromApi` / `trackFromApi` flatten API
  responses to plain objects (image `{uri}` → string; `sample_url` → `sample`;
  `new_release_date` → `release_date`; label from `release.label` or a
  `{id:0,name:""}` placeholder).
- `client.ts` — `BeatportClient` (`search`, `getArtist`, `getArtistTop`,
  `iterArtistTracks`); private `get()` attaches `Authorization: Bearer`, retries
  once after a 401 (invalidate → refresh), maps 429→rate-limited, else
  unavailable. Depends on a `TokenProvider` (`getToken`/`invalidate`).
- `auth.ts` — `AuthManager implements TokenProvider`. Token store in
  `localStorage` (`groovegrind.token`), refresh via `grant_type=refresh_token`
  with a 60s expiry buffer, popup OAuth `login()` (opens Beatport's authorize
  page, receives the `code` via `postMessage` from the `post-message/` relay,
  exchanges it for a token), and `setTokenManually()` for the fallback (no
  refresh token → a 401 forces re-setup). `MANUAL_TOKEN_SNIPPET` is the console
  command shown in the setup UI. The public swagger `client_id` is hardcoded.
- `catalog.ts` — `streamArtist(client, id, onEvent, signal)` replaces the server
  NDJSON generator: emits `{type:'artist',artist,top10}`, then
  `{type:'tracks',tracks,cumulative}` per page, then
  `{type:'done',labelsByDate,all}` (group by label name, sort by release_date),
  or `{type:'error',code,message}`. Respects an `AbortSignal`.

### Session + UI

- `src/stores/session.ts` — singleton `auth` (AuthManager) and `client`
  (BeatportClient), a `session` writable store `{connected}`, and
  `loginPopup` / `setManualToken` / `logout` / `refreshSession`.
- `App.svelte` — shows the **connect gate** when `!connected`, otherwise the
  search UI. `search()` calls `client.search()`; `openArtist()` calls
  `streamArtist(...)` feeding the unchanged `handleStreamEvent` dispatcher. Auth
  failures (including mid-stream, surfaced as error events) call
  `refreshSession()` so the gate reappears.

## Auth flow notes

- Popup origin guard and `MANUAL_TOKEN_SNIPPET` are validated/finalized by the
  spike harness in `spike/auth-popup.html` (see
  `docs/superpowers/spike-auth-notes.md`). If Beatport's relay posts from a
  different origin than `https://api.beatport.com`, update the guard in
  `auth.ts`'s `runPopup`.
- CORS is open on the API (`access-control-allow-origin: *` with `authorization`
  allowed), so direct browser calls work from any origin.

## Deployment

Azure Static Web Apps via `.github/workflows/azure-static-web-apps.yml`
(`app_location: /`, `output_location: public`, build `npm run build`).
`staticwebapp.config.json` provides the SPA navigation fallback. The only
required secret is `AZURE_STATIC_WEB_APPS_API_TOKEN`; there are no server-side
app settings or Beatport credentials.

## Key conventions

- No server, no `.env`, no `FLASK_SECRET_KEY` / `BEATPORT_*` — the only credential
  is the per-user OAuth token in the browser.
- Tests are colocated (`src/beatport/*.test.ts`) and require no network.
- `App.svelte` is plain JS (not `lang="ts"`); the `.ts` modules under `src/` are
  what `tsc --noEmit` type-checks.
