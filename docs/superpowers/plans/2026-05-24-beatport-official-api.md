# Official Beatport API Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `_next/data` web scraper with Beatport's official v4 API so production (Azure) can fetch data, and show differentiated error messages instead of silent empty results.

**Architecture:** A new `beatport/` package (`errors`, `auth`, `models`, `client`) holds the OAuth `authorization_code` flow with an app-level auto-refreshing token, endpoint methods, and typed errors. `app.py` keeps its existing routes and the ndjson stream shape but swaps the data source and maps typed errors to HTTP status + error JSON. `App.svelte` gains real error handling on search.

**Tech Stack:** Python 3.11, Flask, `requests`, `toolz`, `unittest`; Svelte/Rollup frontend. The venv is uv-managed — run Python as `.venv/bin/python`.

---

## Reference: confirmed API facts (verified live 2026-05-24)

- Base: `https://api.beatport.com/v4`. Token endpoint: `/auth/o/token/`. Redirect URI: `https://api.beatport.com/v4/auth/o/post-message/`.
- Public client_id (the only one needed): `0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd`. It supports **only** `authorization_code` (password grant → `unauthorized_client`).
- Auth = 3 steps: `POST /auth/login/` JSON `{username,password}` (sets cookies; success body has `username`+`email`) → `GET /auth/o/authorize/?response_type=code&client_id=&redirect_uri=` with `allow_redirects=False` (`code` in `Location` header) → `POST /auth/o/token/?code=&grant_type=authorization_code&redirect_uri=&client_id=` (returns `access_token`, `refresh_token`, `expires_in=36000`).
- `BEATPORT_USERNAME` is a username (`kindling970`), not an email.
- Endpoints: `GET /catalog/search/?q=` → `{artists[],labels[],tracks[],...}`; `GET /catalog/artists/{id}/` → `{bio,id,image,name,slug}`; `GET /catalog/artists/{id}/top/{count}/` → `{results[],next,...}`; `GET /catalog/artists/{id}/tracks/?page=&per_page=` → `{results[],next,count}`.
- Track JSON fields: `id,name,slug,sample_url,new_release_date,image{uri},artists[{id,name,slug,image{uri}}],remixers[],release{id,name,slug,image{uri},label{id,name,slug,image{uri}}}`.

## File Structure

- `beatport/__init__.py` — package exports.
- `beatport/errors.py` — `BeatportError` + 3 subclasses (each with `code`, `http_status`, `user_message`).
- `beatport/models.py` — `Artist`, `Label`, `Track` (`from_api()` + `to_dict()`).
- `beatport/auth.py` — `TokenManager` (OAuth flow, process-level token cache, refresh, thread-safe).
- `beatport/client.py` — `BeatportClient` (endpoint methods, pagination, status→error mapping).
- `_testsupport.py` — shared test fakes (`FakeResponse`, `FakeSession`).
- `test_models.py`, `test_auth.py`, `test_client.py`, `test_app.py` — new unit tests (no network).
- Modify `app.py`, `client/src/App.svelte`, `requirements.txt`, `test_fast.py`, `CLAUDE.md`, `README.md`.
- Delete `crawler.py`; replace `test.py` with opt-in live tests.

---

## Task 1: Error taxonomy

**Files:**
- Create: `beatport/__init__.py`
- Create: `beatport/errors.py`
- Test: `test_errors.py`

- [ ] **Step 1: Write the failing test**

`test_errors.py`:
```python
import unittest
from beatport.errors import (
    BeatportError, BeatportUnavailable, BeatportRateLimited, BeatportAuthError,
)


class ErrorTaxonomyTest(unittest.TestCase):
    def test_attributes(self):
        cases = [
            (BeatportUnavailable, "unavailable", 503),
            (BeatportRateLimited, "rate_limited", 429),
            (BeatportAuthError, "auth", 502),
        ]
        for cls, code, status in cases:
            e = cls()
            self.assertIsInstance(e, BeatportError)
            self.assertEqual(e.code, code)
            self.assertEqual(e.http_status, status)
            self.assertTrue(e.user_message)

    def test_custom_message_does_not_change_user_message(self):
        e = BeatportUnavailable("internal detail HTTP 500")
        self.assertEqual(str(e), "internal detail HTTP 500")
        self.assertIn("unavailable", e.user_message.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_errors -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beatport'`.

- [ ] **Step 3: Write minimal implementation**

`beatport/__init__.py`:
```python
from .errors import (
    BeatportError,
    BeatportUnavailable,
    BeatportRateLimited,
    BeatportAuthError,
)

__all__ = [
    "BeatportError",
    "BeatportUnavailable",
    "BeatportRateLimited",
    "BeatportAuthError",
]
```

