#!/usr/bin/env python

# Fast tests (no network). Run by CI before deploy.
# python -m unittest test_fast -v

import os
import unittest

os.environ.setdefault('FLASK_SECRET_KEY', 'test')


class AppImportTest(unittest.TestCase):
    def test_app_imports(self):
        import app
        from flask import Flask
        self.assertIsInstance(app.app, Flask)


class CrawlerImportTest(unittest.TestCase):
    def test_crawler_imports(self):
        from crawler import Beatport, Artist, Label, Track, to_dict
        for symbol in (Beatport, Artist, Label, Track, to_dict):
            self.assertTrue(symbol)


class ModelSerializationTest(unittest.TestCase):
    def test_models_to_dict(self):
        from crawler import Artist, Label, Track, to_dict

        artist_data = {
            'id': 1,
            'name': 'Test Artist',
            'slug': 'test-artist',
            'image': {'uri': 'http://example.com/a.jpg'},
            'bio': 'a bio',
        }
        label_data = {
            'id': 2,
            'name': 'Test Label',
            'slug': 'test-label',
            'image': {'uri': 'http://example.com/l.jpg'},
        }
        track_data = {
            'id': 3,
            'name': 'Test Track',
            'slug': 'test-track',
            'bpm': 128,
            'new_release_date': '2024-01-01',
            'sample_url': 'http://example.com/s.mp3',
            'genre': {'name': 'Techno'},
            'sub_genre': None,
            'artists': [artist_data],
            'remixers': [],
            'release': {
                'label': label_data,
                'image': {'uri': 'http://example.com/r.jpg'},
            },
        }

        a = Artist(artist_data)
        self.assertEqual(a.to_dict()['name'], 'Test Artist')
        self.assertEqual(a.to_dict()['slug'], 'test-artist')

        l = Label(label_data)
        self.assertEqual(l.to_dict()['name'], 'Test Label')

        t = Track(track_data)
        td = t.to_dict()
        self.assertEqual(td['name'], 'Test Track')
        self.assertEqual(td['label']['name'], 'Test Label')
        self.assertEqual(td['artists'][0]['name'], 'Test Artist')

        serialized = to_dict([a])
        self.assertEqual(len(serialized), 1)
        self.assertEqual(serialized[0]['name'], 'Test Artist')


if __name__ == '__main__':
    unittest.main()
