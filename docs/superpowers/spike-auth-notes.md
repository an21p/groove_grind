# Auth spike notes (Task 1)

Date: 2026-05-25. Tested with the harness at `spike/auth-popup.html` and the
beatport.com devtools console.

## Popup OAuth flow — LOCKED (does not work for our app)

Opening a popup to
`https://api.beatport.com/v4/auth/o/authorize/?...&redirect_uri=.../post-message/`
and logging in produced **no `postMessage` back to our `localhost` window** —
the grey log box stayed empty after login. The `post-message/` relay exists for
Beatport's own swagger UI (same-origin on `api.beatport.com`) and does not post
to a third-party origin.

**Conclusion:** the popup path can't return a code to our app. It is retained in
`auth.ts` as a non-functional, experimental fallback only.

## Manual path — beatport.com uses NextAuth, token via `/api/auth/session`

On beatport.com:
- `document.cookie` is empty → auth cookies are **httpOnly** (NextAuth session).
- `localStorage` has only `nextauth.message`; no token in JS-readable storage.
- `GET /api/auth/session` (same-origin, credentialed) returns the live Beatport
  token. Relevant shape:
  ```
  { token: { accessToken: "<JWT>", refreshToken: "<opaque>",
             accessTokenExpires: <epoch ms>, ... } }
  ```

So the manual snippet reads `s.token.accessToken` (and, for refresh,
`s.token.refreshToken`). This is the **primary** auth path.

### Token characteristics (from the JWT payload)

- **Short-lived: ~10 minutes** (`exp - iat` = 600s) — far shorter than the
  swagger flow's ~10h. This is why the app offers auto-refresh.
- `client_id` in the JWT is **beatport.com's own web client**
  (different from the public swagger client id). Refresh must use that client id,
  which the app reads by decoding the access-token JWT (`auth.ts` `decodeJwt`).
- Scope `user:dj openid app:prostore` covers catalog reads.

### Refresh — UNVERIFIED against the API

Whether `POST /v4/auth/o/token/` with `grant_type=refresh_token` + the web
`client_id` is honored **from our origin** has not been confirmed (beatport.com's
web client may be confidential / require a secret). The app attempts it and
**falls back gracefully**: on a rejected refresh, a `BeatportAuthError` surfaces,
the gate reappears, and the user re-runs the console command. To verify the
refresh works, test it with a fresh refresh token; if it 401s, auto-refresh is
effectively a no-op and users re-paste every ~10 min.

## CORS (verified earlier)

`OPTIONS` to `/v4/auth/login/` and `/v4/catalog/search/` return
`access-control-allow-origin: *` with `authorization` allowed, so direct
browser API calls work from any origin once a Bearer token is in hand.