`beatport/errors.py`:
```python
class BeatportError(Exception):
    """Base class for all Beatport client errors."""

    code = "error"
    http_status = 502
    user_message = "Something went wrong talking to Beatport."

    def __init__(self, message=None):
        super().__init__(message or self.user_message)


class BeatportUnavailable(BeatportError):
    """Timeouts, connection errors, HTTP 5xx, or a 403 IP block."""

    code = "unavailable"
    http_status = 503
    user_message = "Beatport is temporarily unavailable. Please try again in a moment."


class BeatportRateLimited(BeatportError):
    """HTTP 429."""

    code = "rate_limited"
    http_status = 429
    user_message = "Beatport is busy right now. Please retry in a few seconds."


class BeatportAuthError(BeatportError):
    """Login / authorize / token failure, or a 401 that survives a refresh."""

    code = "auth"
    http_status = 502
    user_message = "We're having trouble connecting to Beatport — we're on it."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_errors -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add beatport/__init__.py beatport/errors.py test_errors.py
git commit -m "feat(beatport): error taxonomy with code/http_status/user_message"
```

---

## Task 2: Models

**Files:**
- Create: `beatport/models.py`
- Test: `test_models.py`

- [ ] **Step 1: Write the failing test**

`test_models.py`:
```python
import unittest
from beatport.models import Artist, Label, Track

ARTIST_JSON = {
    "id": 3812, "name": "Darude", "slug": "darude",
    "image": {"uri": "http://img/darude.jpg"}, "bio": "Finnish DJ",
}
TRACK_JSON = {
    "id": 99, "name": "Sandstorm", "slug": "sandstorm",
    "sample_url": "http://s/x.mp3", "new_release_date": "2000-01-01",
    "image": {"uri": "http://img/track.jpg"},
    "artists": [{"id": 3812, "name": "Darude", "slug": "darude",
                 "image": {"uri": "http://img/d.jpg"}}],
    "remixers": [],
    "release": {
        "id": 1, "name": "Sandstorm EP", "slug": "sandstorm-ep",
        "image": {"uri": "http://img/rel.jpg"},
        "label": {"id": 7, "name": "16 Inch", "slug": "16-inch",
                  "image": {"uri": "http://img/lab.jpg"}},
    },
}


class ArtistModelTest(unittest.TestCase):
    def test_from_api_to_dict(self):
        d = Artist.from_api(ARTIST_JSON).to_dict()
        self.assertEqual(d, {"id": 3812, "name": "Darude", "slug": "darude",
                             "image": "http://img/darude.jpg", "bio": "Finnish DJ"})

    def test_missing_bio_defaults_empty(self):
        d = Artist.from_api({"id": 1, "name": "X", "slug": "x", "image": {}}).to_dict()
        self.assertEqual(d["bio"], "")
        self.assertEqual(d["image"], "")


class TrackModelTest(unittest.TestCase):
    def test_from_api_to_dict(self):
        d = Track.from_api(TRACK_JSON).to_dict()
        self.assertEqual(d["id"], 99)
        self.assertEqual(d["name"], "Sandstorm")
        self.assertEqual(d["sample"], "http://s/x.mp3")
        self.assertEqual(d["release_date"], "2000-01-01")
        self.assertEqual(d["image"], "http://img/track.jpg")
        self.assertEqual(d["artists"][0]["name"], "Darude")
        self.assertEqual(d["remixers"], [])
        self.assertEqual(d["label"], {"id": 7, "name": "16 Inch", "slug": "16-inch",
                                      "image": "http://img/lab.jpg", "bio": ""})

    def test_track_image_falls_back_to_release_image(self):
        data = dict(TRACK_JSON); data["image"] = {}
        self.assertEqual(Track.from_api(data).to_dict()["image"], "http://img/rel.jpg")

    def test_missing_label_yields_placeholder(self):
        data = dict(TRACK_JSON); data["release"] = {"id": 1, "name": "r", "image": {}}
        d = Track.from_api(data).to_dict()
        self.assertEqual(d["label"]["id"], 0)
        self.assertEqual(d["label"]["name"], "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_models -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beatport.models'`.

- [ ] **Step 3: Write minimal implementation**

`beatport/models.py`:
```python
def _img(obj):
    """Flatten Beatport's {'image': {'uri': ...}} to a plain URL string."""
    if not obj:
        return ""
    return (obj.get("image") or {}).get("uri", "") or ""


class Artist:
    def __init__(self, id, name, slug="", image="", bio=""):
        self.id = id
        self.name = name
        self.slug = slug
        self.image = image
        self.bio = bio

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            image=_img(data),
            bio=data.get("bio", "") or "",
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug,
                "image": self.image, "bio": self.bio}


class Label:
    def __init__(self, id, name, slug="", image="", bio=""):
        self.id = id
        self.name = name
        self.slug = slug
        self.image = image
        self.bio = bio

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            image=_img(data),
            bio=data.get("bio", "") or "",
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug,
                "image": self.image, "bio": self.bio}


class Track:
    def __init__(self, id, name, slug, artists, remixers, label, image, sample, release_date):
        self.id = id
        self.name = name
        self.slug = slug
        self.artists = artists
        self.remixers = remixers
        self.label = label
        self.image = image
        self.sample = sample
        self.release_date = release_date

    @classmethod
    def from_api(cls, data):
        release = data.get("release") or {}
        label_data = release.get("label") or {}
        label = Label.from_api(label_data) if label_data else Label(0, "", "", "")
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            artists=[Artist.from_api(a) for a in data.get("artists", [])],
            remixers=[Artist.from_api(r) for r in data.get("remixers", [])],
            label=label,
            image=_img(data) or _img(release),
            sample=data.get("sample_url") or "",
            release_date=data.get("new_release_date") or "",
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "artists": [a.to_dict() for a in self.artists],
            "remixers": [r.to_dict() for r in self.remixers],
            "label": self.label.to_dict(),
            "image": self.image,
            "sample": self.sample,
            "release_date": self.release_date,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_models -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add beatport/models.py test_models.py
git commit -m "feat(beatport): Artist/Label/Track models mapping API JSON to frontend shape"
```

