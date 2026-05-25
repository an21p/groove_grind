import { BeatportAuthError, BeatportUnavailable } from './errors';
import type { TokenProvider } from './client';

export const API_BASE = 'https://api.beatport.com/v4';
export const TOKEN_URL = `${API_BASE}/auth/o/token/`;
export const AUTHORIZE_URL = `${API_BASE}/auth/o/authorize/`;
export const REDIRECT_URI = `${API_BASE}/auth/o/post-message/`;
export const PUBLIC_CLIENT_ID = '0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd';

// Console commands for the manual-token fallback (the popup relay is locked to
// beatport.com's own origin, so the popup flow can't return a code to our app).
// beatport.com authenticates with NextAuth and exposes the live Beatport token
// via /api/auth/session — these read it from there.
//
// Token-only: paste a bare access token (expires in ~10 min, no auto-refresh).
export const MANUAL_TOKEN_SNIPPET = `// Run in the devtools console at https://www.beatport.com (logged in):
fetch('/api/auth/session', { credentials: 'include' })
  .then((r) => r.json())
  .then((s) => { copy(s.token.accessToken); console.log('Access token copied.'); });`;

// Full-session: paste a JSON blob with the refresh token so the app can renew
// the short-lived access token without re-pasting.
export const MANUAL_SESSION_SNIPPET = `// Run in the devtools console at https://www.beatport.com (logged in):
fetch('/api/auth/session', { credentials: 'include' })
  .then((r) => r.json())
  .then((s) => {
    copy(JSON.stringify({ access_token: s.token.accessToken, refresh_token: s.token.refreshToken }));
    console.log('Session copied — paste it into Groove Grind.');
  });`;

const EXPIRY_BUFFER_MS = 60_000;
const STORAGE_KEY = 'groovegrind.token';

interface StoredToken {
  access_token: string;
  refresh_token: string | null;
  expiry: number | null; // epoch ms; null = unknown (manual token-only path)
  client_id: string | null; // client to use for refresh (null = manager default)
}

// Best-effort decode of a JWT payload (base64url). Returns {} on any failure.
function decodeJwt(token: string): any {
  try {
    const part = token.split('.')[1];
    if (!part) return {};
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const pad = b64.length % 4 ? '='.repeat(4 - (b64.length % 4)) : '';
    return JSON.parse(atob(b64 + pad));
  } catch (_e) {
    return {};
  }
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
    } catch (_e) {
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
      client_id: this.token?.client_id ?? null,
    };
    this.save();
  }

  setTokenManually(accessToken: string): void {
    this.token = { access_token: accessToken, refresh_token: null, expiry: null, client_id: null };
    this.save();
  }

  // Manual full-session path: store the access + refresh token from beatport.com's
  // /api/auth/session. Expiry and the refresh client_id are read from the JWT so
  // the app can renew the short-lived token against the API.
  setSessionManually(accessToken: string, refreshToken: string): void {
    const claims = decodeJwt(accessToken);
    this.token = {
      access_token: accessToken,
      refresh_token: refreshToken || null,
      expiry: typeof claims.exp === 'number' ? claims.exp * 1000 - EXPIRY_BUFFER_MS : null,
      client_id: typeof claims.client_id === 'string' ? claims.client_id : null,
    };
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
    url.searchParams.set('client_id', this.token!.client_id ?? this.clientId);
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
        // Spike result: the post-message relay is locked to beatport.com's own
        // origin and does not post back to a third-party origin, so this popup
        // path is a non-functional fallback retained for completeness. The
        // manual /api/auth/session path is primary. Origin guard kept regardless.
        if (ev.origin !== 'https://api.beatport.com') return;
        // ev.data may be any serializable value; only object payloads carry a code/error.
        if (!ev.data || typeof ev.data !== 'object' || Array.isArray(ev.data)) return;
        const data = ev.data as { code?: string; error?: string };
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
        } catch (_e) {
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
}
