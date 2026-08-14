import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';
import {
  cancelPayout,
  fetchEarnings,
  fetchPayout,
  fetchPayoutDestination,
  fetchPayouts,
  fetchSettlements,
  payoutStatusLabel,
  requestPayout,
  savePayoutDestination,
} from '@/api/endpoints/payments';

const BASE_URL = 'http://192.168.1.24:8000';
const PAYOUT_ID = 'bbbbbbbb-0000-4000-8000-000000000000';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(response: Response): jest.Mock {
  const fetchMock = jest.fn().mockResolvedValue(response);
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

const EARNINGS = {
  currency: 'NGN',
  settlement_count: 2,
  gross_earned_kobo: 3_000_000,
  commission_kobo: 600_000,
  net_earned_kobo: 2_400_000,
  reserved_kobo: 400_000,
  paid_out_kobo: 1_000_000,
  available_kobo: 1_000_000,
};

describe('payments api', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
    setAccessTokenProvider(() => 'token');
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('loads the earnings summary', async () => {
    const fetchMock = mockFetch(jsonResponse(200, EARNINGS));

    await expect(fetchEarnings()).resolves.toMatchObject({ available_kobo: 1_000_000 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/earnings/`);
  });

  it('reports the balance the server sent rather than recomputing it', async () => {
    // The app has no way to know about a payout requested on another device, so
    // the only honest available balance is the one the server just gave it.
    mockFetch(jsonResponse(200, { ...EARNINGS, available_kobo: 7 }));

    const earnings = await fetchEarnings();

    expect(earnings.available_kobo).toBe(7);
    expect(earnings.net_earned_kobo - earnings.reserved_kobo - earnings.paid_out_kobo).not.toBe(7);
  });

  it('lists the settlements behind the balance', async () => {
    const fetchMock = mockFetch(jsonResponse(200, EMPTY_PAGE));

    await fetchSettlements();

    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE_URL}/api/v1/provider/earnings/settlements/`,
    );
  });

  it('lists payouts', async () => {
    const fetchMock = mockFetch(jsonResponse(200, EMPTY_PAGE));

    await expect(fetchPayouts()).resolves.toMatchObject({ count: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/payouts/`);
  });

  it('reads one payout', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: PAYOUT_ID, status: 'REQUESTED' }));

    await fetchPayout(PAYOUT_ID);

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/payouts/${PAYOUT_ID}/`);
  });

  it('requests a payout in kobo, through its own route', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: PAYOUT_ID, status: 'REQUESTED' }));

    await requestPayout(600_000, 'key-1');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/provider/payouts/request/`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ amount_kobo: 600_000 });
  });

  it('sends the idempotency key so a retry cannot become a second payout', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: PAYOUT_ID }));

    await requestPayout(600_000, 'key-1');

    expect(fetchMock.mock.calls[0][1].headers['Idempotency-Key']).toBe('key-1');
  });

  it('never sends a status when requesting a payout', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: PAYOUT_ID }));

    await requestPayout(600_000, 'key-1');

    expect(fetchMock.mock.calls[0][1].body).not.toContain('status');
  });

  it('cancels through an action route rather than by writing a status', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: PAYOUT_ID, status: 'CANCELLED' }));

    await cancelPayout(PAYOUT_ID);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/cancel/');
    expect(init.method).toBe('POST');
    expect(init.body).not.toContain('status');
  });

  it('sends the account number but only ever reads back its last four digits', async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { id: 'x', bank_name: 'GTB', account_number_last4: '6789' }),
    );

    const saved = await savePayoutDestination({
      bank_code: '058',
      bank_name: 'Guaranty Trust Bank',
      account_name: 'Adaeze Okonkwo',
      account_number: '0123456789',
    });

    expect(fetchMock.mock.calls[0][1].method).toBe('PUT');
    expect(saved.account_number_last4).toBe('6789');
    expect(saved).not.toHaveProperty('account_number');
  });

  it('surfaces a refusal for not enough balance, with the figure the server sent', async () => {
    mockFetch(
      jsonResponse(422, {
        error: {
          code: 'INSUFFICIENT_BALANCE',
          message: 'That is more than your available balance.',
          details: { available_kobo: 1_000_000, requested_kobo: 9_000_000 },
        },
      }),
    );

    await expect(requestPayout(9_000_000, 'key-1')).rejects.toMatchObject({
      code: 'INSUFFICIENT_BALANCE',
      status: 422,
      details: { available_kobo: 1_000_000 },
    });
  });

  it('surfaces a verification refusal', async () => {
    mockFetch(
      jsonResponse(403, {
        error: {
          code: 'EMAIL_VERIFICATION_REQUIRED',
          message: 'Verify your email address to continue.',
          details: { capability: 'REQUEST_PAYOUT', unmet: ['EMAIL_VERIFIED'] },
        },
      }),
    );

    await expect(requestPayout(100_000, 'key-1')).rejects.toMatchObject({
      code: 'EMAIL_VERIFICATION_REQUIRED',
      status: 403,
    });
  });

  it('surfaces a missing payout destination', async () => {
    mockFetch(
      jsonResponse(422, {
        error: {
          code: 'INVALID_PAYOUT_DESTINATION',
          message: 'Add the bank account you want to be paid into first.',
          details: {},
        },
      }),
    );

    await expect(fetchPayoutDestination()).rejects.toMatchObject({
      code: 'INVALID_PAYOUT_DESTINATION',
    });
  });

  it('surfaces another provider payout as a not found rather than a forbidden', async () => {
    mockFetch(
      jsonResponse(404, {
        error: { code: 'PAYOUT_NOT_FOUND', message: 'That payout could not be found.', details: {} },
      }),
    );

    await expect(fetchPayout(PAYOUT_ID)).rejects.toMatchObject({
      code: 'PAYOUT_NOT_FOUND',
      status: 404,
    });
  });

  it('treats a dropped connection as unknown rather than failed', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;

    await expect(requestPayout(100_000, 'key-1')).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
    });
  });
});

describe('payoutStatusLabel', () => {
  it('says where the money is, in the provider terms', () => {
    expect(payoutStatusLabel('REQUESTED')).toBe('Requested');
    expect(payoutStatusLabel('PROCESSING')).toBe('On its way');
    expect(payoutStatusLabel('PAID')).toBe('Paid');
  });

  it('falls back to the raw code rather than rendering nothing', () => {
    expect(payoutStatusLabel('SOMETHING_NEW' as never)).toBe('SOMETHING_NEW');
  });
});
