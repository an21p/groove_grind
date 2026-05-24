import unittest
import requests
from beatport.auth import TokenManager
from beatport.errors import BeatportAuthError, BeatportUnavailable
from _testsupport import FakeResponse, single_session_factory

LOGIN_OK = FakeResponse(200, {"username": "kindling970", "email": "x@y.z"})
AUTHORIZE_OK = FakeResponse(302, headers={"Location": "https://x/post-message/?code=AC123"})


def token_route(**kwargs):
    grant = kwargs["params"]["grant_type"]
    if grant == "refresh_token":
        return FakeResponse(200, {"access_token": "TOK2", "refresh_token": "RT2", "expires_in": 36000})
    return FakeResponse(200, {"access_token": "TOK1", "refresh_token": "RT1", "expires_in": 36000})


def routes():
    return [
        ("POST", "/auth/login/", LOGIN_OK),
        ("GET", "/auth/o/authorize/", AUTHORIZE_OK),
        ("POST", "/auth/o/token/", token_route),
    ]


class TokenManagerTest(unittest.TestCase):
    def _mgr(self, route_list, clock_holder):
        factory, session = single_session_factory(route_list)
        mgr = TokenManager("u", "p", "cid",
                           session_factory=factory,
                           clock=lambda: clock_holder[0])
        return mgr, session

    def test_full_auth_returns_token(self):
        mgr, session = self._mgr(routes(), [1000.0])
        self.assertEqual(mgr.get_token(), "TOK1")
        methods = [c[0] for c in session.calls]
        self.assertIn("POST", methods)

    def test_cached_token_reused_without_relogin(self):
        mgr, session = self._mgr(routes(), [1000.0])
        mgr.get_token()
        before = len(session.calls)
        self.assertEqual(mgr.get_token(), "TOK1")
        self.assertEqual(len(session.calls), before)  # no new HTTP

    def test_expired_token_is_refreshed(self):
        clock = [1000.0]
        mgr, session = self._mgr(routes(), clock)
        self.assertEqual(mgr.get_token(), "TOK1")
        logins_before = sum(1 for c in session.calls if "/auth/login/" in c[1])
        clock[0] += 40000  # past the 10h expiry
        self.assertEqual(mgr.get_token(), "TOK2")  # came from refresh_token route
        logins_after = sum(1 for c in session.calls if "/auth/login/" in c[1])
        self.assertEqual(logins_after, logins_before)  # refresh, not re-login

    def test_login_failure_raises_auth(self):
        bad = [("POST", "/auth/login/", FakeResponse(403, {"error": "nope"}))]
        mgr, _ = self._mgr(bad, [1000.0])
        with self.assertRaises(BeatportAuthError):
            mgr.get_token()

    def test_network_error_raises_unavailable(self):
        def boom():
            class S:
                headers = {}
                def __enter__(self): return self
                def __exit__(self, *a): return False
                def post(self, *a, **k): raise requests.RequestException("down")
                def get(self, *a, **k): raise requests.RequestException("down")
            return S()
        mgr = TokenManager("u", "p", "cid", session_factory=boom, clock=lambda: 1000.0)
        with self.assertRaises(BeatportUnavailable):
            mgr.get_token()


if __name__ == "__main__":
    unittest.main()