---

## Task 3: Shared test fakes + TokenManager

**Files:**
- Create: `_testsupport.py`
- Create: `beatport/auth.py`
- Test: `test_auth.py`

- [ ] **Step 1: Write the shared fakes**

`_testsupport.py`:
```python
import json as _json


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=None):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.headers = headers or {}
        self.text = text if text is not None else _json.dumps(self._json)

    def json(self):
        return self._json


class FakeSession:
    """Routes GET/POST to canned responses by URL substring.

    routes: list of (method, url_substring, resp) where resp is a FakeResponse
    or a callable(**request_kwargs) -> FakeResponse. First match (in order) wins.
    Records every call in .calls as (method, url, kwargs).
    """

    def __init__(self, routes):
        self.routes = list(routes)
        self.headers = {}
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _handle(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        for m, sub, resp in self.routes:
            if m == method and sub in url:
                return resp(**kwargs) if callable(resp) else resp
        raise AssertionError(f"no fake route for {method} {url}")

    def get(self, url, **kwargs):
        return self._handle("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._handle("POST", url, kwargs)


def single_session_factory(routes):
    """Return (factory, session): factory() always yields the same FakeSession,
    so calls accumulate across TokenManager/_get invocations for assertions."""
    session = FakeSession(routes)
    return (lambda: session), session
```

- [ ] **Step 2: Write the failing test**

`test_auth.py`:
```python
import unittest
import requests
from beatport.auth import TokenManager
from beatport.errors import BeatportAuthError, BeatportUnavailable
from _testsupport import FakeResponse, single_session_factory

LOGIN_OK = FakeResponse(200, {"username": "kindling970", "email": "x@y.z"})
AUTHORIZE_OK = FakeResponse(302, headers={"Location": "https://x/post-message/?code=AC123"})


def token_route(**kwargs):
    grant = kwargs["params"]["grant_type"]
    if grant == "refresh_token":
        return FakeResponse(200, {"access_token": "TOK2", "refresh_token": "RT2", "expires_in": 36000})
    return FakeResponse(200, {"access_token": "TOK1", "refresh_token": "RT1", "expires_in": 36000})


def routes():
    return [
        ("POST", "/auth/login/", LOGIN_OK),
        ("GET", "/auth/o/authorize/", AUTHORIZE_OK),
        ("POST", "/auth/o/token/", token_route),
    ]


class TokenManagerTest(unittest.TestCase):
    def _mgr(self, route_list, clock_holder):
        factory, session = single_session_factory(route_list)
        mgr = TokenManager("u", "p", "cid",
                           session_factory=factory,
                           clock=lambda: clock_holder[0])
        return mgr, session

    def test_full_auth_returns_token(self):
        mgr, session = self._mgr(routes(), [1000.0])
        self.assertEqual(mgr.get_token(), "TOK1")
        methods = [c[0] for c in session.calls]
        self.assertIn("POST", methods)

    def test_cached_token_reused_without_relogin(self):
        mgr, session = self._mgr(routes(), [1000.0])
        mgr.get_token()
        before = len(session.calls)
        self.assertEqual(mgr.get_token(), "TOK1")
        self.assertEqual(len(session.calls), before)  # no new HTTP

    def test_expired_token_is_refreshed(self):
        clock = [1000.0]
        mgr, session = self._mgr(routes(), clock)
        self.assertEqual(mgr.get_token(), "TOK1")
        logins_before = sum(1 for c in session.calls if "/auth/login/" in c[1])
        clock[0] += 40000  # past the 10h expiry
        self.assertEqual(mgr.get_token(), "TOK2")  # came from refresh_token route
        logins_after = sum(1 for c in session.calls if "/auth/login/" in c[1])
        self.assertEqual(logins_after, logins_before)  # refresh, not re-login

    def test_login_failure_raises_auth(self):
        bad = [("POST", "/auth/login/", FakeResponse(403, {"error": "nope"}))]
        mgr, _ = self._mgr(bad, [1000.0])
        with self.assertRaises(BeatportAuthError):
            mgr.get_token()

    def test_network_error_raises_unavailable(self):
        def boom():
            class S:
                headers = {}
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def post(self, *a, **k): raise requests.RequestException("down")
                def get(self, *a, **k): raise requests.RequestException("down")
            return S()
        mgr = TokenManager("u", "p", "cid", session_factory=boom, clock=lambda: 1000.0)
        with self.assertRaises(BeatportUnavailable):
            mgr.get_token()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_auth -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beatport.auth'`.

- [ ] **Step 4: Write minimal implementation**

