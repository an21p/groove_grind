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
      image: { uri: 'http://x/waveform.jpg' }, // track image = waveform
      release: { label: { id: 5, name: 'Lbl' }, image: { uri: 'http://x/cover.jpg' } },
    });
    expect(t.sample).toBe('http://x/s.mp3');
    expect(t.release_date).toBe('2021-01-01');
    expect(t.label.name).toBe('Lbl');
    expect(t.image).toBe('http://x/cover.jpg'); // prefers album cover over waveform
    expect(t.artists[0].name).toBe('A');
    expect(t.remixers[0].name).toBe('R');
  });
  it('trackFromApi falls back to the track image when the release has no cover', () => {
    const t = trackFromApi({ id: 9, name: 'Trk', image: { uri: 'http://x/wave.jpg' }, release: {} });
    expect(t.image).toBe('http://x/wave.jpg');
  });
  it('trackFromApi falls back to empty label when release has none', () => {
    const t = trackFromApi({ id: 9, name: 'Trk', release: {} });
    expect(t.label).toEqual({ id: 0, name: '', slug: '', image: '', bio: '' });
  });
});
