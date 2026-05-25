# Groove Grind — Static Browser-Auth Migration

**Date:** 2026-05-25
**Status:** Approved design, pending implementation plan

## Problem

Groove Grind runs a Flask server that performs the Beatport OAuth flow with one
shared account and proxies every Beatport API call. In production on Azure,
Cloudflare/Beatport blocks the datacenter IP with HTTP 403. Every server-side
workaround tried (curl_cffi, OS `curl`, dropping the spoofed UA, an opt-in
outbound proxy) has failed or remains inactive. The block is **IP-based**: the
official API responds normally to a residential connection.

## Goal

Eliminate the 403 by moving all Beatport interaction into the user's browser, so
every API call originates from the user's residential IP. Convert the app from a
Flask-served SPA into a **pure static Svelte SPA** with no server and no shared
secrets. Make it **multi-user**: each visitor logs in with their *own* Beatport
account via a popup on beatport.com.

## Feasibility (verified)

`OPTIONS` preflights against the live API confirm CORS is wide open:

```
access-control-allow-origin: *
access-control-allow-headers: accept, authorization, content-type, user-agent, x-csrftoken, x-requested-with
access-control-allow-methods: DELETE, GET, OPTIONS, PATCH, POST, PUT
```

Both `/v4/auth/login/` and `/v4/catalog/search/` return these headers, and the
API answers a residential IP directly (`server: istio-envoy`, HTTP 200 — no
Cloudflare challenge). So a static app on any origin can call the API directly
with a `Bearer` token. `GET /v4/auth/o/authorize/` for a logged-out client
302-redirects to a hosted login page at `/v4/auth/login/?next=...`, and
`/v4/auth/o/post-message/` is the relay that returns the `code` to the opener
window — confirming Beatport hosts its own login UI and intends a popup flow.

## Chosen approach

**Full static rewrite, all logic in TypeScript.** Delete Flask. Port the Python
`beatport/` package and `app.py`'s artist-stream orchestration into TypeScript
modules that run in the browser. Host the built bundle on **Azure Static Web
Apps**.

Approaches rejected:
- *Static + serverless proxy fallback:* a proxy still runs on an Azure
  datacenter IP, so it hits the same 403. Adds a server back without solving the
  problem.
- *Hybrid (keep Flask serving the SPA, browser makes the API calls):* dodges the
  403 but keeps a server, gunicorn, and the Azure Web App we don't need. Viable
  only as an interim step; not the end state.

## Architecture

Pure static Svelte SPA. All Beatport logic lives in a TypeScript
`src/beatport/` package mirroring today's Python package one-to-one, so the port
is mechanical and reviewable side-by-side.

```
client/
  src/
    App.svelte            # unchanged UI; fetch() calls swapped for client calls
    main.js
    beatport/
      auth.ts             # popup OAuth + token store + refresh  (<- auth.py)
      client.ts           # search / getArtist / getArtistTop / iterArtistTracks  (<- client.py)
      models.ts           # Artist/Label/Track from_api mappers  (<- models.py)
      errors.ts           # typed error classes  (<- errors.py)
      catalog.ts          # artist-stream orchestration  (<- app.py get_artist gen())
    stores/
      session.ts          # Svelte store: token state, login/logout
```

### Data flow (all client-side)

1. User lands. If there is no valid token, the UI shows a **login gate**;
   clicking it opens the Beatport popup.
2. After login the token lives in the browser; `client.ts` attaches
   `Authorization: Bearer <token>` to direct `api.beatport.com/v4` calls.
3. `catalog.ts` replaces the server's NDJSON generator: it paginates tracks and
   invokes a callback that emits the **same** `{type:'artist'|'tracks'|'done'|'error'}`
   events `handleStreamEvent()` already consumes, so `App.svelte`'s streaming
   logic barely changes.

**Principle:** the UI's event-handling and rendering stay intact. We only swap
the *source* of those events from "fetch from Flask" to "call `catalog.ts`
directly."

