"""Minimal requests-like HTTP session backed by the OS `curl` binary.

Beatport sits behind Cloudflare, which 403s every in-process Python TLS client
(requests/urllib3 and curl_cffi's BoringSSL builds) from datacenter IPs like
Azure, while the system `curl` binary's fingerprint passes. So we shell out to
`curl`. This class exposes just the slice of the requests/curl_cffi `Session`
API that `beatport.auth` and `beatport.client` use: a `.headers` dict, `.get`
/`.post` (with `params`, `json`, `headers`, `allow_redirects`, `timeout`),
context-manager support, and a response with `.status_code`, `.headers`
(case-insensitive `.get`), `.text`, and `.json()`. Cookies persist across calls
within a session via a per-session cookie jar (needed for login -> authorize).
"""

import json as _json
import os
import subprocess
import tempfile
from urllib.parse import urlencode

CURL_BIN = "curl"


class CurlError(Exception):
    """Raised when the curl subprocess fails (network error, timeout, etc.)."""


class _CIDict(dict):
    def get(self, key, default=None):
        lk = key.lower()
        for k, v in self.items():
            if k.lower() == lk:
                return v
        return default


class _CurlResponse:
    def __init__(self, status_code, headers, text):
        self.status_code = status_code
        self.headers = headers
        self.text = text

    def json(self):
        return _json.loads(self.text)


class CurlSession:
    def __init__(self, timeout=30):
        self.headers = {}
        self._default_timeout = timeout
        jar = tempfile.NamedTemporaryFile(prefix="bp_cookies_", delete=False)
        jar.close()
        self._jar = jar.name

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            os.unlink(self._jar)
        except OSError:
            pass
        return False

    def get(self, url, params=None, headers=None, allow_redirects=True, timeout=None):
        return self._request("GET", url, params=params, headers=headers,
                             allow_redirects=allow_redirects, timeout=timeout)

    def post(self, url, params=None, json=None, headers=None, allow_redirects=True, timeout=None):
        return self._request("POST", url, params=params, json=json, headers=headers,
                             allow_redirects=allow_redirects, timeout=timeout)

    def _request(self, method, url, params=None, json=None, headers=None,
                 allow_redirects=True, timeout=None):
        timeout = timeout or self._default_timeout
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params)

        hdr = tempfile.NamedTemporaryFile(prefix="bp_hdr_", delete=False); hdr.close()
        body = tempfile.NamedTemporaryFile(prefix="bp_body_", delete=False); body.close()

        args = [CURL_BIN, "-s", "-S",
                "-o", body.name,
                "-D", hdr.name,
                "-w", "%{http_code}",
                "-c", self._jar, "-b", self._jar,
                "--max-time", str(timeout)]
        if allow_redirects:
            args.append("-L")
        if method == "POST":
            args += ["-X", "POST"]

        merged = dict(self.headers)
        if headers:
            merged.update(headers)

        stdin_bytes = None
        if json is not None:
            merged.setdefault("Content-Type", "application/json")
            stdin_bytes = _json.dumps(json).encode()
            args += ["--data-binary", "@-"]

        for k, v in merged.items():
            args += ["-H", f"{k}: {v}"]
        args.append(url)

        try:
            proc = subprocess.run(args, input=stdin_bytes, capture_output=True,
                                  timeout=timeout + 5)
        except (subprocess.TimeoutExpired, OSError) as e:
            self._cleanup(hdr.name, body.name)
            raise CurlError(str(e))

        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()[:150]
            self._cleanup(hdr.name, body.name)
            raise CurlError(f"curl exit {proc.returncode}: {detail}")

        try:
            status = int(proc.stdout.decode().strip() or "0")
        except ValueError:
            status = 0
        with open(body.name, "rb") as f:
            text = f.read().decode("utf-8", "replace")
        headers_dict = self._parse_headers(hdr.name)
        self._cleanup(hdr.name, body.name)
        return _CurlResponse(status, headers_dict, text)

    @staticmethod
    def _parse_headers(path):
        d = _CIDict()
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return d
        # With -L there may be multiple header blocks; the last response's
        # headers win, which is what callers want.
        for line in lines:
            if line.startswith("HTTP/") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            d[k.strip()] = v.strip()
        return d

    @staticmethod
    def _cleanup(*paths):
        for p in paths:
            try:
                os.unlink(p)
            except OSError:
                pass


def default_session():
    return CurlSession()
