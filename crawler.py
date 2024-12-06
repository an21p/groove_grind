from datetime import date, timedelta
from typing import Tuple, List
from json import loads, dumps
from pprint import pprint
from requests_html import HTMLSession
from requests import get
from re import compile

def check(status):
    if status == 404:
        raise Exception('404')
    
def flatten(xss):
    return [x for xs in xss for x in xs]

class Track:
    def __init__(self, data):
        self.data = data
        self.artists = [Artist(a) for a in data['artists']]
        self.remixers = [Artist(a) for a in data['remixers']]
        self.label = Label(data['release']['label'])
        self.name = data['name']
        self.bpm = data['bpm']
        self.image = data['release']['image']['uri']
        self.slug = data['slug']
        self.release_date = data['new_release_date']
        self.sample = data['sample_url']
        self.genre = data['genre']
        self.sub_genre = data['sub_genre']
        self.genre = data['genre']
    def __repr__(self):
        return f"{self.name} by {[a.name for a in self.artists]} remixed by {[a.name for a in self.remixers]} released on {self.label.name}"
    def toJSON(self):
        return dumps(
            {'name': self.name, 'id': self.id, 'slug': self.slug},
            default=lambda o: o.__dict__, 
            skipkeys=True,
            sort_keys=True,
            indent=4)
    # def __hash__(self):
    #     return hash((self.name, self.artists, self.label, self.bpm))
    # def __eq__(self, other):
    #     if isinstance(other, Track):
    #         return self.name == other.name \
    #             and self.bpm == other.bpm \
    #             and self.artists == other.artists \
    #             and self.release_date == other.release_date 
    #     return False

class Artist:
    def __init__(self, data):
        self.top10 = []
        self.data = data
        self.bio = data['bio'] if 'bio' in data else ""
        self.id = data['id'] if 'id' in data else data['artist_id']
        self.image = data['image']['uri'] if 'image' in data else data['artist_image_uri']
        self.name = data['name'] if 'name' in data else data['artist_name']
        self.slug = data['slug'] if 'slug' in data else self.name.lower().replace(' ', '-')
    def __repr__(self):
        return f"{self.name} [{self.slug}/{self.id}]"    
    def enrich(self, beatport, per_page:int=150, all:bool=True):
        self.tracks = beatport.get_tracks_by_artist(slug=self.slug, id=self.id, per_page=per_page, all=all)
        a, self.top10 = beatport.get_artist(slug=self.slug,id=self.id)
        self.bio = a.bio
        self.slug = a.slug
    def toJSON(self):
        return dumps(
            {'name': self.name, 'id': self.id, 'slug': self.slug},
            default=lambda o: o.__dict__, 
            skipkeys=True,
            sort_keys=True,
            indent=4)
    # def __hash__(self):
    #     return hash((self.name, self.id, self.slug))
    # def __eq__(self, other):
    #     if isinstance(other, Artist):
    #         return self.name == other.name \
    #             and self.id == other.id \
    #             and self.slug == other.slug 
    #     return False
        
class Label:
    def __init__(self, data):
        self.top10 = []
        self.data = data
        self.bio = data['bio'] if 'bio' in data else ""
        self.id = data['id'] if 'id' in data else data['label_id']
        self.image = data['image']['uri'] if 'image' in data else data['label_image_uri']
        self.name = data['name'] if 'name' in data else data['label_name']
        self.slug = data['slug'] if 'slug' in data else self.name.lower().replace(' ', '-')
    def __repr__(self):
        return f"{self.name} [{self.slug}/{self.id}]"
    def enrich(self, beatport, per_page:int=150, all:bool=True):
        self.tracks = beatport.get_tracks_by_label(slug=self.slug, id=self.id, per_page=per_page, all=all)
        l, self.top10 = beatport.get_label(slug=self.slug,id=self.id)
        self.bio = l.bio
        self.slug = l.slug
    def toJSON(self):
        return dumps(
            {'name': self.name, 'id': self.id, 'slug': self.slug},
            default=lambda o: o.__dict__, 
            skipkeys=True,
            sort_keys=True,
            indent=4)
    # def __hash__(self):
    #     return hash((self.name, self.id, self.slug))
    # def __eq__(self, other):
    #     if isinstance(other, Label):
    #         return self.name == other.name \
    #             and self.id == other.id \
    #             and self.slug == other.slug 
    #     return False

