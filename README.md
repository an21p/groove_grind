# Groove Grid

## API - Flask
- Search for artists via Beatport API
- Get all tracks of an artist
- Get all labels an artist has released on
- Get top 10 tracks of an artist

### TODO
- Get all tracks of a label
- Get all artists of a label
- Get top 10 tracks of a label

## Front-end - Svelte
- Made to facilitate the use of the API

#### Svelte.js + Flask
Run the following for development:

- `python server.py` to start the Flask server.
- `cd client; npm install; npm run autobuild` to automatically build and reload the Svelte frontend when it's changed.

- `python -m venv .venv`
- `source .venv/bin/activate`
- `python -m pip install -r requirements.txt`
- `python -m pip freeze`
- `deactivate`
