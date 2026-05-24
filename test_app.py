import os
import unittest

os.environ.setdefault("FLASK_SECRET_KEY", "test")

import app  # noqa: E402
from beatport.errors import BeatportUnavailable  # noqa: E402
from beatport.models import Artist, Label, Track  # noqa: E402


def _track(name, label_name, date):
    return Track(
        id=hash(name) & 0xffff, name=name, slug=name.lower(),
        artists=[Artist(1, "A", "a", "")], remixers=[],
        label=Label(id=hash(label_name) & 0xffff, name=label_name, slug=label_name.lower(), image=""),
        image="", sample="", release_date=date,
    )


class FakeClient:
    def __init__(self, search_result=None, exc=None, artist=None, top10=None, track_pages=None,
                 artist_exc=None):
        self._search_result = search_result
        self._exc = exc
        self._artist = artist
        self._top10 = top10 or []
        self._track_pages = track_pages or []
        self._artist_exc = artist_exc

    def search(self, q):
        if self._exc:
            raise self._exc
        return self._search_result

    def get_artist(self, id):
        if self._artist_exc:
            raise self._artist_exc
        return self._artist

    def get_artist_top(self, id, count=10):
        return self._top10

    def iter_artist_tracks(self, id, per_page=150):
        for page in self._track_pages:
            yield page


class SearchRouteTest(unittest.TestCase):
    def setUp(self):
        self.http = app.app.test_client()
        self._orig = app.beatport

    def tearDown(self):
        app.beatport = self._orig

    def test_search_ok(self):
        app.beatport = FakeClient(search_result=(
            [Artist(1, "Darude", "darude", "img")],
            [Label(2, "Lab", "lab", "img2")],
        ))
        r = self.http.get("/search/darude")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["artists"][0]["name"], "Darude")
        self.assertEqual(d["labels"][0]["name"], "Lab")

    def test_search_empty_is_200_no_error(self):
        app.beatport = FakeClient(search_result=([], []))
        r = self.http.get("/search/zzzznope")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["artists"], [])
        self.assertNotIn("error", d)

    def test_search_unavailable_returns_503_error(self):
        app.beatport = FakeClient(exc=BeatportUnavailable())
        r = self.http.get("/search/darude")
        self.assertEqual(r.status_code, 503)
        d = r.get_json()
        self.assertEqual(d["error"]["code"], "unavailable")
        self.assertIn("unavailable", d["error"]["message"].lower())


import json


class ArtistStreamTest(unittest.TestCase):
    def setUp(self):
        self.http = app.app.test_client()
        self._orig = app.beatport

    def tearDown(self):
        app.beatport = self._orig

    def _events(self, resp):
        return [json.loads(line) for line in resp.data.decode().splitlines() if line.strip()]

    def test_stream_emits_artist_tracks_done(self):
        app.beatport = FakeClient(
            artist=Artist(1, "Darude", "darude", "img", bio="b"),
            top10=[_track("Sandstorm", "16 Inch", "2000-01-01")],
            track_pages=[[_track("Sandstorm", "16 Inch", "2000-01-01"),
                          _track("Feel The Beat", "Neo", "2001-01-01")]],
        )
        r = self.http.get("/artist/darude/1/labels")
        self.assertEqual(r.status_code, 200)
        events = self._events(r)
        self.assertEqual([e["type"] for e in events], ["artist", "tracks", "done"])
        done = events[-1]
        self.assertIn("labelsByDate", done)
        self.assertIn("all", done)
        # two distinct labels grouped, earliest-first in labelsByDate
        self.assertEqual(done["labelsByDate"][0]["date"], "2000-01-01")
        self.assertEqual({g["label"]["name"] for g in done["all"]}, {"16 Inch", "Neo"})

    def test_stream_error_event_when_artist_fails(self):
        from beatport.errors import BeatportUnavailable
        app.beatport = FakeClient(artist_exc=BeatportUnavailable())
        r = self.http.get("/artist/darude/1/labels")
        self.assertEqual(r.status_code, 200)  # stream opens; error is an event
        events = self._events(r)
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(events[-1]["code"], "unavailable")


if __name__ == "__main__":
    unittest.main()
