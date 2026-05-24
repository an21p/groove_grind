import unittest
from curl_cffi.requests import exceptions as cffi_exc
from beatport.client import BeatportClient
from beatport.errors import BeatportRateLimited, BeatportUnavailable, BeatportAuthError
from _testsupport import FakeResponse, single_session_factory


class FakeTokens:
    def __init__(self):
        self.invalidated = 0

    def get_token(self):
        return "TOK"

    def invalidate(self):
        self.invalidated += 1


SEARCH = {"artists": [{"id": 1, "name": "Darude", "slug": "darude", "image": {"uri": "a"}}],
          "labels": [{"id": 2, "name": "Lab", "slug": "lab", "image": {"uri": "l"}}],
          "tracks": [], "releases": []}
ARTIST = {"id": 1, "name": "Darude", "slug": "darude", "image": {"uri": "a"}, "bio": "b"}
TRACK = {"id": 9, "name": "T", "slug": "t", "sample_url": "s", "new_release_date": "2000-01-01",
         "image": {"uri": "i"}, "artists": [], "remixers": [],
         "release": {"id": 1, "name": "r", "image": {"uri": "ri"},
                     "label": {"id": 3, "name": "L", "slug": "l", "image": {"uri": "li"}}}}


def client_for(routes):
    factory, session = single_session_factory(routes)
    return BeatportClient(FakeTokens(), session_factory=factory), session


class ClientHappyPathTest(unittest.TestCase):
    def test_search(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(200, SEARCH))])
        artists, labels = c.search("darude")
        self.assertEqual(artists[0].name, "Darude")
        self.assertEqual(labels[0].name, "Lab")

    def test_get_artist(self):
        c, _ = client_for([("GET", "/catalog/artists/1/", FakeResponse(200, ARTIST))])
        self.assertEqual(c.get_artist(1).bio, "b")

    def test_get_artist_top(self):
        c, _ = client_for([("GET", "/top/10/", FakeResponse(200, {"results": [TRACK]}))])
        top = c.get_artist_top(1, 10)
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].name, "T")

    def test_iter_artist_tracks_paginates(self):
        page1 = FakeResponse(200, {"results": [TRACK], "next": "p2"})
        page2 = FakeResponse(200, {"results": [TRACK], "next": None})
        calls = {"n": 0}

        def tracks_route(**kw):
            calls["n"] += 1
            return page1 if calls["n"] == 1 else page2

        c, _ = client_for([("GET", "/tracks/", tracks_route)])
        pages = list(c.iter_artist_tracks(1))
        self.assertEqual(len(pages), 2)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(pages[0][0].name, "T")


class ClientErrorMappingTest(unittest.TestCase):
    def test_429_raises_rate_limited(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(429))])
        with self.assertRaises(BeatportRateLimited):
            c.search("x")

    def test_500_raises_unavailable(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(503))])
        with self.assertRaises(BeatportUnavailable):
            c.search("x")

    def test_403_raises_unavailable(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(403))])
        with self.assertRaises(BeatportUnavailable):
            c.search("x")

    def test_401_retries_after_invalidate_then_succeeds(self):
        seq = {"n": 0}

        def search_route(**kw):
            seq["n"] += 1
            return FakeResponse(401) if seq["n"] == 1 else FakeResponse(200, SEARCH)

        factory, _ = single_session_factory([("GET", "/catalog/search/", search_route)])
        tokens = FakeTokens()
        c = BeatportClient(tokens, session_factory=factory)
        artists, _ = c.search("x")
        self.assertEqual(artists[0].name, "Darude")
        self.assertEqual(tokens.invalidated, 1)

    def test_401_twice_raises_auth(self):
        c, _ = client_for([("GET", "/catalog/search/", FakeResponse(401))])
        with self.assertRaises(BeatportAuthError):
            c.search("x")

    def test_network_error_raises_unavailable(self):
        def boom(**kw):
            raise cffi_exc.ConnectionError("down")
        c, _ = client_for([("GET", "/catalog/search/", boom)])
        with self.assertRaises(BeatportUnavailable):
            c.search("x")


if __name__ == "__main__":
    unittest.main()