## Authentication

The riskiest part. The implementation plan's **first task is a spike that gates
everything else.**

### Spike (Task 1)

Build a throwaway HTML page that opens a popup to:

```
https://api.beatport.com/v4/auth/o/authorize/
  ?response_type=code
  &client_id=<PUBLIC_CLIENT_ID>
  &redirect_uri=https://api.beatport.com/v4/auth/o/post-message/
```

Log in as a real Beatport user on beatport.com and observe whether the
`post-message/` relay `postMessage`s the `code` back to our window, and **what
target origin it uses**.

- **Relay posts to our origin (or `*`)** → popup flow confirmed; build on it.
- **Relay is locked to beatport.com origins** → fall back to the native
  email/password form: POST `{username, password}` to `/v4/auth/login/`, then
  `GET /v4/auth/o/authorize/`, then `POST /v4/auth/o/token/` — all CORS-open as
  verified above. Trade-off: users type their Beatport password into our form
  (phishing-shaped, breaks under 2FA/CAPTCHA), so this is the fallback only.

The public client id is the swagger client already hardcoded today:
`0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd`.

### `auth.ts` (mirrors `TokenManager`)

- `login()` — runs the popup handshake; resolves with
  `{access_token, refresh_token, expires_in}`.
- `getToken()` — returns the cached token if unexpired; else refreshes via
  `POST /v4/auth/o/token/` with `grant_type=refresh_token`; else triggers
  re-login. Same 60s expiry buffer as today (`EXPIRY_BUFFER_SECONDS`).
- `invalidate()` / `logout()` — clears the access token (and, for logout, the
  refresh token).

### Token storage

`localStorage` — persists across reloads and tabs, best UX for a browsing tool.
The token is a read-only Beatport catalog token (not high value) and the
`client_id` is already public, so the XSS exposure is acceptable and noted here
explicitly. A `session.ts` Svelte store wraps storage so the UI reacts to
login/logout/expiry.

No client secret and no server session, so `FLASK_SECRET_KEY` and the shared
`BEATPORT_*` credentials are deleted.

## Client, models, orchestration, errors

### `models.ts`

Faithful port of the three `from_api` mappers. Same `_img` flattening
(`{image:{uri}}` → plain URL string), same field names the Svelte already reads:

- Artist/Label: `id, name, slug, image, bio`
- Track: `id, name, slug, artists, remixers, label, image, sample, release_date`

JS objects are already the "dict" shape, so there is no separate `to_dict()` —
`from_api` returns plain objects directly. `Track.from_api` keeps the same
fallbacks: `sample_url → sample`, `new_release_date → release_date`, label from
`release.label` or a `{id:0, name:""}` placeholder.

### `client.ts` (mirrors `BeatportClient`)

A private `_get(path, params)` attaches the Bearer token and
`Accept: application/json`, with the same **401 → invalidate → retry once** logic
(`_get` with `_retry=false` on the second attempt). Exposes:

- `search(q)` → `{artists, labels}`
- `getArtist(id)`
- `getArtistTop(id, count=10)`
- `iterArtistTracks(id, perPage=150)` — async generator; page loop stops when no
  `next` or empty `results`.

### `catalog.ts` (ports `app.py` `get_artist` generator)

`streamArtist(id, onEvent, signal)`:

1. `getArtist` + `getArtistTop(10)` → emit `{type:'artist', artist, top10}`.
2. Loop `iterArtistTracks`, accumulating, emitting
   `{type:'tracks', tracks, cumulative}` per page (drives the live counters and
   progressive merge).
3. Sort all tracks by `release_date`; group by `label.name` (a small `groupBy`
   helper replaces `toolz.groupby`); build `labelsByDate` (earliest release per
   label, sorted ascending) and `all` groups → emit
   `{type:'done', labelsByDate, all}`.
4. On error emit `{type:'error', code, message}`. Respects an `AbortSignal` so
   `backToSearch` / new-artist cancellation still works.

