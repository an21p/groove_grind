class BeatportError(Exception):
    """Base class for all Beatport client errors."""

    code = "error"
    http_status = 502
    user_message = "Something went wrong talking to Beatport."

    def __init__(self, message=None):
        super().__init__(message or self.user_message)


class BeatportUnavailable(BeatportError):
    """Timeouts, connection errors, HTTP 5xx, or a 403 IP block."""

    code = "unavailable"
    http_status = 503
    user_message = "Beatport is temporarily unavailable. Please try again in a moment."


class BeatportRateLimited(BeatportError):
    """HTTP 429."""

    code = "rate_limited"
    http_status = 429
    user_message = "Beatport is busy right now. Please retry in a few seconds."


class BeatportAuthError(BeatportError):
    """Credentials invalid, or login/authorize/token/refresh failed."""

    code = "auth"
    http_status = 502  # surfaced as our problem (Bad Gateway), not the client's
    user_message = "We're having trouble connecting to Beatport — we're on it."
