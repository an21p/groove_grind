#!/usr/bin/env python

# Live end-to-end tests against the real Beatport API.
# Skipped unless RUN_LIVE_TESTS=1 and BEATPORT_* credentials are present.
# RUN_LIVE_TESTS=1 .venv/bin/python -m unittest test -v

import os
import unittest

from dotenv import load_dotenv

load_dotenv()

from beatport import BeatportClient, TokenManager  # noqa: E402

PUBLIC_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

_RUN = (
    os.environ.get("RUN_LIVE_TESTS") == "1"
    and bool(os.environ.get("BEATPORT_USERNAME"))
    and bool(os.environ.get("BEATPORT_PASSWORD"))
)


@unittest.skipUnless(_RUN, "set RUN_LIVE_TESTS=1 (+ BEATPORT_* creds) to run live tests")
class LiveBeatportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tokens = TokenManager(
            username=os.environ["BEATPORT_USERNAME"],
            password=os.environ["BEATPORT_PASSWORD"],
            client_id=os.environ.get("BEATPORT_CLIENT_ID", PUBLIC_CLIENT_ID),
        )
        cls.client = BeatportClient(tokens)

    def test_search_returns_artists(self):
        artists, _ = self.client.search("darude")
        self.assertTrue(any(a.name.lower() == "darude" for a in artists))

    def test_artist_detail_has_bio_field(self):
        artist = self.client.get_artist(3812)  # Darude
        self.assertEqual(artist.id, 3812)
        self.assertIsInstance(artist.bio, str)

    def test_artist_top_returns_tracks(self):
        top = self.client.get_artist_top(3812, 10)
        self.assertTrue(top)
        self.assertTrue(top[0].name)

    def test_iter_artist_tracks_first_page(self):
        first = next(self.client.iter_artist_tracks(3812))
        self.assertTrue(first)            # page has at least one track
        self.assertTrue(first[0].name)    # track is populated (name always present)


if __name__ == "__main__":
    unittest.main()
