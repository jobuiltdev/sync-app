import { ApiError } from '@/api/errors';
import { toFormErrors } from '@/features/auth/form-errors';

describe('toFormErrors', () => {
  it('maps validation errors onto their fields', () => {
    const result = toFormErrors(
      new ApiError({
        code: 'VALIDATION_ERROR',
        message: 'The submitted data was invalid.',
        status: 400,
        details: {
          fields: {
            email: ['An account with this email already exists.'],
            password: ['This password is too short.'],
          },
        },
      }),
    );

    expect(result.fields.email).toBe('An account with this email already exists.');
    expect(result.fields.password).toBe('This password is too short.');
    expect(result.message).toBeNull();
  });

  it('shows only the first message per field', () => {
    const result = toFormErrors(
      new ApiError({
        code: 'VALIDATION_ERROR',
        message: 'invalid',
        status: 400,
        details: { fields: { password: ['Too short.', 'Too common.'] } },
      }),
    );

    expect(result.fields.password).toBe('Too short.');
  });

  it('promotes non-field errors to the banner so they cannot vanish', () => {
    const result = toFormErrors(
      new ApiError({
        code: 'VALIDATION_ERROR',
        message: 'invalid',
        status: 400,
        details: { fields: { non_field_errors: ['Something was wrong overall.'] } },
      }),
    );

    expect(result.message).toBe('Something was wrong overall.');
    expect(result.fields.non_field_errors).toBeUndefined();
  });

  it('shows a credentials failure as a banner, not against a field', () => {
    // The server deliberately does not say which of the two was wrong, so the
    // message must not be attached to the email or the password input.
    const result = toFormErrors(
      new ApiError({
        code: 'INVALID_CREDENTIALS',
        message: 'That email or password is not correct.',
        status: 401,
      }),
    );

    expect(result.fields).toEqual({});
    expect(result.message).toBe('That email or password is not correct.');
  });

  it('surfaces a connectivity failure', () => {
    const result = toFormErrors(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' }),
    );

    expect(result.message).toBe('No connection.');
  });

  it('returns nothing for a non-API error or no error at all', () => {
    expect(toFormErrors(null)).toEqual({ fields: {}, message: null });
    expect(toFormErrors(new Error('boom'))).toEqual({ fields: {}, message: null });
  });
});
