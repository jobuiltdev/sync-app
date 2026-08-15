import { ApiError, codeOf, fieldErrors, isNetworkError, messageFor } from '@/api/errors';

describe('messageFor', () => {
  it('prefers the server message over anything written in the client', () => {
    // A domain message is the useful half of a failure. Replacing it with a
    // generic apology throws away the only thing that explains what happened.
    const error = new ApiError({
      code: 'NO_ELIGIBLE_PROVIDERS',
      message: 'No provider covers this service in your area yet.',
      status: 422,
    });

    expect(messageFor(error)).toBe('No provider covers this service in your area yet.');
  });

  it('replaces the transport-level codes with something a person can act on', () => {
    const offline = new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'fetch failed' });
    const slow = new ApiError({ code: 'TIMEOUT', message: 'aborted' });

    expect(messageFor(offline)).toMatch(/No connection/);
    expect(messageFor(slow)).toMatch(/took too long/);
  });

  it('falls back to a plain error message', () => {
    expect(messageFor(new Error('something specific'))).toBe('something specific');
  });

  it('has something to say about a value that is not an error at all', () => {
    expect(messageFor(undefined)).toMatch(/went wrong/);
    expect(messageFor('a string')).toMatch(/went wrong/);
  });
});

describe('isNetworkError', () => {
  it('is true only for connectivity failures', () => {
    expect(isNetworkError(new ApiError({ code: 'NETWORK_UNAVAILABLE', message: '' }))).toBe(true);
    expect(isNetworkError(new ApiError({ code: 'TIMEOUT', message: '' }))).toBe(true);
    expect(isNetworkError(new ApiError({ code: 'INSUFFICIENT_BALANCE', message: '' }))).toBe(false);
    expect(isNetworkError(new Error('boom'))).toBe(false);
  });
});

describe('codeOf', () => {
  it('exposes the stable machine code', () => {
    expect(codeOf(new ApiError({ code: 'PAYOUT_NOT_ACTIONABLE', message: '' }))).toBe(
      'PAYOUT_NOT_ACTIONABLE',
    );
  });

  it('is null for anything that is not an API error', () => {
    expect(codeOf(new Error('boom'))).toBeNull();
  });
});

describe('fieldErrors', () => {
  it('takes the first message for each field', () => {
    const error = new ApiError({
      code: 'VALIDATION_ERROR',
      message: 'That did not validate.',
      status: 400,
      details: { email: ['Already in use.', 'Second message.'], phone: 'Not a valid number.' },
    });

    expect(fieldErrors(error)).toEqual({
      email: 'Already in use.',
      phone: 'Not a valid number.',
    });
  });

  it('ignores details that are not messages', () => {
    const error = new ApiError({
      code: 'VALIDATION_ERROR',
      message: '',
      details: { unmet: [], available_kobo: 5000 },
    });

    expect(fieldErrors(error)).toEqual({});
  });

  it('is empty for a non-API error', () => {
    expect(fieldErrors(new Error('boom'))).toEqual({});
  });
});
