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
