#!/usr/bin/env python

# python -m unittest discover -v                     (fast tests only)
# RUN_LIVE_TESTS=1 python -m unittest discover -v    (includes live Beatport)

import os
import unittest
from crawler import Beatport


@unittest.skipUnless(os.getenv('RUN_LIVE_TESTS'),
                     'set RUN_LIVE_TESTS=1 to run live Beatport tests')
class BeatportTestCase(unittest.TestCase):

    def setUp(self):
        self.beatport = Beatport()
        pass

    def tearDown(self):
        pass

    def test_get_artist(self):
        """Should be able to fetch an artist by search"""
        a, _= self.beatport.search('john summit')
        john = a[0]
        name = john.name
        self.assertEqual(name, 'John Summit')
    
    def test_get_label(self):
        """Should be able to fetch an label by search"""
        _, l = self.beatport.search('realm')
        realm = l[0]
        name = realm.name
        self.assertEqual(name, 'REALM Records')

    def test_get_artist_tracks(self):
        """Should be able to fetch an artists list of tracks"""
        a, _= self.beatport.search('john summit')
        john = a[0]
        john.enrich(self.beatport)
        self.assertEqual(len(john.top10), 10)
        self.assertEqual(len(john.tracks), 25)

    def test_get_artist_tracks(self):
        """Should be able to fetch an label list of tracks"""
        _, l = self.beatport.search('realm')
        realm = l[0]
        realm.enrich(self.beatport, per_page=25, all=False)
        self.assertEqual(len(realm.top10), 10)
        self.assertEqual(len(realm.tracks), 25)


if __name__ == '__main__':
    unittest.main()