`beatport/auth.py`:
```python
import threading
import time
from urllib.parse import urlparse, parse_qs

import requests

from .errors import BeatportAuthError, BeatportUnavailable

API_BASE = "https://api.beatport.com/v4"
LOGIN_URL = f"{API_BASE}/auth/login/"
AUTHORIZE_URL = f"{API_BASE}/auth/o/authorize/"
TOKEN_URL = f"{API_BASE}/auth/o/token/"
REDIRECT_URI = f"{API_BASE}/auth/o/post-message/"
EXPIRY_BUFFER_SECONDS = 60
HTTP_TIMEOUT = 30
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class TokenManager:
    """Obtains and caches one Beatport API access token per process,
    refreshing it before expiry. Thread-safe."""

    def __init__(self, username, password, client_id,
                 session_factory=requests.Session, clock=time.monotonic):
        self._username = username
        self._password = password
        self._client_id = client_id
        self._session_factory = session_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._access_token = None
        self._refresh_token = None
        self._expiry = 0.0

    def get_token(self):
        with self._lock:
            if self._access_token and self._clock() < self._expiry:
                return self._access_token
            if self._refresh_token:
                try:
                    self._refresh()
                    return self._access_token
                except BeatportAuthError:
                    pass  # refresh rejected — fall through to a full re-auth
            self._authorize()
            return self._access_token

    def invalidate(self):
        with self._lock:
            self._access_token = None
            self._expiry = 0.0

    def _store(self, data):
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._expiry = self._clock() + data.get("expires_in", 36000) - EXPIRY_BUFFER_SECONDS

    def _refresh(self):
        try:
            with self._session_factory() as s:
                s.headers.update(HEADERS)
                r = s.post(TOKEN_URL, params={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                }, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise BeatportUnavailable(str(e))
        if r.status_code != 200 or "access_token" not in r.text:
            raise BeatportAuthError(f"refresh failed: HTTP {r.status_code}")
        self._store(r.json())

    def _authorize(self):
        try:
            with self._session_factory() as s:
                s.headers.update(HEADERS)
                r = s.post(LOGIN_URL,
                           json={"username": self._username, "password": self._password},
                           timeout=HTTP_TIMEOUT)
                if r.status_code != 200:
                    raise BeatportAuthError(f"login failed: HTTP {r.status_code}")
                data = r.json()
                if "username" not in data or "email" not in data:
                    raise BeatportAuthError("login rejected (invalid credentials)")

                r = s.get(AUTHORIZE_URL, params={
                    "response_type": "code",
                    "client_id": self._client_id,
                    "redirect_uri": REDIRECT_URI,
                }, allow_redirects=False, timeout=HTTP_TIMEOUT)
                codes = parse_qs(urlparse(r.headers.get("Location", "")).query).get("code")
                if not codes:
                    raise BeatportAuthError("no authorization code in redirect")

                r = s.post(TOKEN_URL, params={
                    "code": codes[0],
                    "grant_type": "authorization_code",
                    "redirect_uri": REDIRECT_URI,
                    "client_id": self._client_id,
                }, timeout=HTTP_TIMEOUT)
                if r.status_code != 200 or "access_token" not in r.text:
                    raise BeatportAuthError(f"token exchange failed: HTTP {r.status_code}")
                self._store(r.json())
        except requests.RequestException as e:
            raise BeatportUnavailable(str(e))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_auth -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add _testsupport.py beatport/auth.py test_auth.py
git commit -m "feat(beatport): TokenManager with 3-step OAuth, refresh, thread-safety"
```

---

## Task 4: BeatportClient

**Files:**
- Create: `beatport/client.py`
- Modify: `beatport/__init__.py` (export `BeatportClient`, `TokenManager`)
- Test: `test_client.py`

- [ ] **Step 1: Write the failing test**

