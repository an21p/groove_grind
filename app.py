from flask import Flask, send_from_directory, session, flash, Response, stream_with_context
from typing import Tuple, List, Any
from crawler import Beatport, Label, Artist, Track, to_dict
from datetime import datetime, timedelta, timezone
from toolz import groupby
import json

app = Flask(__name__)
app.secret_key = 'make_this_an_env'

# wrapper
def handle_beatport(func):
    def handler(*args, **kwargs):
        session['beatport'] = session.get('beatport', Beatport().get_key())
        session['expiry'] = session.get('expiry', datetime.now(timezone.utc) + timedelta(hours=12))
        if datetime.now(timezone.utc) > session['expiry']:
            app.logger.info('-----> expired')
            session['beatport'] = Beatport().get_key()
            session['expiry'] =  datetime.now() + timedelta(seconds=1)

        app.logger.info('-----> beatport key %s ,expiry %s',  session['beatport'], session['expiry'])
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
    b = get_beatport()

    def gen():
        try:
            artist, top10 = b.get_artist(slug=slug, id=id)
            yield json.dumps({
                'type': 'artist',
                'artist': artist.to_dict(),
                'top10': to_dict(top10),
            }) + '\n'

            all_tracks: List[Track] = []
            for page_tracks in b.get_tracks_by_artist_stream(slug=artist.slug, id=artist.id):
                all_tracks.extend(page_tracks)
                yield json.dumps({
                    'type': 'tracks',
                    'tracks': to_dict(page_tracks),
                    'cumulative': len(all_tracks),
                }) + '\n'

            sorted_tracks = sorted(all_tracks, key=lambda t: t.release_date)
            grouped = groupby(lambda t: t.label.name, sorted_tracks)
            labels_by_date = sorted(
                [{
                    'label': grouped[k][0].label.to_dict(),
                    'date': min(t.release_date for t in grouped[k]),
                } for k in grouped],
                key=lambda item: item['date'],
            )
            all_groups = [
                {'label': grouped[k][0].label.to_dict(), 'tracks': to_dict(grouped[k])}
                for k in grouped
            ]
            yield json.dumps({
                'type': 'done',
                'labelsByDate': labels_by_date,
                'all': all_groups,
            }) + '\n'
        except Exception as e:
            app.logger.exception('stream failed')
            yield json.dumps({'type': 'error', 'message': str(e)}) + '\n'

    return Response(stream_with_context(gen()), mimetype='application/x-ndjson')

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

    

