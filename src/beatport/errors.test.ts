import { describe, it, expect } from 'vitest';
import {
  BeatportError,
  BeatportUnavailable,
  BeatportRateLimited,
  BeatportAuthError,
} from './errors';

describe('errors', () => {
  it('base is an Error with default code/message', () => {
    const e = new BeatportError();
    expect(e instanceof Error).toBe(true);
    expect(e.code).toBe('error');
    expect(e.userMessage).toContain('Something went wrong');
  });
  it('unavailable maps copy and code', () => {
    const e = new BeatportUnavailable();
    expect(e.code).toBe('unavailable');
    expect(e.userMessage).toContain('temporarily unavailable');
  });
  it('rate limited maps code', () => {
    expect(new BeatportRateLimited().code).toBe('rate_limited');
  });
  it('auth maps code', () => {
    expect(new BeatportAuthError().code).toBe('auth');
  });
});
