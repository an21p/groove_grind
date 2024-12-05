from flask import Flask, send_from_directory, g, request
import random
import urllib.parse
import requests
import json

app = Flask(__name__)


def get_key():
    if 'key' not in g:
        g.key = init_key()

    return g.key

def init_key():
    client_id = "0GIvkCltVIuPkkwSJHp6NDb3s0potTjLBQr388Dd"
    redirect_uri = urllib.parse.quote_plus("http://127.0.0.1:5000/callback")
    beatport_link = f"https://api.beatport.com/v4/auth/o/authorize/?client_id={client_id}&response_type=code&redirect_uri={redirect_uri}"
    # response = requests.post(beatport_link)
    # print(response.text)
    
    return {'client_id': client_id, 'beatport_link': beatport_link}

# Path for our main Svelte page
@app.route("/")
def base():
    return send_from_directory('client/public', 'index.html')

# Path for all the static files (compiled JS/CSS, etc.)
@app.route("/<path:path>")
def home(path):
    return send_from_directory('client/public', path)


@app.route("/rand")
def rand():
    key = get_key()
    print(key)
    bl = key['beatport_link']
    return bl



@app.route("/callback")
def callback():
    code = request.args.get('code')
    print(request)


if __name__ == "__main__":
    app.run(debug=True)