`test_client.py`:
```python
import unittest
from beatport.client import BeatportClient
from beatport.errors import BeatportRateLimited, BeatportUnavailable, BeatportAuthError
from _testsupport import FakeResponse, single_session_factory


class FakeTokens:
    def __init__(self):
        self.invalidated = 0

    def get_token(self):
        return "TOK"

    def invalidate(self):
        self.invalidated += 1


SEARCH = {"artists": [{"id": 1, "name": "Darude", "slug": "darude", "image": {"uri": "a"}}],
          "labels": [{"id": 2, "name": "Lab", "slug": "lab", "image": {"uri": "l"}}],
          "tracks": [], "releases": []}
ARTIST = {"id": 1, "name": "Darude", "slug": "darude", "image": {"uri": "a"}, "bio": "b"}
TRACK = {"id": 9, "name": "T", "slug": "t", "sample_url": "s", "new_release_date": "2000-01-01",
         "image": {"uri": "i"}, "artists": [], "remixers": [],
         "release": {"id": 1, "name": "r", "image": {"uri": "ri"},
                     "label": {"id": 3, "name": "L", "slug": "l", "image": {"uri": "li"}}}}


def client_for(routes):
    factory, session = single_session_factory(routes)
    return BeatportClient(FakeTokens(), session_factory=factory), session


class ClientHappyPathTest(unittest.TestCase):
    def test_search(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(200, SEARCH))])
        artists, labels = c.search("darude")
        self.assertEqual(artists[0].name, "Darude")
        self.assertEqual(labels[0].name, "Lab")

    def test_get_artist(self):
        c, _ = client_for([("GET", "/catalog/artists/1/", FakeResponse(200, ARTIST))])
        self.assertEqual(c.get_artist(1).bio, "b")

    def test_get_artist_top(self):
        c, _ = client_for([("GET", "/top/10/", FakeResponse(200, {"results": [TRACK]}))])
        top = c.get_artist_top(1, 10)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].name, "T")

    def test_iter_artist_tracks_paginates(self):
        page1 = FakeResponse(200, {"results": [TRACK], "next": "p2"})
        page2 = FakeResponse(200, {"results": [TRACK], "next": None})
        calls = {"n": 0}

        def tracks_route(**kw):
            calls["n"] += 1
            return page1 if calls["n"] == 1 else page2

        c, _ = client_for([("GET", "/tracks/", tracks_route)])
        pages = list(c.iter_artist_tracks(1))
        self.assertEqual(len(pages), 2)
        self.assertEqual(calls["n"], 2)


class ClientErrorMappingTest(unittest.TestCase):
    def test_429_raises_rate_limited(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(429))])
        with self.assertRaises(BeatportRateLimited):
            c.search("x")

    def test_500_raises_unavailable(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(503))])
        with self.assertRaises(BeatportUnavailable):
            c.search("x")

    def test_403_raises_unavailable(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(403))])
        with self.assertRaises(BeatportUnavailable):
            c.search("x")

    def test_401_retries_after_invalidate_then_succeeds(self):
        seq = {"n": 0}

        def search_route(**kw):
            seq["n"] += 1
            return FakeResponse(401) if seq["n"] == 1 else FakeResponse(200, SEARCH)

        factory, _ = single_session_factory([("GET", "/catalog/search/", search_route)])
        tokens = FakeTokens()
        c = BeatportClient(tokens, session_factory=factory)
        artists, _ = c.search("x")
        self.assertEqual(artists[0].name, "Darude")
        self.assertEqual(tokens.invalidated, 1)

    def test_401_twice_raises_auth(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(401))])
        with self.assertRaises(BeatportAuthError):
            c.search("x")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_client -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'beatport.client'`.

- [ ] **Step 3: Write minimal implementation**

`beatport/client.py`:
```python
import requests

from .auth import API_BASE, HEADERS, HTTP_TIMEOUT
from .errors import BeatportAuthError, BeatportRateLimited, BeatportUnavailable
from .models import Artist, Label, Track


class BeatportClient:
    def __init__(self, token_manager, base=API_BASE, session_factory=requests.Session):
        self._tokens = token_manager
        self._base = base
        self._session_factory = session_factory

    def _get(self, path, params=None, _retry=True):
        headers = dict(HEADERS)
        headers["Authorization"] = f"Bearer {self._tokens.get_token()}"
        try:
            with self._session_factory() as s:
                r = s.get(f"{self._base}{path}", params=params or {},
                          headers=headers, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise BeatportUnavailable(str(e))

        if r.status_code == 200:
            return r.json()
        if r.status_code == 401 and _retry:
            self._tokens.invalidate()
            return self._get(path, params=params, _retry=False)
        if r.status_code == 401:
            raise BeatportAuthError("HTTP 401 after token refresh")
        if r.status_code == 429:
            raise BeatportRateLimited()
        raise BeatportUnavailable(f"HTTP {r.status_code}")

    def search(self, q):
        data = self._get("/catalog/search/", {"q": q})
        artists = [Artist.from_api(a) for a in data.get("artists", [])]
        labels = [Label.from_api(l) for l in data.get("labels", [])]
        return artists, labels

    def get_artist(self, id):
        return Artist.from_api(self._get(f"/catalog/artists/{id}/"))

    def get_artist_top(self, id, count=10):
        data = self._get(f"/catalog/artists/{id}/top/{count}/")
        return [Track.from_api(t) for t in data.get("results", [])]

    def iter_artist_tracks(self, id, per_page=150):
        page = 1
        while True:
            data = self._get(f"/catalog/artists/{id}/tracks/",
                             {"page": page, "per_page": per_page})
            yield [Track.from_api(t) for t in data.get("results", [])]
            if not data.get("next"):
                break
            page += 1
```

- [ ] **Step 4: Update package exports**

Replace `beatport/__init__.py` with:
```python
from .auth import TokenManager
from .client import BeatportClient
from .errors import (
    BeatportError,
    BeatportUnavailable,
    BeatportRateLimited,
    BeatportAuthError,
)

__all__ = [
    "TokenManager",
    "BeatportClient",
    "BeatportError",
    "BeatportUnavailable",
    "BeatportRateLimited",
    "BeatportAuthError",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m unittest test_client -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add beatport/client.py beatport/__init__.py test_client.py
git commit -m "feat(beatport): BeatportClient with endpoints, pagination, status->error mapping"
```

---

## Task 5: Wire app.py to BeatportClient + error responses

**Files:**
- Modify: `app.py` (full rewrite of imports/client/routes)
- Test: `test_app.py`

- [ ] **Step 1: Write the failing test**

