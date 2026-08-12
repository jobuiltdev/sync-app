import { ApiError } from '@/api/errors';
import { needsNewCode, toVerificationState } from '@/features/auth/phone-verification';

function apiError(code: string, message = 'x', details: Record<string, unknown> = {}): ApiError {
  return new ApiError({ code, message, status: 400, details });
}

describe('toVerificationState', () => {
  it('is null when nothing has failed', () => {
    expect(toVerificationState(null)).toBeNull();
    expect(toVerificationState(undefined)).toBeNull();
  });

  it.each([
    ['PHONE_NOT_SET', 'PHONE_NOT_SET'],
    ['PHONE_ALREADY_VERIFIED', 'ALREADY_VERIFIED'],
    ['PHONE_VERIFICATION_COOLDOWN', 'COOLDOWN'],
    ['PHONE_VERIFICATION_EXPIRED', 'EXPIRED'],
    ['PHONE_VERIFICATION_EXHAUSTED', 'EXHAUSTED'],
    ['INVALID_PHONE_VERIFICATION_CODE', 'INVALID_CODE'],
    ['VERIFICATION_CHALLENGE_NOT_FOUND', 'CHALLENGE_GONE'],
  ])('maps %s to %s', (code, expected) => {
    expect(toVerificationState(apiError(code))?.failure).toBe(expected);
  });

  it('carries the server cooldown rather than computing one', () => {
    // One set of timing rules, and the server owns it.
    const state = toVerificationState(
      apiError('PHONE_VERIFICATION_COOLDOWN', 'Wait.', { retry_after_seconds: 42 }),
    );

    expect(state?.retryAfterSeconds).toBe(42);
  });

  it('carries the attempts left on a wrong code', () => {
    const state = toVerificationState(
      apiError('INVALID_PHONE_VERIFICATION_CODE', 'Nope.', { attempts_remaining: 3 }),
    );

    expect(state?.attemptsRemaining).toBe(3);
  });

  it('uses the server message rather than inventing one', () => {
    const state = toVerificationState(apiError('INVALID_PHONE_VERIFICATION_CODE', 'That is wrong.'));

    expect(state?.message).toBe('That is wrong.');
  });

  it('reports a connectivity failure as its own state', () => {
    const state = toVerificationState(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' }),
    );

    expect(state?.failure).toBe('CONNECTION');
  });

  it('falls back to unknown for a code it has not seen', () => {
    expect(toVerificationState(apiError('SOMETHING_NEW'))?.failure).toBe('UNKNOWN');
  });

  it('handles a non-API error without crashing the screen', () => {
    const state = toVerificationState(new Error('boom'));

    expect(state?.failure).toBe('UNKNOWN');
    expect(state?.message).not.toBe('boom');
  });

  it('leaves timings null when the server did not supply them', () => {
    const state = toVerificationState(apiError('INVALID_PHONE_VERIFICATION_CODE'));

    expect(state?.retryAfterSeconds).toBeNull();
    expect(state?.attemptsRemaining).toBeNull();
  });
});

describe('needsNewCode', () => {
  it.each(['EXPIRED', 'EXHAUSTED', 'CHALLENGE_GONE'])(
    'is true after %s, because the current challenge is finished',
    (code) => {
      const map: Record<string, string> = {
        EXPIRED: 'PHONE_VERIFICATION_EXPIRED',
        EXHAUSTED: 'PHONE_VERIFICATION_EXHAUSTED',
        CHALLENGE_GONE: 'VERIFICATION_CHALLENGE_NOT_FOUND',
      };

      expect(needsNewCode(toVerificationState(apiError(map[code])))).toBe(true);
    },
  );

  it('is false for a wrong code, where the customer should just try again', () => {
    expect(needsNewCode(toVerificationState(apiError('INVALID_PHONE_VERIFICATION_CODE')))).toBe(
      false,
    );
  });

  it('is false when nothing has failed', () => {
    expect(needsNewCode(null)).toBe(false);
  });
});
