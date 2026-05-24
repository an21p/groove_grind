def _img(obj):
    """Flatten Beatport's {'image': {'uri': ...}} to a plain URL string."""
    if not obj:
        return ""
    return (obj.get("image") or {}).get("uri", "") or ""


class Artist:
    def __init__(self, id, name, slug="", image="", bio=""):
        self.id = id
        self.name = name
        self.slug = slug
        self.image = image
        self.bio = bio

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            image=_img(data),
            bio=data.get("bio", "") or "",
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug,
                "image": self.image, "bio": self.bio}


class Label:
    def __init__(self, id, name, slug="", image="", bio=""):
        self.id = id
        self.name = name
        self.slug = slug
        self.image = image
        self.bio = bio

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            image=_img(data),
            bio=data.get("bio", "") or "",
        )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "slug": self.slug,
                "image": self.image, "bio": self.bio}


class Track:
    def __init__(self, id, name, slug, artists, remixers, label, image, sample, release_date):
        self.id = id
        self.name = name
        self.slug = slug
        self.artists = artists
        self.remixers = remixers
        self.label = label
        self.image = image
        self.sample = sample
        self.release_date = release_date

    @classmethod
    def from_api(cls, data):
        release = data.get("release") or {}
        label_data = release.get("label") or {}
        label = Label.from_api(label_data) if label_data.get("id") else Label(id=0, name="")
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug", "") or "",
            artists=[Artist.from_api(a) for a in data.get("artists", [])],
            remixers=[Artist.from_api(r) for r in data.get("remixers", [])],
            label=label,
            image=_img(data) or _img(release),
            sample=data.get("sample_url") or "",
            release_date=data.get("new_release_date") or "",
        )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "artists": [a.to_dict() for a in self.artists],
            "remixers": [r.to_dict() for r in self.remixers],
            "label": self.label.to_dict(),
            "image": self.image,
            "sample": self.sample,
            "release_date": self.release_date,
        }