`test_app.py`:
```python
import os
import unittest

os.environ.setdefault("FLASK_SECRET_KEY", "test")

import app  # noqa: E402
from beatport.errors import BeatportUnavailable  # noqa: E402
from beatport.models import Artist, Label  # noqa: E402


class FakeClient:
    def __init__(self, search_result=None, exc=None):
        self._search_result = search_result
        self._exc = exc

    def search(self, q):
        if self._exc:
            raise self._exc
        return self._search_result


class SearchRouteTest(unittest.TestCase):
    def setUp(self):
        self.http = app.app.test_client()
        self._orig = app.beatport

    def tearDown(self):
        app.beatport = self._orig

    def test_search_ok(self):
        app.beatport = FakeClient(search_result=(
            [Artist(1, "Darude", "darude", "img")],
            [Label(2, "Lab", "lab", "img2")],
        ))
        r = self.http.get("/search/darude")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["artists"][0]["name"], "Darude")
        self.assertEqual(d["labels"][0]["name"], "Lab")

    def test_search_empty_is_200_no_error(self):
        app.beatport = FakeClient(search_result=([], []))
        r = self.http.get("/search/zzzznope")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["artists"], [])
        self.assertNotIn("error", d)

    def test_search_unavailable_returns_503_error(self):
        app.beatport = FakeClient(exc=BeatportUnavailable())
        r = self.http.get("/search/darude")
        self.assertEqual(r.status_code, 503)
        d = r.get_json()
        self.assertEqual(d["error"]["code"], "unavailable")
        self.assertIn("unavailable", d["error"]["message"].lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_app -v`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'beatport'` (or the search route still imports `crawler`).

- [ ] **Step 3: Rewrite `app.py`**

Replace the entire contents of `app.py` with:
```python
from flask import Flask, send_from_directory, Response, stream_with_context
from dotenv import load_dotenv
from toolz import groupby
from beatport import BeatportClient, TokenManager, BeatportError
import json
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

PUBLIC_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

_tokens = TokenManager(
    username=os.environ.get("BEATPORT_USERNAME", ""),
    password=os.environ.get("BEATPORT_PASSWORD", ""),
    client_id=os.environ.get("BEATPORT_CLIENT_ID", PUBLIC_CLIENT_ID),
)
beatport = BeatportClient(_tokens)


def _error_body(err):
    return {"error": {"code": err.code, "message": err.user_message}}


@app.route("/")
def base():
    return send_from_directory("client/public", "index.html")


@app.route("/<path:path>")
def home(path):
    return send_from_directory("client/public", path)


@app.route("/search/<term>")
def search(term):
    try:
        artists, labels = beatport.search(term)
    except BeatportError as e:
        app.logger.warning("search failed: %s", e)
        return _error_body(e), e.http_status
    return {
        "artists": [a.to_dict() for a in artists],
        "labels": [l.to_dict() for l in labels],
    }


@app.route("/artist/<slug>/<id>/labels")
def get_artist(slug, id):
    def gen():
        try:
            artist = beatport.get_artist(id)
            top10 = beatport.get_artist_top(id, 10)
            yield json.dumps({
                "type": "artist",
                "artist": artist.to_dict(),
                "top10": [t.to_dict() for t in top10],
            }) + "\n"

            all_tracks = []
            for page in beatport.iter_artist_tracks(id):
                all_tracks.extend(page)
                yield json.dumps({
                    "type": "tracks",
                    "tracks": [t.to_dict() for t in page],
                    "cumulative": len(all_tracks),
                }) + "\n"

            sorted_tracks = sorted(all_tracks, key=lambda t: t.release_date)
            grouped = groupby(lambda t: t.label.name, sorted_tracks)
            labels_by_date = sorted(
                [{
                    "label": grouped[k][0].label.to_dict(),
                    "date": min(t.release_date for t in grouped[k]),
                } for k in grouped],
                key=lambda item: item["date"],
            )
            all_groups = [
                {"label": grouped[k][0].label.to_dict(),
                 "tracks": [t.to_dict() for t in grouped[k]]}
                for k in grouped
            ]
            yield json.dumps({
                "type": "done",
                "labelsByDate": labels_by_date,
                "all": all_groups,
            }) + "\n"
        except BeatportError as e:
            app.logger.warning("artist stream failed: %s", e)
            yield json.dumps({"type": "error", "code": e.code,
                              "message": e.user_message}) + "\n"
        except Exception:
            app.logger.exception("artist stream crashed")
            yield json.dumps({"type": "error", "code": "error",
                              "message": "Something went wrong. Please try again."}) + "\n"

    return Response(stream_with_context(gen()), mimetype="application/x-ndjson")


