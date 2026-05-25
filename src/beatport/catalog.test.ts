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
