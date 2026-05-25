# Static Browser-Auth Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Groove Grind from a Flask-served SPA into a pure static Svelte app where each user authenticates to Beatport in their own browser, eliminating the Azure datacenter 403.

**Architecture:** All Beatport logic (auth, client, models, errors, artist-stream orchestration) moves into a TypeScript `src/beatport/` package that runs in the browser. Each user logs in via a Beatport popup (with a manual token-paste fallback); their browser holds the token and calls `api.beatport.com/v4` directly. The repo is flattened so it *is* the Svelte app, built by Rollup and deployed to Azure Static Web Apps. The UI's existing `{type}` streaming-event protocol is preserved so `App.svelte` changes minimally.

**Tech Stack:** Svelte 3, Rollup 2, TypeScript (added), Vitest + jsdom (added), Azure Static Web Apps.

**Spec:** `docs/superpowers/specs/2026-05-25-beatport-static-browser-auth-design.md`

**Commit convention:** Every commit message ends with the trailer `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` (omitted from the example commands below for brevity — add it). Work happens on the `feat/static-browser-auth` branch (already created).

---

## File Structure

After this plan, the repo root is the Svelte app:

```
.
├── index.html                 (moved from client/public, served as SPA root)
├── package.json               (moved from client/, + ts/vitest deps & scripts)
├── rollup.config.js           (moved from client/, + typescript plugin)
├── tsconfig.json              (new)
├── vitest.config.ts           (new)
├── staticwebapp.config.json   (new — SPA fallback for Azure SWA)
├── src/
│   ├── main.js                (unchanged)
│   ├── App.svelte             (fetch() calls swapped for client/catalog calls + login gate)
│   ├── beatport/
│   │   ├── errors.ts          (← beatport/errors.py)
│   │   ├── models.ts          (← beatport/models.py)
│   │   ├── client.ts          (← beatport/client.py)
│   │   ├── auth.ts            (← beatport/auth.py: token store + popup + manual)
│   │   └── catalog.ts         (← app.py get_artist generator)
│   └── stores/
│       └── session.ts         (Svelte store wrapping AuthManager + BeatportClient)
├── public/                    (Rollup build output: bundle.js/.css)
├── spike/auth-popup.html      (Task 1 spike harness)
├── docs/superpowers/...       (spec + this plan + spike notes)
└── .github/workflows/azure-static-web-apps.yml  (new — replaces python workflow)
```

Deleted: `app.py`, `requirements.txt`, `beatport/` (Python), `test*.py`, `_testsupport.py`, `research.ipynb`, `__pycache__/`, `.github/workflows/azure-webapps-python.yml`, the `client/` directory shell.

---

## Task 1: Auth spike — confirm popup flow OR produce the manual snippet (DECISION GATE)

This is investigation, not TDD. Its output gates the auth UI design in Tasks 9 and 12.

**Files:**
- Create: `spike/auth-popup.html`
- Create: `docs/superpowers/spike-auth-notes.md`

- [ ] **Step 1: Create the spike harness**

Create `spike/auth-popup.html`:

```html
<!doctype html>
<html>
  <body>
    <button id="go">Open Beatport login popup</button>
    <pre id="log"></pre>
    <script>
      const CID = '0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd';
      const RURI = 'https://api.beatport.com/v4/auth/o/post-message/';
      const log = (...a) =>
        (document.getElementById('log').textContent +=
          a.map((x) => (typeof x === 'object' ? JSON.stringify(x) : x)).join(' ') + '\n');
      window.addEventListener('message', (e) =>
        log('message FROM origin=', e.origin, ' data=', e.data),
      );
      document.getElementById('go').onclick = () => {
        const u = new URL('https://api.beatport.com/v4/auth/o/authorize/');
        u.searchParams.set('response_type', 'code');
        u.searchParams.set('client_id', CID);
        u.searchParams.set('redirect_uri', RURI);
        window.open(u.toString(), 'bp', 'width=480,height=720');
      };
    </script>
  </body>
</html>
```

- [ ] **Step 2: Serve and exercise it**

Run: `python3 -m http.server 8080 --directory spike`
Open `http://localhost:8080/auth-popup.html` in a browser where you can log in to Beatport. Click the button, complete login, and watch the `<pre>` log.

Expected (popup works): a line `message FROM origin= https://api.beatport.com data= {"code":"..."}` (or similar) appears — meaning the relay `postMessage`s the code back to our window.
Expected (popup locked): no `message` arrives, or it targets only a beatport.com origin (nothing logged in our window).

- [ ] **Step 3: Record the decision and the manual snippet**

Create `docs/superpowers/spike-auth-notes.md` documenting:
1. Whether a `message` arrived, its exact `origin`, and the exact shape of `e.data` (the property holding the code).
2. **If popup works:** the precise `origin` string to validate against and the `e.data` code property name — Task 9 uses these.
3. **If popup is locked:** the working console command a user runs (logged in at beatport.com) to obtain their access token, recorded verbatim as the value for `MANUAL_TOKEN_SNIPPET` in Task 9. Determine it during this step by trying, in the beatport.com devtools console: reading the token the web app stores, and/or a `fetch(..., {credentials:'include'})` against the authorize/token endpoints. Record whichever works.

- [ ] **Step 4: Commit**

```bash
git add spike/auth-popup.html docs/superpowers/spike-auth-notes.md
git commit -m "spike: confirm Beatport browser auth flow + record manual snippet"
```

---

## Task 2: Remove the Flask/Python backend

**Files:**
- Delete: `app.py`, `requirements.txt`, `_testsupport.py`, `test.py`, `test_app.py`, `test_auth.py`, `test_client.py`, `test_errors.py`, `test_fast.py`, `test_models.py`, `research.ipynb`, `beatport/` (Python package), `__pycache__/`

- [ ] **Step 1: Delete the Python backend and tests**

Run:
```bash
git rm app.py requirements.txt _testsupport.py \
       test.py test_app.py test_auth.py test_client.py test_errors.py test_fast.py test_models.py \
       research.ipynb
git rm -r beatport
git rm -r --ignore-unmatch __pycache__
```

