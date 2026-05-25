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
