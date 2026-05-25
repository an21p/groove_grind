import logging
import threading
import time
from urllib.parse import urlparse, parse_qs

from .curl_transport import CurlError, default_session
from .errors import BeatportAuthError, BeatportUnavailable

logger = logging.getLogger(__name__)

API_BASE = "https://api.beatport.com/v4"
LOGIN_URL = f"{API_BASE}/auth/login/"
AUTHORIZE_URL = f"{API_BASE}/auth/o/authorize/"
TOKEN_URL = f"{API_BASE}/auth/o/token/"
REDIRECT_URI = f"{API_BASE}/auth/o/post-message/"
EXPIRY_BUFFER_SECONDS = 60
HTTP_TIMEOUT = 30
# No User-Agent override: a spoofed browser UA ("Mozilla/5.0") on curl's TLS
# fingerprint is exactly what Cloudflare flags as a bot from datacenter IPs
# (bare curl, with its honest curl/x.y UA, passed our Azure probe). Let curl
# send its default UA.
HEADERS = {"Accept": "application/json"}


class TokenManager:
    """Obtains and caches one Beatport API access token per process,
    refreshing it before expiry. Thread-safe."""

    def __init__(self, username, password, client_id,
                 session_factory=default_session, clock=time.monotonic):
        self._username = username
        self._password = password
        self._client_id = client_id
        self._session_factory = session_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._access_token = None
        self._refresh_token = None
        self._expiry = 0.0

    def get_token(self):
        with self._lock:
            if self._access_token and self._clock() < self._expiry:
                return self._access_token
            if self._refresh_token:
                try:
                    self._refresh()
                    return self._access_token
                except BeatportAuthError:
                    logger.warning("Beatport token refresh rejected; falling back to full re-auth")
            self._authorize()
            return self._access_token

    def invalidate(self):
        with self._lock:
            self._access_token = None
            self._expiry = 0.0

    def _store(self, data):
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._expiry = self._clock() + data.get("expires_in", 36000) - EXPIRY_BUFFER_SECONDS

    def _refresh(self):
        try:
            with self._session_factory() as s:
                s.headers.update(HEADERS)
                r = s.post(TOKEN_URL, params={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                }, timeout=HTTP_TIMEOUT)
        except CurlError as e:
            raise BeatportUnavailable(str(e))
        if r.status_code != 200 or "access_token" not in r.text:
            raise BeatportAuthError(f"refresh failed: HTTP {r.status_code}")
        self._store(r.json())

    def _authorize(self):
        try:
            with self._session_factory() as s:
                s.headers.update(HEADERS)
                r = s.post(LOGIN_URL,
                           json={"username": self._username, "password": self._password},
                           timeout=HTTP_TIMEOUT)
                if r.status_code != 200:
                    raise BeatportAuthError(f"login failed: HTTP {r.status_code}")
                data = r.json()
                if "username" not in data or "email" not in data:
                    raise BeatportAuthError("login rejected (invalid credentials)")

                r = s.get(AUTHORIZE_URL, params={
                    "response_type": "code",
                    "client_id": self._client_id,
                    "redirect_uri": REDIRECT_URI,
                }, allow_redirects=False, timeout=HTTP_TIMEOUT)
                codes = parse_qs(urlparse(r.headers.get("Location", "")).query).get("code")
                if not codes:
                    raise BeatportAuthError("no authorization code in redirect")

                r = s.post(TOKEN_URL, params={
                    "code": codes[0],
                    "grant_type": "authorization_code",
                    "redirect_uri": REDIRECT_URI,
                    "client_id": self._client_id,
                }, timeout=HTTP_TIMEOUT)
                if r.status_code != 200 or "access_token" not in r.text:
                    raise BeatportAuthError(f"token exchange failed: HTTP {r.status_code}")
                self._store(r.json())
        except CurlError as e:
            raise BeatportUnavailable(str(e))