- [ ] **Step 2: Remove server secrets from local `.env`**

`.env` is gitignored (not tracked). Manually edit it to delete `FLASK_SECRET_KEY` and the `BEATPORT_USERNAME`/`BEATPORT_PASSWORD`/`BEATPORT_CLIENT_ID`/`BEATPORT_PROXY` lines — the static app has no server secrets. (If `.env` becomes empty, leave it.)

- [ ] **Step 3: Verify no Python references remain**

Run: `git ls-files | grep -E '\.py$'`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove Flask backend and Python beatport package"
```

---

## Task 3: Flatten `client/` to the repo root

**Files:**
- Move: `client/{package.json,package-lock.json,rollup.config.js,src,public}` → repo root
- Delete: root `package-lock.json` stub, the `client/` directory

- [ ] **Step 1: Remove the root stub lockfile, then move client files up**

The repo root has a 27-byte placeholder `package-lock.json`; remove it so the real one can move up.

Run:
```bash
git rm package-lock.json
git mv client/package.json package.json
git mv client/package-lock.json package-lock.json
git mv client/rollup.config.js rollup.config.js
git mv client/src src
git mv client/public public
```

- [ ] **Step 2: Merge .gitignore and remove the client shell**

Append Node ignores to the root `.gitignore` if absent (add these lines if not already present):
```
node_modules/
public/bundle.js
public/bundle.css
public/bundle.js.map
public/bundle.css.map
```
Then remove leftover untracked client contents:
```bash
rm -rf client
```

- [ ] **Step 3: Verify the build still works from root**

Run: `npm install && npm run build`
Expected: Rollup writes `public/bundle.js` and `public/bundle.css` with no errors. (`rollup.config.js` input `src/main.js` and output `public/bundle.js` are now root-relative — unchanged.)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: flatten client/ to repo root"
```

---

## Task 4: Add TypeScript + Vitest toolchain

**Files:**
- Modify: `package.json` (devDeps + scripts)
- Modify: `rollup.config.js` (typescript plugin)
- Create: `tsconfig.json`
- Create: `vitest.config.ts`

- [ ] **Step 1: Install dev dependencies**

Run:
```bash
npm install -D typescript tslib @rollup/plugin-typescript vitest jsdom
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 3: Wire the typescript plugin into `rollup.config.js`**

Add the import at the top:
```js
import typescript from '@rollup/plugin-typescript';
```
Add `typescript()` to the `plugins` array, immediately after the `svelte({...})` plugin block:
```js
		typescript({ sourceMap: !production, inlineSources: !production }),
```

- [ ] **Step 4: Create `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
  },
});
```

- [ ] **Step 5: Add test scripts to `package.json`**

In the `"scripts"` block add:
```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 6: Verify the toolchain runs**

Run: `npm test`
Expected: Vitest starts and reports "No test files found" (no `*.test.ts` exist yet) and exits 0.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json rollup.config.js tsconfig.json vitest.config.ts
git commit -m "build: add TypeScript and Vitest toolchain"
```

---

## Task 5: Port `errors.ts`

**Files:**
- Create: `src/beatport/errors.ts`
- Test: `src/beatport/errors.test.ts`

- [ ] **Step 1: Write the failing test**

`src/beatport/errors.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import {
  BeatportError,
  BeatportUnavailable,
  BeatportRateLimited,
  BeatportAuthError,
} from './errors';