if __name__ == "__main__":
    app.run(debug=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_app -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "feat(app): serve search/artist from official API; map errors to HTTP + JSON"
```

---

## Task 6: Frontend error UX (App.svelte)

**Files:**
- Modify: `client/src/App.svelte`

No JS unit-test framework exists; verification is a production build + manual check.

- [ ] **Step 1: Add the `searchError` state variable**

In `client/src/App.svelte`, after line `let labels = null;` (around line 15), add:
```javascript
	let searchError = null;   // {code, message} | string | null
```

- [ ] **Step 2: Rewrite the `search()` function to surface errors**

Replace the existing `search()` function (the block starting `function search() {` … through its closing `}`) with:
```javascript
	function search() {
		if (!searchTerm.trim()) return;
		loading = true;
		hasSearched = true;
		artist = null;
		artists = null;
		labels = null;
		searchError = null;
		fetch(`./search/${encodeURIComponent(searchTerm.trim())}`)
			.then(async r => {
				const d = await r.json().catch(() => ({}));
				if (!r.ok || (d && d.error)) {
					searchError = (d && d.error && d.error.message)
						|| 'Beatport is temporarily unavailable. Please try again in a moment.';
					loading = false;
					return;
				}
				artists = d.artists || [];
				labels = d.labels || [];
				loading = false;
			})
			.catch(() => {
				searchError = 'Beatport is temporarily unavailable. Please try again in a moment.';
				loading = false;
			});
	}
```

- [ ] **Step 3: Render an error banner distinct from the empty state**

In the markup, immediately after the loading-bar block (after its closing `{/if}`, around line 320) and before `<!-- Artist index (search results) -->`, insert:
```svelte
	<!-- Search connection error (distinct from a zero-result search) -->
	{#if searchError && !artist && !loading}
		<section class="section">
			<div class="stream-error caps" role="alert">
				<span class="stream-error-label">Connection problem</span>
				<span class="stream-error-msg">{searchError}</span>
			</div>
		</section>
	{/if}
```
(The results section already only renders `{#if artists && !artist && !loading}`, so on error — where `artists` stays `null` — the banner shows instead of an empty index. A genuine zero-result search sets `artists = []`, which still renders the existing "No entries found in the index." empty state.)

- [ ] **Step 4: Make the stream error use the server message**

Find the `handleStreamEvent` branch `else if (evt.type === 'error')` (around line 135) and ensure its body is exactly:
```javascript
		} else if (evt.type === 'error') {
			streamError = evt.message || 'Beatport is temporarily unavailable. Please try again in a moment.';
			streamingCatalog = false;
		}
```

- [ ] **Step 5: Build the frontend**

Run:
```bash
cd client && npm install && npm run build && cd ..
```
Expected: build completes; `client/public/bundle.js` is regenerated with no Rollup errors.

- [ ] **Step 6: Manual verification (happy path + error path)**

Happy path:
```bash
.venv/bin/python app.py   # then in a browser: http://127.0.0.1:5000, search "darude"
```
Expected: artist results render; clicking an artist streams top10 + catalog.

Error path — temporarily break the credential to force an auth failure:
```bash
# In .env, change BEATPORT_PASSWORD to a wrong value, restart app.py, search "darude".
```
Expected: the red "Connection problem" banner shows "We're having trouble connecting to Beatport — we're on it." (NOT an empty result, NOT "No entries found"). Then restore the correct password and restart.

- [ ] **Step 7: Commit**

```bash
git add client/src/App.svelte client/public/bundle.js client/public/bundle.js.map
git commit -m "feat(ui): show differentiated connection-error banner on search instead of empty results"
```

---

## Task 7: Remove the scraper, update tests, deps, and docs

**Files:**
- Delete: `crawler.py`
- Replace: `test.py` (opt-in live tests)
- Modify: `test_fast.py`, `requirements.txt`, `CLAUDE.md`, `README.md`

- [ ] **Step 1: Delete the scraper**

```bash
git rm crawler.py
```

- [ ] **Step 2: Simplify `test_fast.py` (drop crawler/model tests now covered elsewhere)**

Replace the entire contents of `test_fast.py` with:
```python
#!/usr/bin/env python

# Fast tests (no network). Run by CI before deploy.
# .venv/bin/python -m unittest test_fast -v

import os
import unittest

os.environ.setdefault("FLASK_SECRET_KEY", "test")


class AppImportTest(unittest.TestCase):
    def test_app_imports(self):
        import app
        from flask import Flask
        self.assertIsInstance(app.app, Flask)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Replace `test.py` with opt-in live tests**

Replace the entire contents of `test.py` with:
```python
#!/usr/bin/env python

# Live end-to-end tests against the real Beatport API.
# Skipped unless RUN_LIVE_TESTS=1 and BEATPORT_* credentials are present.
# RUN_LIVE_TESTS=1 .venv/bin/python -m unittest test -v

import os
import unittest

from dotenv import load_dotenv

load_dotenv()

from beatport import BeatportClient, TokenManager  # noqa: E402

PUBLIC_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

_RUN = os.environ.get("RUN_LIVE_TESTS") == "1" and bool(os.environ.get("BEATPORT_PASSWORD"))


@unittest.skipUnless(_RUN, "set RUN_LIVE_TESTS=1 (+ BEATPORT_* creds) to run live tests")
class LiveBeatportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tokens = TokenManager(
            username=os.environ["BEATPORT_USERNAME"],
            password=os.environ["BEATPORT_PASSWORD"],
            client_id=os.environ.get("BEATPORT_CLIENT_ID", PUBLIC_CLIENT_ID),
        )
        cls.client = BeatportClient(tokens)

    def test_search_returns_artists(self):
        artists, _ = self.client.search("darude")
        self.assertTrue(any(a.name.lower() == "darude" for a in artists))

    def test_artist_detail_has_bio_field(self):
        artist = self.client.get_artist(3812)  # Darude
        self.assertEqual(artist.id, 3812)
        self.assertIsInstance(artist.bio, str)

    def test_artist_top_returns_tracks(self):
        top = self.client.get_artist_top(3812, 10)
        self.assertTrue(top)
        self.assertTrue(top[0].name)

    def test_iter_artist_tracks_first_page(self):
        first = next(self.client.iter_artist_tracks(3812))
        self.assertTrue(first)
        self.assertTrue(first[0].release_date)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Drop the scraping dependencies**

In `requirements.txt`, delete exactly these two lines:
```
requests-html==0.10.0
pyppeteer==2.0.0
```
(Leave the rest of the pinned list unchanged.)

- [ ] **Step 5: Verify nothing still imports the scraper or removed deps**

Run:
```bash
grep -rn "import crawler\|from crawler\|requests_html\|pyppeteer" --include="*.py" . | grep -v "^\./\.venv/"
```
Expected: no output.

- [ ] **Step 6: Update docs**

In `CLAUDE.md`, replace the "Run the scraper directly" command line with a note that scraping is gone:
```
# Run the official-API client directly (live; needs BEATPORT_* in .env)
RUN_LIVE_TESTS=1 .venv/bin/python -m unittest test -v
```
And replace the "The Beatport scraping trick (`crawler.py`)" architecture section with:
```
### The Beatport official API (`beatport/` package)

Data comes from `https://api.beatport.com/v4`. `beatport.auth.TokenManager` runs the
3-step `authorization_code` OAuth flow (login → authorize → token) with the public swagger
client_id, caches one access token per process, and refreshes it before its 10h expiry.
`beatport.client.BeatportClient` exposes `search`, `get_artist`, `get_artist_top`, and
`iter_artist_tracks`, mapping responses to `beatport.models` and raising the typed errors in
`beatport.errors` (which `app.py` turns into HTTP status + `{error:{code,message}}`).
```

In `README.md`, update the project description line and the "Running tests" section to mention the official API and `RUN_LIVE_TESTS=1` for live tests; remove any "scrapes `_next/data`" wording.

- [ ] **Step 7: Run the full suite**

Run:
```bash
.venv/bin/python -m unittest discover -v
```
Expected: all tests PASS; the live `test` cases report `skipped` (no `RUN_LIVE_TESTS`).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: remove _next/data scraper; live tests opt-in; drop requests-html/pyppeteer; docs"
```

---

## Task 8: Deploy and verify in production

**Files:** none (operational task)

- [ ] **Step 1: Set the Beatport credentials as Azure app settings**

The deployed app reads creds from the environment. Set them (run yourself; the values are secrets):
```bash
az webapp config appsettings set \
  --resource-group groove-grind --name groove-grind \
  --settings BEATPORT_USERNAME='kindling970' \
             BEATPORT_PASSWORD='<your-beatport-password>' \
             BEATPORT_CLIENT_ID='0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd'
```

- [ ] **Step 2: Push to main to trigger the Azure deploy**

```bash
git push origin main
```

- [ ] **Step 3: Watch the deploy**

Run:
```bash
gh run watch "$(gh run list --workflow=azure-webapps-python.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```
Expected: workflow conclusion `success` (fast tests pass — no creds needed — then deploy).

- [ ] **Step 4: Verify production now returns data (the original bug)**

Run:
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" "https://groove-grind.azurewebsites.net/search/darude"
curl -s "https://groove-grind.azurewebsites.net/search/darude" | head -c 200; echo
```
Expected: HTTP 200 and JSON containing `"artists"` with Darude — **not** a 503/error and **not** the old 403-driven 500. If it returns a 503 `unavailable`, the official API is also IP-blocked from Azure; set `BEATPORT_PROXY` (the existing env hook) to a residential proxy and redeploy.

---

## Self-Review

- **Spec coverage:** full replacement (Tasks 1-5, 7 remove scraper); differentiated errors by cause (Task 1 taxonomy → Task 4 mapping → Task 5 HTTP/JSON → Task 6 UI); app-level token + refresh (Task 3); `beatport/` package structure (Tasks 1-4); endpoints search/artist/top10/tracks (Task 4); data-flow & stream shape preserved (Task 5); CI-safe unit tests + opt-in live (Tasks 1-5, 7); drop deps + docs (Task 7); deploy + prod verify + proxy fallback note (Task 8). No gaps.
- **Placeholder scan:** every code step contains complete code; commands have expected output; the only `<...>` is the secret password the operator supplies in Task 8.
- **Type consistency:** `TokenManager.get_token()`/`invalidate()`, `BeatportClient.search/get_artist/get_artist_top/iter_artist_tracks`, model `from_api()`/`to_dict()`, and error `code`/`http_status`/`user_message` are used identically across tasks. `_testsupport.single_session_factory` returns `(factory, session)` consistently in Tasks 3-4. `app.beatport` is the patch point in Task 5 tests.
