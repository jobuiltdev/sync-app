import { ApiError } from '@/api/errors';
import {
  needsDestination,
  needsVerification,
  toPayoutOutcome,
} from '@/features/payments/outcomes';

function apiError(code: string, details: Record<string, unknown> = {}): ApiError {
  return new ApiError({ code, message: `message for ${code}`, status: 422, details });
}

describe('toPayoutOutcome', () => {
  it('is null when nothing went wrong', () => {
    expect(toPayoutOutcome(null)).toBeNull();
    expect(toPayoutOutcome(undefined)).toBeNull();
  });

  it('maps a capability refusal and carries what is outstanding', () => {
    const outcome = toPayoutOutcome(
      apiError('EMAIL_VERIFICATION_REQUIRED', { unmet: ['EMAIL_VERIFIED'] }),
    );

    expect(outcome?.failure).toBe('VERIFICATION_REQUIRED');
    expect(outcome?.unmet).toEqual(['EMAIL_VERIFIED']);
    expect(needsVerification(outcome)).toBe(true);
  });

  it('treats every verification code as the same kind of refusal', () => {
    for (const code of [
      'VERIFICATION_REQUIRED',
      'PHONE_VERIFICATION_REQUIRED',
      'EMAIL_VERIFICATION_REQUIRED',
    ]) {
      expect(toPayoutOutcome(apiError(code))?.failure).toBe('VERIFICATION_REQUIRED');
    }
  });

  it('maps a missing bank account to something the screen can act on', () => {
    const outcome = toPayoutOutcome(apiError('INVALID_PAYOUT_DESTINATION'));

    expect(outcome?.failure).toBe('NO_DESTINATION');
    expect(needsDestination(outcome)).toBe(true);
  });

  it('reads the available balance out of an insufficient balance refusal', () => {
    const outcome = toPayoutOutcome(
      apiError('INSUFFICIENT_BALANCE', { available_kobo: 1_000_000, requested_kobo: 9_000_000 }),
    );

    expect(outcome?.failure).toBe('INSUFFICIENT_BALANCE');
    expect(outcome?.availableKobo).toBe(1_000_000);
  });

  it('ignores an available balance that is not a number', () => {
    const outcome = toPayoutOutcome(apiError('INSUFFICIENT_BALANCE', { available_kobo: 'lots' }));

    expect(outcome?.availableKobo).toBeNull();
  });

  it('maps a payout already in flight', () => {
    expect(toPayoutOutcome(apiError('PAYOUT_ALREADY_REQUESTED'))?.failure).toBe(
      'ALREADY_REQUESTED',
    );
  });

  it('maps a payout that can no longer be cancelled', () => {
    expect(toPayoutOutcome(apiError('PAYOUT_NOT_ACTIONABLE'))?.failure).toBe('NOT_ACTIONABLE');
  });

  it('maps another provider payout to gone rather than to a permission problem', () => {
    // A 404 is what the API returns for somebody else's row, and the app must not
    // dress that up as "you are not allowed", which would confirm it exists.
    expect(toPayoutOutcome(apiError('PAYOUT_NOT_FOUND'))?.failure).toBe('GONE');
  });

  it('maps field validation to an amount problem', () => {
    expect(toPayoutOutcome(apiError('VALIDATION_ERROR'))?.failure).toBe('INVALID_AMOUNT');
  });

  it('offers a retry only when trying again could possibly work', () => {
    const connection = toPayoutOutcome(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' }),
    );
    expect(connection?.failure).toBe('CONNECTION');
    expect(connection?.isRetryable).toBe(true);

    for (const code of [
      'INSUFFICIENT_BALANCE',
      'INVALID_PAYOUT_DESTINATION',
      'PAYOUT_ALREADY_REQUESTED',
      'EMAIL_VERIFICATION_REQUIRED',
    ]) {
      expect(toPayoutOutcome(apiError(code))?.isRetryable).toBe(false);
    }
  });

  it('treats a timeout as retryable, since the request may never have arrived', () => {
    const outcome = toPayoutOutcome(
      new ApiError({ code: 'TIMEOUT', message: 'The request took too long.' }),
    );

    expect(outcome?.failure).toBe('CONNECTION');
    expect(outcome?.isRetryable).toBe(true);
  });

  it('falls back to unknown for a code it has never seen', () => {
    const outcome = toPayoutOutcome(apiError('SOMETHING_NEW_FROM_THE_SERVER'));

    expect(outcome?.failure).toBe('UNKNOWN');
    expect(outcome?.message).toBe('message for SOMETHING_NEW_FROM_THE_SERVER');
  });

  it('handles a thrown value that is not an ApiError at all', () => {
    const outcome = toPayoutOutcome(new TypeError('undefined is not a function'));

    expect(outcome?.failure).toBe('UNKNOWN');
    expect(outcome?.isRetryable).toBe(true);
  });

  it('says no to verification and destination prompts when neither applies', () => {
    const outcome = toPayoutOutcome(apiError('INSUFFICIENT_BALANCE'));

    expect(needsVerification(outcome)).toBe(false);
    expect(needsDestination(outcome)).toBe(false);
  });
});
