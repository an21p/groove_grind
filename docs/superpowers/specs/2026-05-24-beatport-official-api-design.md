# Design: Replace the Beatport scraper with the official v4 API

**Date:** 2026-05-24
**Status:** Approved (design); pending implementation plan

## Problem

Groove Grind currently scrapes Beatport's `www.beatport.com/_next/data/<BUILD_ID>/...json`
endpoints. In production (Azure App Service), Beatport returns **HTTP 403** to the
datacenter IP on the homepage fetch in `Beatport.unlock()`, so production cannot retrieve
any data. The block is IP-based (it works from residential IPs), not a code bug. Browser
headers did not bypass it; a proxy hook (`BEATPORT_PROXY`) was added as a fallback but
needs a paid residential proxy to activate.

The durable fix is to use Beatport's **official v4 API** (`https://api.beatport.com/v4`),
which is authenticated and not subject to the same IP block. The credentials already exist
in `.env` (`BEATPORT_USERNAME` = `kindling970`, `BEATPORT_PASSWORD`, `BEATPORT_CLIENT_ID` =
the public swagger client id `0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd`). No developer-portal
registration or client secret is required.

A second requirement: when Beatport cannot be reached, users must see an **appropriate
error message** rather than a silent empty result set. The current search path swallows
errors (`.catch(() => loading = false)`), which is the root of the "empty with no error"
behavior.

## Decisions (from brainstorming)

1. **Full replacement** of the scraper with the official API. Remove `requests_html`, the
   build-ID `unlock()`, and the brittle hardcoded React-Query index parsing. Nothing is lost
   because scraping is already blocked in prod.
2. **Differentiated error messages by cause** (unavailable / rate-limited / auth-config),
   plus a distinct "no results" empty state.
3. **App-level token** with auto-refresh — one shared token per server process (the
   credential is a single service account), not per-Flask-session.
4. **Small `beatport/` package** structure (auth / client / models / errors), replacing the
   single `crawler.py`.

## Authentication flow (verified working)

The public swagger client supports only the `authorization_code` grant (password grant
returns `unauthorized_client`). The verified 3-step flow, reference implementation
beets-beatport4 `beetsplug/beatport4/client.py`:

1. `POST https://api.beatport.com/v4/auth/login/` with JSON `{username, password}` on a
   `requests.Session` (sets session/csrf cookies). Success body contains `username` + `email`.
2. `GET https://api.beatport.com/v4/auth/o/authorize/?response_type=code&client_id=<id>&redirect_uri=https://api.beatport.com/v4/auth/o/post-message/`
   with `allow_redirects=False` → authorization `code` in the `Location` header query string.
3. `POST https://api.beatport.com/v4/auth/o/token/?code=<code>&grant_type=authorization_code&redirect_uri=<same>&client_id=<id>`
   → `{access_token, refresh_token, expires_in=36000 (10h), scope="app:docs user:dj", token_type="Bearer"}`.

Refresh: `POST .../auth/o/token/` with `grant_type=refresh_token&refresh_token=<rt>&client_id=<id>`.
API calls send `Authorization: Bearer <access_token>`.

## Architecture

New `beatport/` package replaces `crawler.py`:

- `beatport/errors.py` — exception taxonomy.
- `beatport/auth.py` — `TokenManager` (OAuth flow + process-level token cache + refresh).
- `beatport/models.py` — `Artist`, `Label`, `Track` (`from_api()` + `to_dict()`).
- `beatport/client.py` — `BeatportClient` (endpoint methods, pagination, error mapping).
- `beatport/__init__.py` — exports `BeatportClient` and the error types.

`app.py` holds one module-level `BeatportClient`, drops the per-session `handle_beatport`
caching, and maps typed errors to HTTP status + error JSON. `client/src/App.svelte` adds
real error handling on the search path and differentiated messages on both paths.

## Components

### errors.py
`BeatportError(Exception)` base with `code: str` and `user_message: str`. Subclasses:

- `BeatportUnavailable` — timeouts, connection errors, HTTP 5xx, HTTP 403 (block).
  `code="unavailable"`.
- `BeatportRateLimited` — HTTP 429. `code="rate_limited"`.
- `BeatportAuthError` — login/authorize/token failure, HTTP 401 after refresh.
  `code="auth"`.

### auth.py — `TokenManager(username, password, client_id)`
- `get_token() -> str` — returns a valid bearer token; obtains or refreshes as needed.
  Guarded by a `threading.Lock` (gunicorn may run multiple workers; each holds its own
  token, and within a worker the lock serializes refreshes).
- Tracks `access_token`, `refresh_token`, and an absolute `expiry` timestamp with a 60s
  safety buffer. When expired/near-expiry: try `_refresh()`; on failure, `_authorize()`.
- `_authorize()` runs the 3-step flow on a fresh `requests.Session`.
- Auth/login/token failures raise `BeatportAuthError`; network failures raise
  `BeatportUnavailable`.

### models.py
Map the official API JSON to the exact shape the frontend already consumes:

- **Artist** `to_dict()` → `{name, bio, id, slug, image}` (`image` flattened from
  `image.uri`; `bio` only present on artist-detail responses, default `""`).
