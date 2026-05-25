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
    image: img(release) || img(data), // album cover first, waveform only as fallback
    sample: data.sample_url || '',
    release_date: data.new_release_date || '',
  };
}
