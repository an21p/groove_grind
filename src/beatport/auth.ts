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
