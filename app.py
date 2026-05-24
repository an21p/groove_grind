from flask import Flask, send_from_directory, Response, stream_with_context
from dotenv import load_dotenv
from toolz import groupby
from beatport import BeatportClient, TokenManager, BeatportError
import json
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

PUBLIC_CLIENT_ID = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"

_tokens = TokenManager(
    username=os.environ.get("BEATPORT_USERNAME", ""),
    password=os.environ.get("BEATPORT_PASSWORD", ""),
    client_id=os.environ.get("BEATPORT_CLIENT_ID", PUBLIC_CLIENT_ID),
)
beatport = BeatportClient(_tokens)


def _error_body(err):
    return {"error": {"code": err.code, "message": err.user_message}}


@app.route("/")
def base():
    return send_from_directory("client/public", "index.html")


@app.route("/<path:path>")
def home(path):
    return send_from_directory("client/public", path)


@app.route("/search/<term>")
def search(term):
    try:
        artists, labels = beatport.search(term)
    except BeatportError as e:
        app.logger.warning("search failed: %s", e)
        return _error_body(e), e.http_status
    return {
        "artists": [a.to_dict() for a in artists],
        "labels": [lbl.to_dict() for lbl in labels],
    }


@app.route("/artist/<slug>/<id>/labels")
def get_artist(slug, id):
    def gen():
        try:
            artist = beatport.get_artist(id)
            top10 = beatport.get_artist_top(id, 10)
            yield json.dumps({
                "type": "artist",
                "artist": artist.to_dict(),
                "top10": [t.to_dict() for t in top10],
            }) + "\n"

            all_tracks = []
            for page in beatport.iter_artist_tracks(id):
                all_tracks.extend(page)
                yield json.dumps({
                    "type": "tracks",
                    "tracks": [t.to_dict() for t in page],
                    "cumulative": len(all_tracks),
                }) + "\n"

            sorted_tracks = sorted(all_tracks, key=lambda t: t.release_date)
            grouped = groupby(lambda t: t.label.name, sorted_tracks)
            labels_by_date = sorted(
                [{
                    "label": grouped[k][0].label.to_dict(),
                    "date": min(t.release_date for t in grouped[k]),
                } for k in grouped],
                key=lambda item: item["date"],
            )
            all_groups = [
                {"label": grouped[k][0].label.to_dict(),
                 "tracks": [t.to_dict() for t in grouped[k]]}
                for k in grouped
            ]
            yield json.dumps({
                "type": "done",
                "labelsByDate": labels_by_date,
                "all": all_groups,
            }) + "\n"
        except BeatportError as e:
            app.logger.warning("artist stream failed: %s", e)
            yield json.dumps({"type": "error", "code": e.code,
                              "message": e.user_message}) + "\n"
        except Exception:
            app.logger.exception("artist stream crashed")
            yield json.dumps({"type": "error", "code": "error",
                              "message": "Something went wrong. Please try again."}) + "\n"

    return Response(stream_with_context(gen()), mimetype="application/x-ndjson")


if __name__ == "__main__":
    app.run(debug=True)
