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
