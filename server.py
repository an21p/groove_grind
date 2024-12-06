from flask import Flask, send_from_directory, g, request, session, flash
from crawler import Beatport

app = Flask(__name__)
app.secret_key = 'make_this_an_env'

# Path for our main Svelte page
@app.route('/')
def base():
    session['beatport'] = session.get('beatport', Beatport().get_key())
    return send_from_directory('client/public', 'index.html')


# Path for all the static files (compiled JS/CSS, etc.)
@app.route("/<path:path>")
def home(path):
    return send_from_directory('client/public', path)


@app.route("/init")
def init():
    key=session.get('beatport', "")
    return f'{key}'


@app.route("/search/<term>")
def search(term):
    key=session.get('beatport', "")
    b = Beatport(key=key)
    artists, labels = b.search(term)
    return [a.toJSON() for a in artists]



if __name__ == "__main__":
    app.run(debug=True)
