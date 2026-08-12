import { ApiError } from '@/api/errors';
import { needsVerification, toOfferOutcome } from '@/features/offers/outcomes';

function apiError(code: string, message = 'x', details: Record<string, unknown> = {}): ApiError {
  return new ApiError({ code, message, status: 409, details });
}

describe('toOfferOutcome', () => {
  it('is null when nothing has failed', () => {
    expect(toOfferOutcome(null)).toBeNull();
    expect(toOfferOutcome(undefined)).toBeNull();
  });

  it.each([
    ['OFFER_NOT_FOUND', 'GONE'],
    ['OFFER_ALREADY_RESPONDED', 'ALREADY_RESPONDED'],
    ['OFFER_EXPIRED', 'EXPIRED'],
    ['BOOKING_NO_LONGER_AVAILABLE', 'TAKEN'],
    ['PHONE_VERIFICATION_REQUIRED', 'VERIFICATION_REQUIRED'],
    ['EMAIL_VERIFICATION_REQUIRED', 'VERIFICATION_REQUIRED'],
    ['VERIFICATION_REQUIRED', 'VERIFICATION_REQUIRED'],
  ])('maps %s to %s', (code, expected) => {
    expect(toOfferOutcome(apiError(code))?.failure).toBe(expected);
  });

  it('treats a taken job as final, so the provider is sent back rather than retrying', () => {
    expect(toOfferOutcome(apiError('BOOKING_NO_LONGER_AVAILABLE'))?.isFinal).toBe(true);
  });

  it.each(['OFFER_NOT_FOUND', 'OFFER_ALREADY_RESPONDED', 'OFFER_EXPIRED'])(
    'treats %s as final',
    (code) => {
      expect(toOfferOutcome(apiError(code))?.isFinal).toBe(true);
    },
  );

  it('does not treat a verification refusal as final, since it can be resolved', () => {
    expect(toOfferOutcome(apiError('EMAIL_VERIFICATION_REQUIRED'))?.isFinal).toBe(false);
  });

  it('carries the outstanding requirements', () => {
    const outcome = toOfferOutcome(
      apiError('VERIFICATION_REQUIRED', 'Verify your details.', {
        unmet: ['PHONE_VERIFIED', 'EMAIL_VERIFIED'],
      }),
    );

    expect(outcome?.unmet).toEqual(['PHONE_VERIFIED', 'EMAIL_VERIFIED']);
  });

  it('uses the server message rather than inventing one', () => {
    expect(toOfferOutcome(apiError('OFFER_EXPIRED', 'This offer has expired.'))?.message).toBe(
      'This offer has expired.',
    );
  });

  it('reports a connectivity failure as retryable', () => {
    const outcome = toOfferOutcome(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' }),
    );

    expect(outcome?.failure).toBe('CONNECTION');
    expect(outcome?.isFinal).toBe(false);
  });

  it('falls back to unknown for a code it has not seen', () => {
    expect(toOfferOutcome(apiError('SOMETHING_NEW'))?.failure).toBe('UNKNOWN');
  });

  it('handles a non-API error without crashing the screen', () => {
    const outcome = toOfferOutcome(new Error('boom'));

    expect(outcome?.failure).toBe('UNKNOWN');
    expect(outcome?.message).not.toBe('boom');
  });

  it('survives a malformed unmet payload', () => {
    expect(toOfferOutcome(apiError('VERIFICATION_REQUIRED', 'x', { unmet: 'nope' }))?.unmet).toEqual(
      [],
    );
  });
});

describe('needsVerification', () => {
  it('is true for a capability refusal', () => {
    expect(needsVerification(toOfferOutcome(apiError('EMAIL_VERIFICATION_REQUIRED')))).toBe(true);
  });

  it('is false for a job somebody else took', () => {
    expect(needsVerification(toOfferOutcome(apiError('BOOKING_NO_LONGER_AVAILABLE')))).toBe(false);
  });

  it('is false when nothing failed', () => {
    expect(needsVerification(null)).toBe(false);
  });
});