describe('errors', () => {
  it('base is an Error with default code/message', () => {
    const e = new BeatportError();
    expect(e instanceof Error).toBe(true);
    expect(e.code).toBe('error');
    expect(e.userMessage).toContain('Something went wrong');
  });
  it('unavailable maps copy and code', () => {
    const e = new BeatportUnavailable();
    expect(e.code).toBe('unavailable');
    expect(e.userMessage).toContain('temporarily unavailable');
  });
  it('rate limited maps code', () => {
    expect(new BeatportRateLimited().code).toBe('rate_limited');
  });
  it('auth maps code', () => {
    expect(new BeatportAuthError().code).toBe('auth');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- errors`
Expected: FAIL — cannot resolve `./errors`.

- [ ] **Step 3: Write the implementation**

`src/beatport/errors.ts`:
```ts
export class BeatportError extends Error {
  code = 'error';
  userMessage = 'Something went wrong talking to Beatport.';
  constructor(message?: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class BeatportUnavailable extends BeatportError {
  code = 'unavailable';
  userMessage = 'Beatport is temporarily unavailable. Please try again in a moment.';
}

export class BeatportRateLimited extends BeatportError {
  code = 'rate_limited';
  userMessage = 'Beatport is busy right now. Please retry in a few seconds.';
}

export class BeatportAuthError extends BeatportError {
  code = 'auth';
  userMessage = "We're having trouble connecting to Beatport — we're on it.";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- errors`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/errors.ts src/beatport/errors.test.ts
git commit -m "feat: port beatport errors to TypeScript"
```

---

## Task 6: Port `models.ts`

**Files:**
- Create: `src/beatport/models.ts`
- Test: `src/beatport/models.test.ts`

- [ ] **Step 1: Write the failing test**

`src/beatport/models.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { artistFromApi, labelFromApi, trackFromApi } from './models';

describe('models', () => {
  it('artistFromApi flattens image and defaults slug/bio', () => {
    const a = artistFromApi({ id: 1, name: 'Foo', image: { uri: 'http://x/i.jpg' } });
    expect(a).toEqual({ id: 1, name: 'Foo', slug: '', image: 'http://x/i.jpg', bio: '' });
  });
  it('labelFromApi handles missing image', () => {
    const l = labelFromApi({ id: 2, name: 'Bar' });
    expect(l.image).toBe('');
  });
  it('trackFromApi maps sample_url, new_release_date, and release.label', () => {
    const t = trackFromApi({
      id: 9,
      name: 'Trk',
      artists: [{ id: 1, name: 'A' }],
      remixers: [{ id: 2, name: 'R' }],
      sample_url: 'http://x/s.mp3',
      new_release_date: '2021-01-01',
      release: { label: { id: 5, name: 'Lbl' }, image: { uri: 'http://x/cover.jpg' } },
    });
    expect(t.sample).toBe('http://x/s.mp3');
    expect(t.release_date).toBe('2021-01-01');
    expect(t.label.name).toBe('Lbl');
    expect(t.image).toBe('http://x/cover.jpg');
    expect(t.artists[0].name).toBe('A');
    expect(t.remixers[0].name).toBe('R');
  });
  it('trackFromApi falls back to empty label when release has none', () => {
    const t = trackFromApi({ id: 9, name: 'Trk', release: {} });
    expect(t.label).toEqual({ id: 0, name: '', slug: '', image: '', bio: '' });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- models`
Expected: FAIL — cannot resolve `./models`.

- [ ] **Step 3: Write the implementation**

`src/beatport/models.ts`:
```ts
export interface Artist {
  id: number | string;
  name: string;
  slug: string;
  image: string;
  bio: string;
}
export interface Label {
  id: number | string;
  name: string;
  slug: string;
  image: string;
  bio: string;
}
export interface Track {
  id: number | string;
  name: string;
  slug: string;
  artists: Artist[];
  remixers: Artist[];
  label: Label;
  image: string;
  sample: string;
  release_date: string;
}

function img(obj: any): string {
  if (!obj) return '';
  return (obj.image && obj.image.uri) || '';
}

export function artistFromApi(data: any): Artist {
  return {
    id: data.id,
    name: data.name,
    slug: data.slug || '',
    image: img(data),
    bio: data.bio || '',
  };
}

export function labelFromApi(data: any): Label {
  return {
    id: data.id,
    name: data.name,
    slug: data.slug || '',
    image: img(data),
    bio: data.bio || '',
  };
}

export function trackFromApi(data: any): Track {
  const release = data.release || {};
  const labelData = release.label || {};
  const label: Label = labelData.id
    ? labelFromApi(labelData)
    : { id: 0, name: '', slug: '', image: '', bio: '' };
  return {
    id: data.id,
    name: data.name,
    slug: data.slug || '',
    artists: (data.artists || []).map(artistFromApi),
    remixers: (data.remixers || []).map(artistFromApi),
    label,
    image: img(data) || img(release),
    sample: data.sample_url || '',
    release_date: data.new_release_date || '',
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- models`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/models.ts src/beatport/models.test.ts
git commit -m "feat: port beatport models to TypeScript"
```

---

## Task 7: Port `client.ts`

**Files:**
- Create: `src/beatport/client.ts`
- Test: `src/beatport/client.test.ts`

- [ ] **Step 1: Write the failing test**

`src/beatport/client.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BeatportClient } from './client';
import { BeatportAuthError, BeatportRateLimited } from './errors';

const okJson = (body: any) => ({ status: 200, json: async () => body });
const fakeTokens = () => ({ getToken: vi.fn(async () => 'tok'), invalidate: vi.fn() });

describe('BeatportClient', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('search maps artists and labels', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => okJson({ artists: [{ id: 1, name: 'A' }], labels: [{ id: 2, name: 'L' }] })),
    );
    const c = new BeatportClient(fakeTokens() as any);
    const { artists, labels } = await c.search('x');
    expect(artists[0].name).toBe('A');
    expect(labels[0].id).toBe(2);
  });

  it('retries once after a 401 then succeeds', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ status: 401, json: async () => ({}) })
      .mockResolvedValueOnce(okJson({ artists: [], labels: [] }));
    vi.stubGlobal('fetch', fetchMock);
    const tokens = fakeTokens();
    await new BeatportClient(tokens as any).search('x');
    expect(tokens.invalidate).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('throws BeatportAuthError on a second 401', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 401, json: async () => ({}) })));
    await expect(new BeatportClient(fakeTokens() as any).search('x')).rejects.toBeInstanceOf(
      BeatportAuthError,
    );
  });

  it('throws BeatportRateLimited on 429', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ status: 429, json: async () => ({}) })));
    await expect(new BeatportClient(fakeTokens() as any).search('x')).rejects.toBeInstanceOf(
      BeatportRateLimited,
    );
  });

  it('iterArtistTracks stops when next is null', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson({ results: [{ id: 1, name: 't1' }], next: 'p2' }))
      .mockResolvedValueOnce(okJson({ results: [{ id: 2, name: 't2' }], next: null }));
    vi.stubGlobal('fetch', fetchMock);
    const c = new BeatportClient(fakeTokens() as any);
    const pages: any[] = [];
    for await (const p of c.iterArtistTracks(7)) pages.push(p);
    expect(pages.length).toBe(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- client`
Expected: FAIL — cannot resolve `./client`.

- [ ] **Step 3: Write the implementation**

`src/beatport/client.ts`:
```ts
import { artistFromApi, labelFromApi, trackFromApi, type Artist, type Label, type Track } from './models';
import { BeatportAuthError, BeatportRateLimited, BeatportUnavailable } from './errors';

export const API_BASE = 'https://api.beatport.com/v4';

export interface TokenProvider {
  getToken(): Promise<string>;
  invalidate(): void;
}

export class BeatportClient {
  constructor(private tokens: TokenProvider, private base = API_BASE) {}

  private async get(path: string, params: Record<string, any> = {}, retry = true): Promise<any> {
    const token = await this.tokens.getToken();
    const url = new URL(`${this.base}${path}`);
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, String(v));

    let res: Response;
    try {
      res = await fetch(url.toString(), {
        headers: { Accept: 'application/json', Authorization: `Bearer ${token}` },
      });
    } catch (e) {
      throw new BeatportUnavailable(String(e));
    }

    if (res.status === 200) return res.json();
    if (res.status === 401 && retry) {
      this.tokens.invalidate();
      return this.get(path, params, false);
    }
    if (res.status === 401) throw new BeatportAuthError('HTTP 401 after token refresh');
    if (res.status === 429) throw new BeatportRateLimited();
    throw new BeatportUnavailable(`HTTP ${res.status}`);
  }

  async search(q: string): Promise<{ artists: Artist[]; labels: Label[] }> {
    const data = await this.get('/catalog/search/', { q });
    return {
      artists: (data.artists || []).map(artistFromApi),
      labels: (data.labels || []).map(labelFromApi),
    };
  }

  async getArtist(id: string | number): Promise<Artist> {
    return artistFromApi(await this.get(`/catalog/artists/${id}/`));
  }

  async getArtistTop(id: string | number, count = 10): Promise<Track[]> {
    const data = await this.get(`/catalog/artists/${id}/top/${count}/`);
    return (data.results || []).map(trackFromApi);
  }

  async *iterArtistTracks(id: string | number, perPage = 150): AsyncGenerator<Track[]> {
    let page = 1;
    while (true) {
      const data = await this.get(`/catalog/artists/${id}/tracks/`, { page, per_page: perPage });
      const results = data.results || [];
      yield results.map(trackFromApi);
      if (!data.next || results.length === 0) break;
      page += 1;
    }
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- client`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/client.ts src/beatport/client.test.ts
git commit -m "feat: port beatport API client to TypeScript"
```

---

## Task 8: `auth.ts` core — token store, refresh, manual token

This task builds everything in `auth.ts` *except* the popup handshake (Task 9). The popup `login()` method is added in Task 9.

**Files:**
- Create: `src/beatport/auth.ts`
- Test: `src/beatport/auth.test.ts`

- [ ] **Step 1: Write the failing test**

`src/beatport/auth.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthManager } from './auth';
import { BeatportAuthError } from './errors';

function memStorage(): Storage {
  const m = new Map<string, string>();
  return {
    getItem: (k) => (m.has(k) ? (m.get(k) as string) : null),
    setItem: (k, v) => void m.set(k, v),
    removeItem: (k) => void m.delete(k),
    clear: () => m.clear(),
    key: () => null,
    get length() {
      return m.size;
    },
  } as Storage;
}

describe('AuthManager', () => {
  beforeEach(() => vi.unstubAllGlobals());

  it('returns the cached token before expiry', async () => {
    let t = 1000;
    const a = new AuthManager('cid', memStorage(), () => t);
    (a as any).store({ access_token: 'A', refresh_token: 'R', expires_in: 100 });
    expect(await a.getToken()).toBe('A');
    expect(a.isAuthenticated()).toBe(true);
  });

  it('refreshes when expired and a refresh token exists', async () => {
    let t = 0;
    const a = new AuthManager('cid', memStorage(), () => t);
    (a as any).store({ access_token: 'A', refresh_token: 'R', expires_in: 100 });
    t = 1_000_000;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        status: 200,
        json: async () => ({ access_token: 'B', refresh_token: 'R2', expires_in: 100 }),
      })),
    );
    expect(await a.getToken()).toBe('B');
  });

  it('manual token returns until invalidated, then throws auth error', async () => {
    let t = 0;
    const a = new AuthManager('cid', memStorage(), () => t);
    a.setTokenManually('M');
    t = 999_999_999;
    expect(await a.getToken()).toBe('M');
    a.invalidate();
    await expect(a.getToken()).rejects.toBeInstanceOf(BeatportAuthError);
  });

  it('persists across instances via storage', async () => {
    const storage = memStorage();
    let t = 0;
    const a = new AuthManager('cid', storage, () => t);
    (a as any).store({ access_token: 'A', refresh_token: 'R', expires_in: 100 });
    const b = new AuthManager('cid', storage, () => t);
    expect(b.isAuthenticated()).toBe(true);
    expect(await b.getToken()).toBe('A');
  });

  it('logout clears stored token', async () => {
    const storage = memStorage();
    const a = new AuthManager('cid', storage, () => 0);
    (a as any).store({ access_token: 'A', refresh_token: 'R', expires_in: 100 });
    a.logout();
    expect(a.isAuthenticated()).toBe(false);
    expect(storage.getItem('groovegrind.token')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- auth`
Expected: FAIL — cannot resolve `./auth`.

- [ ] **Step 3: Write the implementation**

`src/beatport/auth.ts`:
```ts
import { BeatportAuthError, BeatportUnavailable } from './errors';
import type { TokenProvider } from './client';

export const API_BASE = 'https://api.beatport.com/v4';
export const TOKEN_URL = `${API_BASE}/auth/o/token/`;
export const AUTHORIZE_URL = `${API_BASE}/auth/o/authorize/`;
export const REDIRECT_URI = `${API_BASE}/auth/o/post-message/`;
export const PUBLIC_CLIENT_ID = '0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd';

const EXPIRY_BUFFER_MS = 60_000;
const STORAGE_KEY = 'groovegrind.token';

interface StoredToken {
  access_token: string;
  refresh_token: string | null;
  expiry: number | null; // epoch ms; null = unknown (manual path)
}

export class AuthManager implements TokenProvider {
  private token: StoredToken | null = null;

  constructor(
    private clientId = PUBLIC_CLIENT_ID,
    private storage: Storage = window.localStorage,
    private now: () => number = Date.now,
  ) {
    this.load();
  }

  private load(): void {
    try {
      const raw = this.storage.getItem(STORAGE_KEY);
      this.token = raw ? (JSON.parse(raw) as StoredToken) : null;
    } catch {
      this.token = null;
    }
  }

  private save(): void {
    if (this.token) this.storage.setItem(STORAGE_KEY, JSON.stringify(this.token));
    else this.storage.removeItem(STORAGE_KEY);
  }

  protected store(data: any): void {
    const expiresIn = typeof data.expires_in === 'number' ? data.expires_in : 36000;
    this.token = {
      access_token: data.access_token,
      refresh_token: data.refresh_token ?? this.token?.refresh_token ?? null,
      expiry: this.now() + expiresIn * 1000 - EXPIRY_BUFFER_MS,
    };
    this.save();
  }

  setTokenManually(accessToken: string): void {
    this.token = { access_token: accessToken, refresh_token: null, expiry: null };
    this.save();
  }

  isAuthenticated(): boolean {
    return !!(this.token && this.token.access_token);
  }

  async getToken(): Promise<string> {
    const tok = this.token;
    if (tok && tok.expiry !== null && this.now() < tok.expiry) return tok.access_token;
    if (tok && tok.expiry === null && tok.access_token) return tok.access_token; // manual
    if (tok && tok.refresh_token) {
      await this.refresh();
      return this.token!.access_token;
    }
    throw new BeatportAuthError('not authenticated');
  }

  private async refresh(): Promise<void> {
    const url = new URL(TOKEN_URL);
    url.searchParams.set('grant_type', 'refresh_token');
    url.searchParams.set('refresh_token', this.token!.refresh_token!);
    url.searchParams.set('client_id', this.clientId);
    let res: Response;
    try {
      res = await fetch(url.toString(), { method: 'POST', headers: { Accept: 'application/json' } });
    } catch (e) {
      throw new BeatportUnavailable(String(e));
    }
    if (res.status !== 200) throw new BeatportAuthError(`refresh failed: HTTP ${res.status}`);
    this.store(await res.json());
  }

  invalidate(): void {
    if (this.token) {
      this.token.access_token = '';
      this.token.expiry = 0;
      this.save();
    }
  }

  logout(): void {
    this.token = null;
    this.save();
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- auth`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/auth.ts src/beatport/auth.test.ts
git commit -m "feat: add AuthManager token store, refresh, and manual token"
```

---

## Task 9: `auth.ts` popup login + manual snippet constant

Apply the Task 1 spike findings here. The `origin` guard and `e.data` code property below use the **default-guess** values; replace them with the exact values recorded in `docs/superpowers/spike-auth-notes.md` if they differ.

**Files:**
- Modify: `src/beatport/auth.ts`
- Test: `src/beatport/auth.test.ts` (add a popup test)

- [ ] **Step 1: Add the failing popup test**

Append to `src/beatport/auth.test.ts`:
```ts
describe('AuthManager.login (popup)', () => {
  it('resolves a code via postMessage and exchanges it for a token', async () => {
    let t = 0;
    const a = new AuthManager('cid', memStorage(), () => t);

    const popup = { closed: false, close: vi.fn() };
    vi.stubGlobal('open', vi.fn(() => popup));
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        status: 200,
        json: async () => ({ access_token: 'X', refresh_token: 'RX', expires_in: 100 }),
      })),
    );

    const p = a.login();
    // Simulate the relay posting the code back to our window.
    window.dispatchEvent(
      new MessageEvent('message', { origin: 'https://api.beatport.com', data: { code: 'CODE123' } }),
    );
    await p;

    expect(a.isAuthenticated()).toBe(true);
    expect(await a.getToken()).toBe('X');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- auth`
Expected: FAIL — `a.login is not a function`.

- [ ] **Step 3: Add `login()`, the popup handshake, and the manual snippet**

Add these to `auth.ts`. First, near the top constants, add (paste the exact verified snippet from the spike notes; the string below is the starting default):
```ts
// Console command for the manual-token fallback. Finalized by the Task 1 spike;
// shown to users in the setup section when the popup is unavailable.
export const MANUAL_TOKEN_SNIPPET = `// Run this in the devtools console at https://www.beatport.com while logged in:
copy(JSON.parse(localStorage.getItem('persist:user') || '{}').access_token);
console.log('Access token copied to clipboard (if present).');`;
```

Then add these methods inside the `AuthManager` class:
```ts
  async login(): Promise<void> {
    const code = await this.runPopup();
    await this.exchangeCode(code);
  }

  private runPopup(): Promise<string> {
    return new Promise<string>((resolve, reject) => {
      const url = new URL(AUTHORIZE_URL);
      url.searchParams.set('response_type', 'code');
      url.searchParams.set('client_id', this.clientId);
      url.searchParams.set('redirect_uri', REDIRECT_URI);
      const popup = window.open(url.toString(), 'beatport_login', 'width=480,height=720');
      if (!popup) {
        reject(new BeatportAuthError('popup blocked'));
        return;
      }
      const onMessage = (ev: MessageEvent) => {
        // SPIKE-CONFIRMED: validate the relay's exact origin here.
        if (ev.origin !== 'https://api.beatport.com') return;
        const data = (ev.data || {}) as { code?: string; error?: string };
        if (data.code) {
          cleanup();
          resolve(data.code);
        } else if (data.error) {
          cleanup();
          reject(new BeatportAuthError(String(data.error)));
        }
      };
      const timer = setInterval(() => {
        if (popup.closed) {
          cleanup();
          reject(new BeatportAuthError('login cancelled'));
        }
      }, 500);
      const cleanup = () => {
        window.removeEventListener('message', onMessage);
        clearInterval(timer);
        try {
          popup.close();
        } catch {
          /* ignore */
        }
      };
      window.addEventListener('message', onMessage);
    });
  }

  private async exchangeCode(code: string): Promise<void> {
    const url = new URL(TOKEN_URL);
    url.searchParams.set('code', code);
    url.searchParams.set('grant_type', 'authorization_code');
    url.searchParams.set('redirect_uri', REDIRECT_URI);
    url.searchParams.set('client_id', this.clientId);
    let res: Response;
    try {
      res = await fetch(url.toString(), { method: 'POST', headers: { Accept: 'application/json' } });
    } catch (e) {
      throw new BeatportUnavailable(String(e));
    }
    if (res.status !== 200) throw new BeatportAuthError(`token exchange failed: HTTP ${res.status}`);
    this.store(await res.json());
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- auth`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/auth.ts src/beatport/auth.test.ts
git commit -m "feat: add Beatport popup OAuth login and manual token snippet"
```

---

## Task 10: Port `catalog.ts` (artist-stream orchestration)

**Files:**
- Create: `src/beatport/catalog.ts`
- Test: `src/beatport/catalog.test.ts`

- [ ] **Step 1: Write the failing test**

`src/beatport/catalog.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { streamArtist, type CatalogEvent } from './catalog';

function fakeClient(): any {
  return {
    getArtist: async () => ({ id: 1, name: 'Art', slug: 'art', image: '', bio: '' }),
    getArtistTop: async () => [
      { id: 9, name: 'top', label: { id: 1, name: 'L1' }, release_date: '2020-01-01' },
    ],
    async *iterArtistTracks() {
      yield [{ id: 1, name: 'a', label: { id: 1, name: 'L1' }, release_date: '2021-05-01' }];
      yield [{ id: 2, name: 'b', label: { id: 2, name: 'L2' }, release_date: '2019-01-01' }];
    },
  };
}

describe('streamArtist', () => {
  it('emits artist, a tracks event per page, then done grouped+sorted by date', async () => {
    const events: CatalogEvent[] = [];
    await streamArtist(fakeClient(), 1, (e) => events.push(e));
    expect(events[0].type).toBe('artist');
    expect(events.filter((e) => e.type === 'tracks').length).toBe(2);
    const done = events.find((e) => e.type === 'done') as Extract<CatalogEvent, { type: 'done' }>;
    expect(done.labelsByDate[0].label.name).toBe('L2'); // 2019 is earliest
    expect(done.all.length).toBe(2);
  });

  it('emits an error event when a call throws', async () => {
    const bad: any = {
      getArtist: async () => {
        throw new Error('boom');
      },
    };
    const events: CatalogEvent[] = [];
    await streamArtist(bad, 1, (e) => events.push(e));
    expect(events[0].type).toBe('error');
  });

  it('stops early when the signal is aborted', async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    const events: CatalogEvent[] = [];
    await streamArtist(fakeClient(), 1, (e) => events.push(e), ctrl.signal);
    expect(events.length).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- catalog`
Expected: FAIL — cannot resolve `./catalog`.

- [ ] **Step 3: Write the implementation**

`src/beatport/catalog.ts`:
```ts
import type { BeatportClient } from './client';
import type { Artist, Label, Track } from './models';
import { BeatportError, BeatportUnavailable } from './errors';

export type CatalogEvent =
  | { type: 'artist'; artist: Artist; top10: Track[] }
  | { type: 'tracks'; tracks: Track[]; cumulative: number }
  | {
      type: 'done';
      labelsByDate: { label: Label; date: string }[];
      all: { label: Label; tracks: Track[] }[];
    }
  | { type: 'error'; code: string; message: string };

function groupByLabelName(tracks: Track[]): Map<string, Track[]> {
  const m = new Map<string, Track[]>();
  for (const t of tracks) {
    const k = t.label.name;
    const arr = m.get(k);
    if (arr) arr.push(t);
    else m.set(k, [t]);
  }
  return m;
}

const byDate = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export async function streamArtist(
  client: BeatportClient,
  id: string | number,
  onEvent: (e: CatalogEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  try {
    if (signal?.aborted) return;
    const artist = await client.getArtist(id);
    const top10 = await client.getArtistTop(id, 10);
    if (signal?.aborted) return;
    onEvent({ type: 'artist', artist, top10 });

    const all: Track[] = [];
    for await (const page of client.iterArtistTracks(id)) {
      if (signal?.aborted) return;
      all.push(...page);
      onEvent({ type: 'tracks', tracks: page, cumulative: all.length });
    }

    const sorted = [...all].sort((a, b) => byDate(a.release_date, b.release_date));
    const grouped = groupByLabelName(sorted);
    const keys = [...grouped.keys()];

    const labelsByDate = keys
      .map((k) => {
        const tracks = grouped.get(k)!;
        const earliest = tracks.reduce(
          (min, t) => (t.release_date && t.release_date < min ? t.release_date : min),
          tracks[0].release_date,
        );
        return { label: tracks[0].label, date: earliest };
      })
      .sort((a, b) => byDate(a.date, b.date));

    const allGroups = keys.map((k) => ({ label: grouped.get(k)![0].label, tracks: grouped.get(k)! }));

    onEvent({ type: 'done', labelsByDate, all: allGroups });
  } catch (e) {
    if ((e as any)?.name === 'AbortError' || signal?.aborted) return;
    const err = e instanceof BeatportError ? e : new BeatportUnavailable(String(e));
    onEvent({ type: 'error', code: err.code, message: err.userMessage });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- catalog`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/beatport/catalog.ts src/beatport/catalog.test.ts
git commit -m "feat: port artist-stream orchestration to catalog.ts"
```

---

## Task 11: Session store

**Files:**
- Create: `src/stores/session.ts`

This is a thin wiring module (a Svelte store + singletons). No unit test — it is exercised by the app and by Task 9's auth tests covering the underlying `AuthManager`.

- [ ] **Step 1: Write the module**

`src/stores/session.ts`:
```ts
import { writable } from 'svelte/store';
import { AuthManager, MANUAL_TOKEN_SNIPPET } from '../beatport/auth';
import { BeatportClient } from '../beatport/client';

export const auth = new AuthManager();
export const client = new BeatportClient(auth);
export const manualTokenSnippet = MANUAL_TOKEN_SNIPPET;

export const session = writable<{ connected: boolean }>({ connected: auth.isAuthenticated() });

function sync() {
  session.set({ connected: auth.isAuthenticated() });
}

export async function loginPopup(): Promise<void> {
  await auth.login();
  sync();
}

export function setManualToken(token: string): void {
  auth.setTokenManually(token.trim());
  sync();
}

export function logout(): void {
  auth.logout();
  sync();
}

// Called by UI error handlers when a BeatportAuthError surfaces mid-session.
export function refreshSession(): void {
  sync();
}
```

- [ ] **Step 2: Verify it type-checks via a build**

Run: `npm run build`
Expected: Rollup builds with no TypeScript errors. (App.svelte does not import this yet, but the typescript plugin still checks the file once it is imported in Task 12; this build confirms the module compiles standalone via `npx tsc --noEmit`.)

Also run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/stores/session.ts
git commit -m "feat: add session store wiring AuthManager and BeatportClient"
```

---

## Task 12: Wire `App.svelte` to the client + add the login gate

**Files:**
- Modify: `src/App.svelte`

- [ ] **Step 1: Add imports and a session subscription**

At the top of the `<script>` block in `src/App.svelte`, after the existing `svelte` imports, add:
```js
	import { client, session, loginPopup, setManualToken, logout, refreshSession, manualTokenSnippet } from './stores/session';
	import { streamArtist } from './beatport/catalog';

	let connected = false;
	const unsubSession = session.subscribe((s) => (connected = s.connected));

	// Login-gate UI state
	let showManualSetup = false;
	let manualTokenInput = '';
	let loginError = null;

	async function connect() {
		loginError = null;
		try {
			await loginPopup();
		} catch (e) {
			loginError = (e && e.userMessage) || 'Could not connect. Try the manual setup below.';
			showManualSetup = true;
		}
	}

	function submitManualToken() {
		if (!manualTokenInput.trim()) return;
		setManualToken(manualTokenInput.trim());
		manualTokenInput = '';
	}
```

Add `unsubSession()` to the existing `onMount` cleanup return. The current `onMount` returns `() => clearInterval(id);` — change it to:
```js
		return () => { clearInterval(id); unsubSession(); };
```

- [ ] **Step 2: Replace `search()` body to call the client**

Replace the `fetch('./search/...')` chain inside `search()` with:
```js
		(async () => {
			try {
				const { artists: a, labels: l } = await client.search(searchTerm.trim());
				artists = a;
				labels = l;
				loading = false;
			} catch (e) {
				searchError = (e && e.userMessage) || 'Beatport is temporarily unavailable. Please try again in a moment.';
				if (e && e.code === 'auth') refreshSession();
				loading = false;
			}
		})();
```

- [ ] **Step 3: Replace the streaming body in `openArtist()`**

Inside `openArtist(slug, id)`, replace the `try { const res = await fetch(...) ... }` block (the NDJSON reader loop) with:
```js
		try {
			await streamArtist(client, id, handleStreamEvent, controller.signal);
		} catch (err) {
			if (err && err.name !== 'AbortError') {
				streamError = (err && err.userMessage) || (err && err.message) || String(err);
				if (err && err.code === 'auth') refreshSession();
			}
		} finally {
			if (activeStreamController === controller) activeStreamController = null;
			loading = false;
			streamingCatalog = false;
		}
```
Keep `handleStreamEvent`, `mergeProgressiveTracks`, and all reactive/render code unchanged — `streamArtist` emits the same `{type}` events they already handle.

- [ ] **Step 4: Add the login gate markup**

In the template, wrap the search hero so it only shows when connected, and add the gate when not. Replace the opening of the hero block — change:
```svelte
	{#if !artist}
		<section class="hero">
```
to:
```svelte
	{#if !artist && !connected}
		<section class="hero gate">
			<div class="prompt-line">
				<span class="caps prompt-num">Nº 00</span>
				<span class="prompt-dot"></span>
				<span class="caps prompt-label">Connect</span>
			</div>
			<h2 class="section-title" style="margin-top:1rem;">Connect your <em>Beatport</em> account to dig</h2>
			<p class="dossier-bio" style="margin-top:1rem;">
				Groove &amp; Grind reads the Beatport catalog from your browser, on your connection — nothing runs on a server.
			</p>
			<div class="prompt-hint" style="margin-top:1.5rem;">
				<button class="prompt-go ready" on:click={connect}><span class="caps">Connect Beatport</span><span class="go-arrow">→</span></button>
				<button class="suggest" on:click={() => (showManualSetup = !showManualSetup)}>Can't use the popup? Manual setup</button>
			</div>
			{#if loginError}
				<div class="stream-error caps" style="margin-top:1.25rem;" role="alert">
					<span class="stream-error-label">Connection problem</span>
					<span class="stream-error-msg">{loginError}</span>
				</div>
			{/if}
			{#if showManualSetup}
				<div class="manual-setup">
					<div class="caps mute">Manual token setup</div>
					<ol class="manual-steps">
						<li>Sign in to beatport.com in this browser.</li>
						<li>Open the devtools console and run this command:</li>
					</ol>
					<pre class="manual-snippet">{manualTokenSnippet}</pre>
					<p class="caps mute">Paste the resulting token below. Note: the token expires (about 10 hours) — when it does, you'll be asked to run the command again.</p>
					<div class="prompt-field" style="margin-top:1rem;">
						<input class="prompt-input" bind:value={manualTokenInput} placeholder="paste your Beatport token" autocomplete="off" spellcheck="false" />
						<button class="prompt-go ready" on:click={submitManualToken}><span class="caps">Save</span><span class="go-arrow">→</span></button>
					</div>
				</div>
			{/if}
		</section>
	{/if}

	{#if !artist && connected}
		<section class="hero">
```

- [ ] **Step 5: Add a disconnect control to the footer**

In the footer block, add a disconnect button when connected. Change the first `.foot-row` div to include:
```svelte
			{#if connected}
				<button class="caps mute disconnect" on:click={logout}>Disconnect Beatport</button>
			{/if}
```
(placed inside `.foot-row`, alongside the existing caption divs).

- [ ] **Step 6: Add minimal styles**

In the `<style>` block, add:
```css
	.manual-setup { margin-top: 2rem; padding-top: 1.5rem; border-top: var(--rule-thin); }
	.manual-steps { margin: 1rem 0; padding-left: 1.25rem; color: var(--paper-dim); font-size: 13px; line-height: 1.6; }
	.manual-snippet {
		font-family: var(--mono);
		font-size: 11px;
		color: var(--paper);
		background: var(--ink-2);
		border: 1px solid var(--rule);
		padding: 12px;
		overflow-x: auto;
		white-space: pre-wrap;
	}
	.disconnect { background: none; border: none; cursor: pointer; }
	.disconnect:hover { color: var(--oxide); }
```

- [ ] **Step 7: Build and smoke-test manually**

Run: `npm run build`
Expected: builds with no errors.

Run: `npx sirv-cli public --single --port 5000` and open `http://localhost:5000`.
Expected: the **Connect** gate shows (no token yet); clicking "Manual setup" reveals the snippet + paste field; search input is hidden until connected. (Live popup login requires the Task 1 spike outcome; verify it end-to-end if the popup path was confirmed.)

- [ ] **Step 8: Commit**

```bash
git add src/App.svelte
git commit -m "feat: wire App.svelte to browser client and add login gate"
```

---

## Task 13: Azure Static Web Apps deploy config

**Files:**
- Create: `staticwebapp.config.json`
- Create: `.github/workflows/azure-static-web-apps.yml`
- Delete: `.github/workflows/azure-webapps-python.yml`

- [ ] **Step 1: Create the SPA fallback config**

`staticwebapp.config.json`:
```json
{
  "navigationFallback": {
    "rewrite": "/index.html"
  }
}
```

- [ ] **Step 2: Create the deploy workflow**

`.github/workflows/azure-static-web-apps.yml`:
```yaml
name: Azure Static Web Apps CI/CD

on:
  push:
    branches: [main]
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches: [main]

jobs:
  build_and_deploy:
    if: github.event_name == 'push' || (github.event_name == 'pull_request' && github.event.action != 'closed')
    runs-on: ubuntu-latest
    name: Build and Deploy
    steps:
      - uses: actions/checkout@v4
      - name: Build And Deploy
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          action: upload
          app_location: "/"
          output_location: "public"
          app_build_command: "npm run build"

  close_pull_request:
    if: github.event_name == 'pull_request' && github.event.action == 'closed'
    runs-on: ubuntu-latest
    name: Close Pull Request
    steps:
      - name: Close Pull Request
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
          action: close
```

- [ ] **Step 3: Delete the old Python workflow**

Run: `git rm .github/workflows/azure-webapps-python.yml`

- [ ] **Step 4: Verify the build command the workflow relies on**

Run: `npm install && npm run build`
Expected: `public/bundle.js` and `public/bundle.css` produced. (The SWA action runs `app_build_command` then serves `output_location`.)

- [ ] **Step 5: Commit**

```bash
git add staticwebapp.config.json .github/workflows/azure-static-web-apps.yml
git commit -m "ci: deploy static app to Azure Static Web Apps"
```

> **Manual deploy step (out of band):** create the Azure Static Web App resource, add its deployment token as the `AZURE_STATIC_WEB_APPS_API_TOKEN` GitHub secret, point the custom domain at it, and decommission the old Azure Web App service. Note this in the PR description.

---

## Task 14: Update documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rewrite `CLAUDE.md` for the static app**

Replace the Flask/backend content. The new `CLAUDE.md` must describe:
- **Project overview:** a static Svelte SPA (no server) that reads the Beatport v4 API directly from the user's browser; each user authenticates with their own Beatport account via popup OAuth (manual token fallback).
- **Commands:** `npm install`, `npm run build` (production), `npm run autobuild` (dev rebuild), `npm test` (Vitest). Remove all `uv`/Flask/gunicorn commands.
- **Architecture:** the `src/beatport/` TypeScript package (`auth`, `client`, `models`, `errors`, `catalog`) running in the browser; `src/stores/session.ts`; `App.svelte` consuming the `{type}` events from `catalog.streamArtist`.
- **Auth:** popup OAuth against `api.beatport.com/v4` with the public client id; token in `localStorage`; manual token fallback.
- **Deploy:** Azure Static Web Apps via `.github/workflows/azure-static-web-apps.yml`; SPA fallback in `staticwebapp.config.json`.
- Remove the "Beatport official API server-side" and `FLASK_SECRET_KEY`/`BEATPORT_*` sections entirely.

- [ ] **Step 2: Update `README.md`**

Remove the Flask/Azure-Web-App/gunicorn/`uv` setup sections. Add: static-app overview, `npm install && npm run build` + `npm run autobuild` dev flow, `npm test`, the per-user Beatport login model, and the Azure Static Web Apps deployment note.

- [ ] **Step 3: Verify no stale backend references remain**

Run: `grep -rniE 'flask|gunicorn|uv pip|FLASK_SECRET_KEY|BEATPORT_USERNAME' README.md CLAUDE.md`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document static browser-auth app, drop Flask instructions"
```

---

## Final verification

- [ ] Run the full test suite: `npm test` — expected: all suites pass (errors, models, client, auth, catalog).
- [ ] Run a type check: `npx tsc --noEmit` — expected: no errors.
- [ ] Run a production build: `npm run build` — expected: `public/bundle.js` + `public/bundle.css`, no errors.
- [ ] Confirm no Python remains: `git ls-files | grep -E '\.py$'` — expected: no output.
- [ ] Manually exercise the running app (`npx sirv-cli public --single`): the connect gate shows, manual setup reveals the snippet, and — if the spike confirmed the popup — a full login → search → artist dossier flow works against the live API.

---

## Self-Review Notes (author checklist — completed)

- **Spec coverage:** spike→T1; Flask removal→T2; repo flatten→T3; toolchain→T4; errors→T5; models→T6; client→T7; auth core (token store/refresh/manual)→T8; popup login + manual snippet→T9; catalog orchestration→T10; session store→T11; UI wiring + login gate + manual setup UI→T12; Azure SWA + SPA fallback→T13; README/CLAUDE docs→T14. localStorage choice, expiry buffer, 401-retry, and the no-refresh-on-manual-token behavior are all implemented in T8/T9.
- **Placeholder scan:** the only deferred value is `MANUAL_TOKEN_SNIPPET` / the popup `origin` guard, which the Task 1 spike produces and Tasks 9 reference explicitly with a concrete default — by design, not a gap.
- **Type consistency:** `TokenProvider` (client.ts) is implemented by `AuthManager` (auth.ts); `BeatportClient` methods (`search`/`getArtist`/`getArtistTop`/`iterArtistTracks`) match catalog.ts usage; `CatalogEvent` shapes (`artist`/`tracks`/`done`/`error`) match `App.svelte`'s `handleStreamEvent`; `from_api` field names match what `App.svelte` renders.
