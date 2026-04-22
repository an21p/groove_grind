# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Groove Grind — a Beatport browser that scrapes `www.beatport.com/_next/data/*` JSON endpoints to search artists/labels and surface an artist's top 10, their labels by first-release date, and their full track history grouped by label. Flask serves a compiled Svelte SPA from the same process and also proxies the Beatport-scraping endpoints.

## Commands

### Backend (Flask + scraper)

```bash
# One-time setup
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# Run the dev server (http://127.0.0.1:5000)
python app.py

# Run the scraper directly (search "darude" / "realm" + enrich)
python crawler.py

# Tests (hit live Beatport; network required)
python -m unittest discover -v
python -m unittest test.BeatportTestCase.test_get_artist   # single test
```

### Frontend (Svelte + Rollup)

```bash
cd client
npm install
npm run autobuild    # rebuild bundle.js on change (dev)
npm run build        # production build (terser minified)
```

Flask serves `client/public/` — the Svelte build must exist on disk before the app can serve anything. `npm run autobuild` writes `client/public/bundle.{js,css}`; Flask picks them up without restart.

### Production

Gunicorn entrypoint is `app:app` (see the GitHub Actions workflow and README Azure snippet):

```bash
gunicorn --bind=0.0.0.0 --timeout 600 app:app
```

CI (`.github/workflows/azure-webapps-python.yml`) builds the Svelte bundle, installs Python deps, and deploys to Azure Web Apps on push to `main`.

## Architecture

### The Beatport scraping trick (`crawler.py`)

Beatport's public site is a Next.js app, and its `/_next/data/<BUILD_ID>/en/...json` routes return the same data the React pages consume. `Beatport.unlock()` scrapes the homepage HTML with `requests_html`, regexes the `_buildManifest.js` path, and extracts the current Next.js build ID. That build ID is the `{key}` interpolated into every endpoint URL — search, artist, label, artist-tracks, label-tracks.

**This key rotates.** Beatport redeploys invalidate it. `app.py` caches it in the Flask session with a 12-hour TTL (`handle_beatport` decorator) and re-unlocks on expiry. If scraping suddenly 404s across the board, the key is stale — `Beatport().get_key()` refreshes it.

Response shape is brittle: the code indexes into `response['pageProps']['dehydratedState']['queries'][N]['state']['data']...` with hardcoded query positions (0, 1, 2). If Beatport reorders their React Query hydration, the indices shift and parsing breaks silently-ish (KeyError on the next access). When a scraper method breaks, dump the raw JSON and re-map indices rather than patching around it.

### `Artist.enrich()` / `Label.enrich()` pattern

`search()` returns lightweight `Artist`/`Label` objects (just what the search endpoint exposes). `.enrich(beatport)` is a deliberate second-fetch that pulls full bio + top 10 + all tracks. This two-step exists because search results don't include bios or tracks, and enriching every search result would be wasteful. Treat `enrich()` as expensive (paginates through all tracks with `all=True`).

### Flask ↔ Svelte wiring

- `/` and `/<path:path>` both `send_from_directory('client/public', ...)` — a catch-all static handler. New API routes must be registered **before** the catch-all would swallow them (Flask resolves routes in registration order, and specific routes win over the variable catch-all, but mind the pattern if adding nested API paths).
- The Svelte app uses relative URLs (`./search/${term}`, `./artist/${slug}/${id}/labels`) so it works under any base path.
- API responses serialize via each model's `to_dict()` method — `DefaultJSONEncoder` exists in `crawler.py` but isn't wired into Flask; use `to_dict()` explicitly (see `app.py:57`, `app.py:67`).

### Data flow for "show me an artist"

1. User types a name → `search()` in `App.svelte` hits `/search/<term>`.
2. Flask `search` → `Beatport.search()` → returns `[Artist], [Label]`.
3. User clicks an artist → `get_labels_by_date_for_artist()` hits `/artist/<slug>/<id>/labels`.
4. `get_all_artist_labels_by_date()` in `app.py` calls `b.get_artist()` (top 10) then `a.enrich()` (full tracks), groups tracks by label name with `toolz.groupby`, sorts each group by `release_date`, and returns `{top10, labelsByDate, all, artist}`.
5. Svelte renders four collapsible `<details>` panels; `toggleDetails()` enforces "only one open at a time" by mutating sibling `isOpen*` flags.

## Key conventions

- `app.secret_key = 'make_this_an_env'` in `app.py:8` is a placeholder — replace via env var before any real deployment (sessions currently cache the Beatport build-ID key).
- README's Svelte install snippet says `npm run autobuild`, not `npm run dev`. `dev` runs both autobuild and a `sirv` static server, but Flask is the intended server — prefer `autobuild` alone.
- Tests in `test.py` hit live Beatport. They assert exact counts (`len(john.tracks) == 25`) that depend on an artist's current catalog and will drift. Treat failures there as "data changed" first, "scraper broke" second.
- `test.py` has two methods named `test_get_artist_tracks` — the second overrides the first, so only the label-tracks assertion actually runs under unittest. Rename if adding back the artist-tracks check.