class Beatport:
    def __init__(self, key=None):
        self.__key = self.unlock() if key is None else key
        self.__tracks_link = 'https://www.beatport.com/_next/data/{key}/en/genre/{slug}/{id}/tracks.json'
        self.__artist_track_link = 'https://www.beatport.com/_next/data/{key}/en/artist/{slug}/{id}/tracks.json'
        self.__artist_link = 'https://www.beatport.com/_next/data/{key}/en/artist/{slug}/{id}.json'
        self.__label_link = 'https://www.beatport.com/_next/data/{key}/en/label/{slug}/{id}.json'
        self.__label_track_link = 'https://www.beatport.com/_next/data/{key}/en/label/{slug}/{id}/tracks.json'
        self.__search_link = 'https://www.beatport.com/_next/data/{key}/en/search.json'
        self.__headers =  {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0',
            'Accept': '*/*',
            'Accept-Language': 'en-GB,en;q=0.5',
            # 'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://www.beatport.com/'
        }
    def __repr__(self):
        return f"Beatport [{self.__key}]"
    def get_key(self):
        return self.__key
    def unlock(self):
        print('unlocking')
        uri = 'https://www.beatport.com'
        pattern = 'src\=\"\/_next\/static\/([a-zA-Z0-9]+)\/_buildManifest\.js'
        session = HTMLSession()
        r = session.get(uri)
        compiled = compile(pattern)
        ms = compiled.search(r.text)
        key = ms.group(1).strip()
        return key
    def search(self, q:str='darude') -> Tuple[List[Artist], List[Label]]:
        headers = self.__headers
        params = {
            'q': f'{q}',
        }
        response = get(
            self.__search_link.format(key=self.__key),
            params=params,
            headers=headers
        )
        check(response.status_code)
        response =  loads(response.text)
        artists_response = response['pageProps']['dehydratedState']['queries'][0]['state']['data']['artists']['data']
        labels_response = response['pageProps']['dehydratedState']['queries'][0]['state']['data']['labels']['data']
        return [Artist(x) for x in artists_response], [Label(x) for x in labels_response]
    def get_tracks_by_genre(self, slug:str='tech-house', id:int=11, date_from:date=date.today() - timedelta(days=1), date_to:date=date.today, page:int=1) -> List[Track]:
        headers = self.__headers
        params = {
            'description': f'{slug}',
            'id': f'{id}',
            'publish_date':  'f{date_from}:{date_to}', #'2024-11-28:2024-11-30',
            'page': f'{page}',
            'per_page': '150',
        }
        response = get(
            self.__tracks_link.format(key=self.__key, slug=slug, id=id),
            params=params,
            headers=headers,
        )
        check(response.status_code)
        response = loads(response.text)
        tracks = response['pageProps']['dehydratedState']['queries'][1]['state']['data']['results']
        return [Track(track) for track in tracks]
    def get_tracks_by_artist(self, slug:str='john-summit', id:int=610028, per_page:int=150, all:bool=True) -> List[Track]:
        headers = self.__headers
        page = 1
        params = {
            'description': f'{slug}',
            'id': f'{id}',
            'page': f'{page}',
            'per_page': f'{per_page}',
        }
        tracks = []
        while True:
            response = get(
                self.__artist_track_link.format(key=self.__key, slug=slug, id=id),
                params=params,
                headers=headers
            )
            
            page += 1
            params['page'] = f'{page}'
            response = loads(response.text)
            tracks.append(response['pageProps']['dehydratedState']['queries'][1]['state']['data']['results'])
            next_page = response['pageProps']['dehydratedState']['queries'][1]['state']['data']['next']
            if next_page is None or all is False:
                break
        return  [Track(track) for track in flatten(tracks)]
    def get_tracks_by_label(self, slug:str='nipplekiss-records', id:int=53231, per_page:int=150, all:bool=False) -> List[Track]:
        headers = self.__headers
        page = 1
        params = {
            'description': f'{slug}',
            'id': f'{id}',
            'page': f'{page}',
            'per_page': f'{per_page}',
        }
        tracks = []
        while True:
            response = get(
                self.__label_track_link.format(key=self.__key, slug=slug, id=id),
                params=params,
                headers=headers
            )
            
            page += 1
            params['page'] = f'{page}'
            response = loads(response.text)
            tracks.append(response['pageProps']['dehydratedState']['queries'][1]['state']['data']['results'])
            next_page = response['pageProps']['dehydratedState']['queries'][1]['state']['data']['next']
            if next_page is None or all is False:
                break
        return  [Track(track) for track in flatten(tracks)]
    def get_artist(self, slug:str, id:int) -> Tuple[Artist, List[Track]]:
        headers = self.__headers
        response = get(
            self.__artist_link.format(key=self.__key, slug=slug, id=id),
            headers= headers,
        )
        response = loads(response.text)
        main = response['pageProps']['dehydratedState']['queries'][0]['state']['data']
        tracks = response['pageProps']['dehydratedState']['queries'][2]['state']['data']['results']
        top10 = [Track(track) for track in tracks]
        main = Artist(main)
        return main, top10
    def get_label(self, slug:str, id:int) -> Tuple[Label, List[Track]]:
        headers = self.__headers
        response = get(
            self.__label_link.format(key=self.__key, slug=slug, id=id),
            headers= headers,
        )
        response = loads(response.text)
        main = response['pageProps']['dehydratedState']['queries'][0]['state']['data']
        tracks = response['pageProps']['dehydratedState']['queries'][2]['state']['data']['results']
        top10 = [Track(track) for track in tracks]
        main = Label(main)
        return main, top10

if __name__ == "__main__":
    b = Beatport()

    ar, _ = b.search('darude')
    darude = ar[0]
    darude.enrich(b)
    pprint(darude.tracks)
    print(len(darude.tracks))
    # [print(t) for t in map(lambda x: [x.label.name, x.release_date, x.name, x.sample], darude.tracks)]

    _, lb = b.search('realm')
    realm = lb[0]
    realm.enrich(b)
    pprint(realm.tracks)
    print(len(realm.tracks))

