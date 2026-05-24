import unittest
from beatport.models import Artist, Label, Track

ARTIST_JSON = {
    "id": 3812, "name": "Darude", "slug": "darude",
    "image": {"uri": "http://img/darude.jpg"}, "bio": "Finnish DJ",
}
TRACK_JSON = {
    "id": 99, "name": "Sandstorm", "slug": "sandstorm",
    "sample_url": "http://s/x.mp3", "new_release_date": "2000-01-01",
    "image": {"uri": "http://img/track.jpg"},
    "artists": [{"id": 3812, "name": "Darude", "slug": "darude",
                 "image": {"uri": "http://img/d.jpg"}}],
    "remixers": [],
    "release": {
        "id": 1, "name": "Sandstorm EP", "slug": "sandstorm-ep",
        "image": {"uri": "http://img/rel.jpg"},
        "label": {"id": 7, "name": "16 Inch", "slug": "16-inch",
                  "image": {"uri": "http://img/lab.jpg"}},
    },
}


class ArtistModelTest(unittest.TestCase):
    def test_from_api_to_dict(self):
        d = Artist.from_api(ARTIST_JSON).to_dict()
        self.assertEqual(d, {"id": 3812, "name": "Darude", "slug": "darude",
                             "image": "http://img/darude.jpg", "bio": "Finnish DJ"})

    def test_missing_bio_defaults_empty(self):
        d = Artist.from_api({"id": 1, "name": "X", "slug": "x", "image": {}}).to_dict()
        self.assertEqual(d["bio"], "")
        self.assertEqual(d["image"], "")


class TrackModelTest(unittest.TestCase):
    def test_from_api_to_dict(self):
        d = Track.from_api(TRACK_JSON).to_dict()
        self.assertEqual(d["id"], 99)
        self.assertEqual(d["name"], "Sandstorm")
        self.assertEqual(d["sample"], "http://s/x.mp3")
        self.assertEqual(d["release_date"], "2000-01-01")
        self.assertEqual(d["image"], "http://img/track.jpg")
        self.assertEqual(d["artists"][0]["name"], "Darude")
        self.assertEqual(d["remixers"], [])
        self.assertEqual(d["label"], {"id": 7, "name": "16 Inch", "slug": "16-inch",
                                      "image": "http://img/lab.jpg", "bio": ""})

    def test_track_image_falls_back_to_release_image(self):
        data = dict(TRACK_JSON); data["image"] = {}
        self.assertEqual(Track.from_api(data).to_dict()["image"], "http://img/rel.jpg")

    def test_missing_label_yields_placeholder(self):
        data = dict(TRACK_JSON); data["release"] = {"id": 1, "name": "r", "image": {}}
        d = Track.from_api(data).to_dict()
        self.assertEqual(d["label"]["id"], 0)
        self.assertEqual(d["label"]["name"], "")

    def test_label_without_id_yields_placeholder(self):
        data = dict(TRACK_JSON)
        data["release"] = dict(TRACK_JSON["release"])
        data["release"]["label"] = {"name": "No ID Label"}  # id missing
        d = Track.from_api(data).to_dict()
        self.assertEqual(d["label"]["id"], 0)
        self.assertEqual(d["label"]["name"], "")


if __name__ == "__main__":
    unittest.main()
