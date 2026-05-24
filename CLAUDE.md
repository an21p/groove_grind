# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Groove Grind — a Beatport browser that uses the official Beatport v4 API to search artists/labels and surface an artist's top 10, their labels by first-release date, and their full track history grouped by label. Flask serves a compiled Svelte SPA from the same process and proxies the Beatport API endpoints.

## Commands

### Backend (Flask + official API)

```bash
# One-time setup (the .venv is uv-managed — use uv, not python -m venv)
uv venv
uv pip install -r requirements.txt
source .venv/bin/activate

# Run the dev server (http://127.0.0.1:5000). app.py calls load_dotenv(),
# so FLASK_SECRET_KEY (and the BEATPORT_* vars) are read from .env automatically.
python app.py

# Run the official-API client directly (live; needs BEATPORT_* in .env)
RUN_LIVE_TESTS=1 .venv/bin/python -m unittest test -v

# Fast tests (no network) — run by CI before deploy
.venv/bin/python -m unittest discover -v
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

### The Beatport official API (`beatport/` package)

Data comes from `https://api.beatport.com/v4`. `beatport.auth.TokenManager` runs the
3-step `authorization_code` OAuth flow (login → authorize → token) with the public swagger
client_id, caches one access token per process, and refreshes it before its 10h expiry.
`beatport.client.BeatportClient` exposes `search`, `get_artist`, `get_artist_top`, and
`iter_artist_tracks`, mapping responses to `beatport.models` and raising the typed errors in
`beatport.errors` (which `app.py` turns into HTTP status + `{error:{code,message}}`).

### Flask ↔ Svelte wiring

- `/` and `/<path:path>` both `send_from_directory('client/public', ...)` — a catch-all static handler. New API routes must be registered **before** the catch-all would swallow them (Flask resolves routes in registration order, and specific routes win over the variable catch-all, but mind the pattern if adding nested API paths).
- The Svelte app uses relative URLs (`./search/${term}`, `./artist/${slug}/${id}/labels`) so it works under any base path.
- API responses serialize via each model's `to_dict()` method — use `to_dict()` explicitly when adding new routes.

### Data flow for "show me an artist"

1. User types a name → `search()` in `App.svelte` hits `/search/<term>`.
2. Flask `search` → `BeatportClient.search()` → returns `[Artist], [Label]` (or raises a typed `BeatportError` → HTTP status + `{error:{code,message}}`).
3. User clicks an artist → hits `/artist/<slug>/<id>/labels` (ndjson stream).
4. `app.py` calls `beatport.get_artist()` (artist detail), `beatport.get_artist_top()` (top 10), then `beatport.iter_artist_tracks()` (paginated full catalog), groups tracks by label name with `toolz.groupby`, sorts each group by `release_date`, and streams `{type:artist}`, `{type:tracks}`, `{type:done}` (or `{type:error}`) events.
5. Svelte renders four collapsible `<details>` panels; `toggleDetails()` enforces "only one open at a time" by mutating sibling `isOpen*` flags.

## Key conventions

- `app.secret_key` is read from `os.environ['FLASK_SECRET_KEY']` (`app.py`), and `load_dotenv()` loads it from `.env` for local dev. The app will fail to import if the var is set neither in `.env` nor the environment (e.g. the Azure app setting in prod).
- README's Svelte install snippet says `npm run autobuild`, not `npm run dev`. `dev` runs both autobuild and a `sirv` static server, but Flask is the intended server — prefer `autobuild` alone.
- Fast tests (`test_fast.py`, `test_errors.py`, `test_models.py`, `test_auth.py`, `test_client.py`, `test_app.py`) require no network and are run by CI. Live tests (`test.py`) are skipped unless `RUN_LIVE_TESTS=1` and `BEATPORT_*` credentials are set.
