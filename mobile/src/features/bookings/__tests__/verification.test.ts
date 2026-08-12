import { ApiError } from '@/api/errors';
import {
  isPhoneVerificationRequired,
  toVerificationBlock,
} from '@/features/bookings/verification';

function verificationError(code: string, unmet: string[]): ApiError {
  return new ApiError({
    code,
    message: 'Verify your phone number to continue.',
    status: 403,
    details: {
      capability: 'CREATE_BOOKING',
      unmet,
      satisfied: [],
      next_step: { requirement: unmet[0], action: 'POST /api/v1/auth/phone/verification/request/' },
    },
  });
}

describe('toVerificationBlock', () => {
  it('reads a phone verification refusal', () => {
    const block = toVerificationBlock(
      verificationError('PHONE_VERIFICATION_REQUIRED', ['PHONE_VERIFIED']),
    );

    expect(block).not.toBeNull();
    expect(block?.unmet).toEqual(['PHONE_VERIFIED']);
    expect(block?.next).toBe('PHONE_VERIFIED');
  });

  it('reads the umbrella code when several requirements are outstanding', () => {
    const block = toVerificationBlock(
      verificationError('VERIFICATION_REQUIRED', ['PHONE_VERIFIED', 'EMAIL_VERIFIED']),
    );

    expect(block?.unmet).toHaveLength(2);
    // The server orders them; the app asks for the first.
    expect(block?.next).toBe('PHONE_VERIFIED');
  });

  it('carries the server message rather than inventing one', () => {
    const block = toVerificationBlock(
      verificationError('PHONE_VERIFICATION_REQUIRED', ['PHONE_VERIFIED']),
    );

    expect(block?.message).toBe('Verify your phone number to continue.');
  });

  it('ignores an unrelated API error', () => {
    const error = new ApiError({ code: 'VALIDATION_ERROR', message: 'bad', status: 400 });

    expect(toVerificationBlock(error)).toBeNull();
  });

  it('ignores a non-API error', () => {
    expect(toVerificationBlock(new Error('boom'))).toBeNull();
    expect(toVerificationBlock(null)).toBeNull();
  });

  it('survives a malformed details payload', () => {
    const error = new ApiError({
      code: 'PHONE_VERIFICATION_REQUIRED',
      message: 'x',
      status: 403,
      details: { unmet: 'not-a-list' },
    });

    expect(toVerificationBlock(error)?.unmet).toEqual([]);
  });
});

describe('isPhoneVerificationRequired', () => {
  it('is true when the phone is what is missing', () => {
    expect(
      isPhoneVerificationRequired(
        verificationError('PHONE_VERIFICATION_REQUIRED', ['PHONE_VERIFIED']),
      ),
    ).toBe(true);
  });

  it('is false when only an email is missing', () => {
    expect(
      isPhoneVerificationRequired(
        verificationError('EMAIL_VERIFICATION_REQUIRED', ['EMAIL_VERIFIED']),
      ),
    ).toBe(false);
  });

  it('is false for an ordinary validation failure', () => {
    expect(
      isPhoneVerificationRequired(
        new ApiError({ code: 'VALIDATION_ERROR', message: 'bad', status: 400 }),
      ),
    ).toBe(false);
  });
});
