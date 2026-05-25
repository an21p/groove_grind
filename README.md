# Groove Grind

Groove Grind is a Beatport browser that uses the official Beatport v4 API to
search artists and labels and surface an artist's top 10, their labels ordered
by first release date, and their full track history grouped by label.

It is a **pure static Svelte single-page app** — there is no server. Each visitor
signs in with their own Beatport account in the browser, and every API call is
made directly from that browser to `api.beatport.com`. This is deliberate:
Beatport's API blocks datacenter IPs (the reason an earlier Flask-on-Azure build
returned HTTP 403), but a browser on a normal residential connection is not
blocked. Moving the calls client-side removes both the server and the block.

## How auth works

The app talks OAuth directly to `api.beatport.com/v4` using the public Beatport
client id. On first visit you see a **connect gate**:

- **Popup login (preferred):** a popup opens Beatport's own login page; you
  authenticate on beatport.com (we never see your password) and the app receives
  an access token.
- **Manual token (fallback):** if the popup flow is unavailable, the setup
  section gives you a devtools console command to copy your token and paste it
  in. Manual tokens expire (~10h) with no auto-refresh, so you'll be asked to
  re-run the command when that happens.

The token lives in `localStorage`. A "Disconnect Beatport" control in the footer
clears it.

## Local development

```bash
npm install
npm run autobuild     # rebuilds public/bundle.{js,css} on change
```

Then serve the static `public/` directory, e.g.:

```bash
npm start             # sirv public --single  (http://localhost:5000)
```

`npm run build` produces the minified production bundle. There is no backend
process and no `.env` — the only secret involved is the OAuth token, which lives
in the user's browser.

## Running tests

```bash
npm test              # Vitest, no network required
npx tsc --noEmit      # type check
```

The suite covers the browser-side Beatport package: error taxonomy
(`errors.ts`), model mapping (`models.ts`), the API client incl. 401-retry and
pagination (`client.ts`), the auth token store / refresh / popup handshake /
manual token (`auth.ts`), and the artist-stream orchestration (`catalog.ts`).

## Architecture

```
src/
  main.js              Svelte entry
  App.svelte           UI: connect gate + search + artist dossier
  beatport/
    errors.ts          typed errors (unavailable / rate-limited / auth)
    models.ts          Artist / Label / Track mappers
    client.ts          BeatportClient: search, getArtist, getArtistTop, iterArtistTracks
    auth.ts            AuthManager: token store, refresh, popup OAuth, manual token
    catalog.ts         streamArtist(): paginate -> group by label -> sort by date
  stores/
    session.ts         singletons (auth, client) + connect/disconnect store
```

`catalog.streamArtist` emits progressive `{type:'artist'|'tracks'|'done'|'error'}`
events that `App.svelte` renders incrementally — the same event protocol the app
used when the server streamed NDJSON.

## Deployment — Azure Static Web Apps

Pushes to `main` build and deploy via
`.github/workflows/azure-static-web-apps.yml` (the `Azure/static-web-apps-deploy`
action, `app_location: /`, `output_location: public`, build via `npm run build`).
`staticwebapp.config.json` rewrites unknown paths to `/index.html` for SPA
routing.

One-time setup: create an Azure Static Web App resource, add its deployment
token as the `AZURE_STATIC_WEB_APPS_API_TOKEN` repository secret, and point your
custom domain at it. No app settings or server secrets are required.
