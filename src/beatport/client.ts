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
