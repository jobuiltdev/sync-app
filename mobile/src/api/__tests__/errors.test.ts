import { ApiError, toApiError } from '@/api/errors';

describe('toApiError', () => {
  it('reads code, message and details from the API envelope', () => {
    const error = toApiError(403, {
      error: {
        code: 'PHONE_VERIFICATION_REQUIRED',
        message: 'Verify your phone number to book a service.',
        details: { unmet: ['PHONE_VERIFIED'] },
      },
    });

    expect(error.code).toBe('PHONE_VERIFICATION_REQUIRED');
    expect(error.message).toBe('Verify your phone number to book a service.');
    expect(error.status).toBe(403);
    expect(error.details).toEqual({ unmet: ['PHONE_VERIFIED'] });
  });

  it('always exposes details as an object', () => {
    const error = toApiError(401, { error: { code: 'NOT_AUTHENTICATED', message: 'No.' } });

    expect(error.details).toEqual({});
  });

  it('does not guess at a body that is not an envelope', () => {
    const error = toApiError(502, '<html>Bad Gateway</html>');

    expect(error.code).toBe('UNEXPECTED_RESPONSE');
    expect(error.status).toBe(502);
  });

  it('treats a partial envelope as unexpected rather than trusting it', () => {
    const error = toApiError(400, { error: { code: 'MISSING_MESSAGE' } });

    expect(error.code).toBe('UNEXPECTED_RESPONSE');
  });
});

describe('ApiError.isConnectivityError', () => {
  it.each(['NETWORK_UNAVAILABLE', 'TIMEOUT'])('is true for %s', (code) => {
    expect(new ApiError({ code, message: 'x' }).isConnectivityError).toBe(true);
  });

  it('is false for an error the server chose to return', () => {
    const error = new ApiError({ code: 'VALIDATION_ERROR', message: 'x', status: 400 });

    expect(error.isConnectivityError).toBe(false);
  });
});