### `errors.ts`

Port the four typed errors with their `code` and `userMessage`:

- `BeatportError` (base)
- `BeatportUnavailable` — timeouts, network failure, 5xx, IP block; "Beatport is
  temporarily unavailable. Please try again in a moment."
- `BeatportRateLimited` — HTTP 429; "Beatport is busy right now…"
- `BeatportAuthError` — credentials/auth failure.

The UI already renders `error.message`, so mapping HTTP 429 → rate-limited,
5xx/network → unavailable, 401 → auth keeps the exact same user-facing copy. A
browser `fetch` failing for network reasons can't always distinguish a true
block from offline; opaque failures map to `BeatportUnavailable`, same as today.

## UI wiring & login gate

Minimal changes to `App.svelte`:

- `search()` — replace `fetch('./search/...')` with `await client.search(term)`;
  map a thrown `BeatportError` to `searchError` (same copy as today).
- `openArtist()` — replace the `fetch('./artist/.../labels')` + NDJSON reader
  loop with `await streamArtist(id, handleStreamEvent, controller.signal)`.
  `handleStreamEvent`, `mergeProgressiveTracks`, the tweened counters, and all
  rendering stay exactly as-is — they already speak the `{type}` event protocol.

Login gate — a small component (or block in `App.svelte`) subscribed to the
`session` store:

- No valid token → a "Connect your Beatport account" button (in the existing
  masthead aesthetic) that calls `auth.login()`. Search is disabled until
  connected.
- Valid token → normal app, plus a small "disconnect" affordance (footer/top
  band) calling `logout()`.
- A 401 mid-session invalidates the token; the store flips and the gate
  reappears with a "session expired, reconnect" note.

Reuses the established editorial design language (Fraunces / JetBrains Mono) and
existing `.caps`, `.prompt-*`, and button styles — no new visual system.

## Repo restructure, Flask removal & deploy

**Delete:** `app.py`, `requirements.txt`, the Python `beatport/` package, all
Python tests (`test*.py`, `_testsupport.py`), `research.ipynb` (or archive it),
gunicorn references, and the `FLASK_SECRET_KEY` + `BEATPORT_*` env vars.

**Restructure:** promote `client/` to the project root so the repo *is* the
Svelte app. `index.html` is the entry; the build outputs `public/` (or `dist/`).

**CI/deploy:** replace `.github/workflows/azure-webapps-python.yml` with the
**Azure Static Web Apps** GitHub Action — build the Svelte bundle, deploy the
static output. Add `staticwebapp.config.json` with a SPA fallback (serve
`index.html` for unknown paths; the app uses client-side state, not real routes).
Decommission the old Azure Web App service. Update `CLAUDE.md` and `README.md` to
drop all Flask/gunicorn/server instructions.

## Testing

Replace the Python suite with **Vitest** (fits the Svelte/Rollup toolchain):

- `models.test.ts` — `from_api` mapping incl. image/label/date fallbacks (ports
  `test_models.py`).
- `client.test.ts` — `_get` 401-retry, search/artist parsing, pagination stop
  conditions, error mapping (ports `test_client.py`), with `fetch` mocked.
- `auth.test.ts` — token caching, expiry-buffer refresh, refresh-failure →
  re-login (ports `test_auth.py`), popup handshake mocked.
- `catalog.test.ts` — orchestration emits the correct `{type}` event sequence and
  correct grouping/sorting (new; covers logic previously in `app.py`).

The popup handshake itself is verified by the Task 1 spike against the live API
(not meaningfully unit-testable).

## Risks

- **Popup origin lock (primary):** the public `client_id` may only `postMessage`
  to beatport.com origins. Mitigated by the Task 1 spike and the native-form
  fallback.
- **Popup blockers:** `auth.login()` must be triggered by a direct user gesture
  (button click) so the browser allows the popup.
- **Token in `localStorage`:** XSS exposure, accepted as above.
