import requests

from .auth import API_BASE, HEADERS, HTTP_TIMEOUT
from .errors import BeatportAuthError, BeatportRateLimited, BeatportUnavailable
from .models import Artist, Label, Track


class BeatportClient:
    def __init__(self, token_manager, base=API_BASE, session_factory=requests.Session):
        self._tokens = token_manager
        self._base = base
        self._session_factory = session_factory

    def _get(self, path, params=None, _retry=True):
        headers = dict(HEADERS)
        headers["Authorization"] = f"Bearer {self._tokens.get_token()}"
        try:
            with self._session_factory() as s:
                r = s.get(f"{self._base}{path}", params=params or {},
                          headers=headers, timeout=HTTP_TIMEOUT)
        except requests.RequestException as e:
            raise BeatportUnavailable(str(e))

        if r.status_code == 200:
            return r.json()
        if r.status_code == 401 and _retry:
            self._tokens.invalidate()
            return self._get(path, params=params, _retry=False)
        if r.status_code == 401:
            raise BeatportAuthError("HTTP 401 after token refresh")
        if r.status_code == 429:
            raise BeatportRateLimited()
        raise BeatportUnavailable(f"HTTP {r.status_code}")

    def search(self, q):
        data = self._get("/catalog/search/", {"q": q})
        artists = [Artist.from_api(a) for a in data.get("artists", [])]
        labels = [Label.from_api(l) for l in data.get("labels", [])]
        return artists, labels

    def get_artist(self, id):
        return Artist.from_api(self._get(f"/catalog/artists/{id}/"))

    def get_artist_top(self, id, count=10):
        data = self._get(f"/catalog/artists/{id}/top/{count}/")
        return [Track.from_api(t) for t in data.get("results", [])]

    def iter_artist_tracks(self, id, per_page=150):
        page = 1
        while True:
            data = self._get(f"/catalog/artists/{id}/tracks/",
                             {"page": page, "per_page": per_page})
            results = data.get("results", [])
            yield [Track.from_api(t) for t in results]
            if not data.get("next") or not results:
                break
            page += 1
