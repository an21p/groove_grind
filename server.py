from flask import Flask, send_from_directory, session, flash
from typing import Tuple, List, Any
from crawler import Beatport, Label, Artist, Track, to_dict
from datetime import datetime, timedelta, timezone
from toolz import groupby

app = Flask(__name__)
app.secret_key = 'make_this_an_env'

# wrapper
def handle_beatport(func):
    def handler(*args, **kwargs):
        session['beatport'] = session.get('beatport', Beatport().get_key())
        session['expiry'] = session.get('expiry', datetime.now(timezone.utc) + timedelta(hours=12))
        if datetime.now(timezone.utc) > session['expiry']:
            print('-----> expired:')
            session['beatport'] = Beatport().get_key()
            session['expiry'] =  datetime.now() + timedelta(seconds=1)

        print(['-----> beatport key,expiry:', session['beatport'], session['expiry']])
        return func(*args, **kwargs)
    return handler


def get_beatport() -> Beatport:
    key=session.get('beatport', "")
    return Beatport(key=key)

def get_all_artist_labels_by_date(b: Beatport, slug: str, id: str) -> Tuple[Artist, Any, List[Track]]:
    a, top10 = b.get_artist(slug=slug, id=id)
    a.enrich(beatport=b)
    s = sorted(a.tracks, key=lambda x:x.release_date)
    g = groupby(lambda x: x.label.name, s)
    return a, g, top10

# Path for our main Svelte page
@app.route('/')
def base():
    return send_from_directory('client/public', 'index.html')

# Path for all the static files (compiled JS/CSS, etc.)
@app.route("/<path:path>")
def home(path):
    return send_from_directory('client/public', path)

@app.route("/search/<term>")
def search(term):
    return do_search(term)

@app.route("/artist/<slug>/<id>/labels")
def get_artist(slug, id):
    return do_get_artist(slug, id)



@handle_beatport
def do_search(term):
    artists, labels = get_beatport().search(term)
    return {'artists': to_dict(artists), 'labels': to_dict(labels)}

@handle_beatport
def do_get_artist(slug, id):
    artist, g, top10 = get_all_artist_labels_by_date(get_beatport(), slug=slug, id=id)
    labels_by_date = list(
        sorted(map(lambda item: {'label':item[1][0].label.to_dict(), 
                                'date': min(map(lambda track:track.release_date, item[1]))}, 
                    g.items()), 
                key=lambda item: item['date']))
    return {'top10': to_dict(top10), 
            'labelsByDate': labels_by_date, 
            'all': [{'label': g[k][0].label.to_dict(), 'tracks': to_dict(g[k])} for k in g],
            'artist': artist.to_dict()}  

if __name__ == "__main__":
    app.run(debug=True)
    # b = Beatport()
    # artists, labels = b.search('chris ger')
    # a = artists[0]
    # a, g, top10 = get_all_artist_labels_by_date(b, slug=a.slug, id=a.id)
    # labels_by_date = list(
    #     sorted(map(lambda item: {'label':item[1][0].label.to_dict(), 
    #                             'date': min(map(lambda track:track.release_date, item[1]))}, 
    #                 g.items()), 
    #             key=lambda item: item['date']))
    # print(labels_by_date)

    