- **Label** `to_dict()` → `{name, bio, id, slug, image}`.
- **Track** `to_dict()` → `{id, name, slug, artists:[Artist], remixers:[Artist],
  label:{id,name,image}, image, sample, release_date}`. Sources: `sample_url` → `sample`;
  `new_release_date` → `release_date`; `release.label` → `label`; `release.image.uri` or
  track `image.uri` → `image`.

### client.py — `BeatportClient(token_manager, base="https://api.beatport.com/v4")`
- `search(q) -> (list[Artist], list[Label])` — `GET /catalog/search/?q=`; reads the
  `artists` and `labels` arrays (ignores `tracks/releases/charts/playlists`).
- `get_artist(id) -> Artist` — `GET /catalog/artists/{id}/`.
- `get_artist_top(id, count=10) -> list[Track]` — `GET /catalog/artists/{id}/top/{count}/`.
- `iter_artist_tracks(id, per_page=150) -> Iterator[list[Track]]` — paginates
  `GET /catalog/artists/{id}/tracks/?page=&per_page=` using `results` + `next`.
- Private `_get(path, params)` attaches the bearer header, maps status codes to typed
  errors, and retries once on 401 after forcing a token refresh.

## Endpoints (confirmed live 2026-05-24)

| Purpose | Endpoint |
|---|---|
| Search | `GET /catalog/search/?q=` → `{artists[], labels[], tracks[], releases[], ...}` |
| Artist detail | `GET /catalog/artists/{id}/` → `{bio, id, image, name, slug, website}` |
| Artist top 10 | `GET /catalog/artists/{id}/top/10/` → list of 10 track objects |
| Artist tracks | `GET /catalog/artists/{id}/tracks/?page=&per_page=` → `{results[], next, count, page, per_page}` |

Label *tracks* are **not** implemented: `app.py` exposes no label route, and "labels-by-date"
and "tracks-grouped-by-label" are both derived from the artist's tracks. Labels appear in
search results as display-only items. (`/catalog/labels/{id}/tracks/` 404s at the obvious
path; out of scope.)

## Data flow

### `GET /search/<term>`
`client.search(term)` → `{"artists": [...], "labels": [...]}` (same shape as today).
Wrapped in try/except: on a typed error, return the matching HTTP status and
`{"error": {"code": ..., "message": ...}}`.

### `GET /artist/<slug>/<id>/labels` (ndjson stream, unchanged shape)
1. `{type:"artist", artist, top10}` — `get_artist(id)` + `get_artist_top(id, 10)`.
2. `{type:"tracks", tracks, cumulative}` per page — `iter_artist_tracks(id)`.
3. `{type:"done", labelsByDate, all}` — group accumulated tracks by `track.label` and sort
   by `release_date` in `app.py` (logic unchanged from today).

`slug` stays in the route and frontend URLs/keys, but the API addresses resources by `id`.

## Error handling (differentiated by cause)

| Cause | HTTP | code | User message |
|---|---|---|---|
| Unavailable (timeout / 5xx / 403 / connection) | 503 | `unavailable` | "Beatport is temporarily unavailable. Please try again in a moment." |
| Rate-limited (429) | 429 | `rate_limited` | "Beatport is busy right now. Please retry in a few seconds." |
| Auth / config (login/token/401) | 502 | `auth` | "We're having trouble connecting to Beatport — we're on it." (full detail logged server-side) |
| Genuine 0 results | 200 | — | distinct **"No results found"** empty state |

- Search error body: `{"error": {"code": "...", "message": "..."}}`.
- Stream: reuse the existing `{type:"error", ...}` event (already rendered as the
  "Transmission interrupted" banner), now carrying `code` + `message`.
- Svelte: replace `.catch(() => loading = false)` on the search path with logic that reads
  the response status/body and renders an error banner **visually distinct from** the
  no-results empty state. The artist-stream error path already exists; extend it to use the
  `code`/`message`.

## Testing

- **CI-safe unit tests (no network, no creds):**
  - `models.*.from_api()` mapping from committed JSON fixtures.
  - status → exception → message mapping.
  - `TokenManager` expiry/refresh logic against a mocked session (valid token reused, expired
    token refreshed, refresh-failure falls back to full auth).
- **Opt-in live tests** (`RUN_LIVE_TESTS=1` + creds): full auth + search + artist end-to-end.
- Commit real JSON fixtures (search, artist detail, top10, tracks page) under
  `tests/fixtures/`.
- The CI fast-test gate stays credential-free, so deploys are not blocked on Beatport
  secrets or flaky live calls.

## Config & deploy

- Env (already present locally; mirror as Azure app settings): `BEATPORT_USERNAME`,
  `BEATPORT_PASSWORD`, `BEATPORT_CLIENT_ID` (default = public swagger id, documented).
- Remove `requests_html` and `pyppeteer` from `requirements.txt`; confirm nothing else
  imports them.
- Keep the `BEATPORT_PROXY` env hook as a safety net in case the API is also IP-blocked from
  Azure.
- Post-deploy verification: confirm prod `https://groove-grind.azurewebsites.net/search/darude`
  returns data (i.e., the official API is reachable from the Azure IP).

## Out of scope

- Label detail / label-track browsing (no current route).
- Search result types beyond artists and labels (tracks/releases/charts/playlists).
- Replacing the existing ndjson streaming protocol or the Svelte rendering structure.
