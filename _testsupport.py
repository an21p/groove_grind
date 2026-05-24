import json as _json


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=None):
        self.status_code = status_code
        self._json = {} if json_data is None else json_data
        self.headers = headers or {}
        self.text = text if text is not None else _json.dumps(self._json)

    def json(self):
        return self._json


class FakeSession:
    """Routes GET/POST to canned responses by URL substring.

    routes: list of (method, url_substring, resp) where resp is a FakeResponse
    or a callable(**request_kwargs) -> FakeResponse. First match (in order) wins.
    Records every call in .calls as (method, url, kwargs).
    """

    def __init__(self, routes):
        self.routes = list(routes)
        self.headers = {}
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _handle(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        for m, sub, resp in self.routes:
            if m == method and sub in url:
                return resp(**kwargs) if callable(resp) else resp
        raise AssertionError(f"no fake route for {method} {url}")

    def get(self, url, **kwargs):
        return self._handle("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._handle("POST", url, kwargs)


def single_session_factory(routes):
    """Return (factory, session): factory() always yields the same FakeSession,
    so calls accumulate across TokenManager/_get invocations for assertions."""
    session = FakeSession(routes)
    return (lambda: session), session
