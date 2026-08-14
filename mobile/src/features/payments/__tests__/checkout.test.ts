import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';
import { verifyPayoutDestination } from '@/api/endpoints/payments';
import { ApiError } from '@/api/errors';
import { type CheckoutStage, stageLabel, toPaymentOutcome } from '@/features/payments/checkout';
import {
  needsDestination,
  needsDestinationVerification,
  toPayoutOutcome,
} from '@/features/payments/outcomes';

function apiError(code: string, details: Record<string, unknown> = {}): ApiError {
  return new ApiError({ code, message: `message for ${code}`, status: 409, details });
}

describe('toPaymentOutcome', () => {
  it('is null when nothing went wrong', () => {
    expect(toPaymentOutcome(null)).toBeNull();
  });

  it('maps a booking that cannot be paid for', () => {
    const outcome = toPaymentOutcome(apiError('BOOKING_NOT_PAYABLE'));

    expect(outcome?.failure).toBe('NOT_PAYABLE');
    expect(outcome?.isRetryable).toBe(false);
  });

  it('maps an amount mismatch and does not offer a retry', () => {
    // Asking again would produce the same refusal. This needs a person.
    const outcome = toPaymentOutcome(apiError('PAYMENT_AMOUNT_MISMATCH'));

    expect(outcome?.failure).toBe('AMOUNT_MISMATCH');
    expect(outcome?.isRetryable).toBe(false);
  });

  it('maps another customer payment to gone rather than to a permission problem', () => {
    expect(toPaymentOutcome(apiError('PAYMENT_NOT_FOUND'))?.failure).toBe('GONE');
  });

  it('offers a retry when the connection dropped', () => {
    const outcome = toPaymentOutcome(
      new ApiError({ code: 'NETWORK_UNAVAILABLE', message: 'No connection.' }),
    );

    expect(outcome?.failure).toBe('CONNECTION');
    expect(outcome?.isRetryable).toBe(true);
  });

  it('treats a timeout as retryable, since the payment may never have started', () => {
    const outcome = toPaymentOutcome(
      new ApiError({ code: 'TIMEOUT', message: 'The request took too long.' }),
    );

    expect(outcome?.failure).toBe('CONNECTION');
    expect(outcome?.isRetryable).toBe(true);
  });

  it('falls back to unknown for a code it has never seen', () => {
    expect(toPaymentOutcome(apiError('SOMETHING_NEW'))?.failure).toBe('UNKNOWN');
  });

  it('handles a thrown value that is not an ApiError', () => {
    expect(toPaymentOutcome(new TypeError('boom'))?.failure).toBe('UNKNOWN');
  });
});

describe('stageLabel', () => {
  it('tells the customer what is happening at each step', () => {
    const stages: Record<CheckoutStage, string> = {
      IDLE: '',
      STARTING: 'Setting up your payment',
      AWAITING_PAYMENT: 'Finish paying in your browser, then come back',
      CHECKING: 'Checking with your bank',
      PAID: 'Paid',
      FAILED: 'That payment did not go through',
    };

    for (const [stage, label] of Object.entries(stages)) {
      expect(stageLabel(stage as CheckoutStage)).toBe(label);
    }
  });

  it('never claims a payment succeeded while it is still being checked', () => {
    // The app has no way to know. Only the provider does.
    expect(stageLabel('CHECKING')).not.toContain('Paid');
    expect(stageLabel('AWAITING_PAYMENT')).not.toContain('Paid');
  });
});

describe('payout destination verification', () => {
  const originalFetch = globalThis.fetch;
  const BASE_URL = 'http://192.168.1.24:8000';

  function jsonResponse(status: number, body: unknown): Response {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    });
  }

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
    setAccessTokenProvider(() => 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('sends the account number to its own action route', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValue(
        jsonResponse(200, { verification_status: 'VERIFIED', resolved_account_name: 'ADAEZE' }),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await verifyPayoutDestination('0123456789');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/payout-destination/verify/`);
    expect(JSON.parse(init.body)).toEqual({ account_number: '0123456789' });
  });

  it('returns the name the bank holds', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(
      jsonResponse(200, {
        verification_status: 'VERIFIED',
        resolved_account_name: 'ADAEZE N OKONKWO',
        is_verified: true,
      }),
    ) as unknown as typeof fetch;

    const destination = await verifyPayoutDestination('0123456789');

    expect(destination.resolved_account_name).toBe('ADAEZE N OKONKWO');
    expect(destination.is_verified).toBe(true);
  });

  it('surfaces an account the bank did not recognise', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: 'BANK_ACCOUNT_NOT_RESOLVED',
          message: 'We could not confirm that account with the bank. Check the details.',
          details: {},
        },
      }),
    ) as unknown as typeof fetch;

    await expect(verifyPayoutDestination('0123456789')).rejects.toMatchObject({
      code: 'BANK_ACCOUNT_NOT_RESOLVED',
      status: 422,
    });
  });

  it('maps an unconfirmed destination to its own kind of refusal', () => {
    const outcome = toPayoutOutcome(
      new ApiError({
        code: 'PAYOUT_DESTINATION_NOT_VERIFIED',
        message: 'Confirm your bank account before requesting a payout.',
        status: 422,
      }),
    );

    expect(outcome?.failure).toBe('UNVERIFIED_DESTINATION');
    expect(outcome?.isRetryable).toBe(false);
  });

  it('tells an unconfirmed account apart from a missing one', () => {
    // They need different things from the provider, so they get different
    // prompts: confirm the one you have, against add one at all.
    const unconfirmed = toPayoutOutcome(
      new ApiError({ code: 'PAYOUT_DESTINATION_NOT_VERIFIED', message: '', status: 422 }),
    );
    const missing = toPayoutOutcome(
      new ApiError({ code: 'INVALID_PAYOUT_DESTINATION', message: '', status: 422 }),
    );

    expect(needsDestinationVerification(unconfirmed)).toBe(true);
    expect(needsDestination(unconfirmed)).toBe(false);

    expect(needsDestination(missing)).toBe(true);
    expect(needsDestinationVerification(missing)).toBe(false);
  });
});
