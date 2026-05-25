export class BeatportError extends Error {
  code = 'error';
  userMessage = 'Something went wrong talking to Beatport.';
  constructor(message?: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class BeatportUnavailable extends BeatportError {
  code = 'unavailable';
  userMessage = 'Beatport is temporarily unavailable. Please try again in a moment.';
}

export class BeatportRateLimited extends BeatportError {
  code = 'rate_limited';
  userMessage = 'Beatport is busy right now. Please retry in a few seconds.';
}

export class BeatportAuthError extends BeatportError {
  code = 'auth';
  userMessage = "We're having trouble connecting to Beatport — we're on it.";
}
