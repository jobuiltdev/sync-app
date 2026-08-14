import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';
import {
  fetchPayment,
  fetchPayments,
  paymentStatusLabel,
  startPayment,
  verifyPayment,
} from '@/api/endpoints/payments-customer';

const BASE_URL = 'http://192.168.1.24:8000';
const BOOKING_ID = 'cccccccc-0000-4000-8000-000000000000';
const PAYMENT_ID = 'dddddddd-0000-4000-8000-000000000000';

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

const INITIALIZED = {
  id: PAYMENT_ID,
  reference: 'SYP-ABC123',
  status: 'INITIALIZED',
  amount_kobo: 2_000_000,
  currency: 'NGN',
  authorization_url: 'https://checkout.example/abc',
};

describe('customer payments api', () => {
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

  it('starts a payment through the booking own action route', async () => {
    const fetchMock = mockFetch(jsonResponse(201, INITIALIZED));

    await startPayment(BOOKING_ID, 'key-1');

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/customer/bookings/${BOOKING_ID}/pay/`);
    expect(init.method).toBe('POST');
  });

  it('sends no amount, because the server takes it from the booking', async () => {
    const fetchMock = mockFetch(jsonResponse(201, INITIALIZED));

    await startPayment(BOOKING_ID, 'key-1');

    expect(fetchMock.mock.calls[0][1].body).toBe('{}');
  });

  it('sends the idempotency key so a retry is not a second collection', async () => {
    const fetchMock = mockFetch(jsonResponse(201, INITIALIZED));

    await startPayment(BOOKING_ID, 'key-1');

    expect(fetchMock.mock.calls[0][1].headers['Idempotency-Key']).toBe('key-1');
  });

  it('returns somewhere to send the customer, and no credential', async () => {
    mockFetch(jsonResponse(201, INITIALIZED));

    const payment = await startPayment(BOOKING_ID, 'key-1');

    expect(payment.authorization_url).toContain('https://');
    expect(payment).not.toHaveProperty('secret_key');
    expect(payment).not.toHaveProperty('public_key');
  });

  it('starts unpaid, whatever the app might like to think', async () => {
    mockFetch(jsonResponse(201, INITIALIZED));

    expect((await startPayment(BOOKING_ID, 'key-1')).status).toBe('INITIALIZED');
  });

  it('verifies through its own route and sends nothing', async () => {
    // The server ignores the body, so putting a status in one would be writing a
    // claim it is right to disregard.
    const fetchMock = mockFetch(jsonResponse(200, { ...INITIALIZED, status: 'SUCCESSFUL' }));

    await verifyPayment(PAYMENT_ID);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/customer/payments/${PAYMENT_ID}/verify/`);
    expect(init.method).toBe('POST');
    expect(init.body).toBe('{}');
    expect(init.body).not.toContain('status');
  });

  it('reports the status the server returned rather than assuming success', async () => {
    mockFetch(jsonResponse(200, { ...INITIALIZED, status: 'FAILED' }));

    expect((await verifyPayment(PAYMENT_ID)).status).toBe('FAILED');
  });

  it('reads one payment', async () => {
    const fetchMock = mockFetch(jsonResponse(200, INITIALIZED));

    await fetchPayment(PAYMENT_ID);

    expect(fetchMock.mock.calls[0][0]).toBe(
      `${BASE_URL}/api/v1/customer/payments/${PAYMENT_ID}/`,
    );
  });

  it('lists your payments', async () => {
    const fetchMock = mockFetch(
      jsonResponse(200, { count: 0, next: null, previous: null, results: [] }),
    );

    await expect(fetchPayments()).resolves.toMatchObject({ count: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/customer/payments/`);
  });

  it('surfaces a booking that cannot be paid for', async () => {
    mockFetch(
      jsonResponse(409, {
        error: {
          code: 'BOOKING_NOT_PAYABLE',
          message: 'This booking cannot be paid for.',
          details: { booking_status: 'CANCELLED' },
        },
      }),
    );

    await expect(startPayment(BOOKING_ID, 'key-1')).rejects.toMatchObject({
      code: 'BOOKING_NOT_PAYABLE',
      status: 409,
    });
  });

  it('surfaces an amount mismatch without the other amount in it', async () => {
    mockFetch(
      jsonResponse(409, {
        error: {
          code: 'PAYMENT_AMOUNT_MISMATCH',
          message: 'That payment does not match the amount for this booking.',
          details: { expected_kobo: 2_000_000 },
        },
      }),
    );

    await expect(verifyPayment(PAYMENT_ID)).rejects.toMatchObject({
      code: 'PAYMENT_AMOUNT_MISMATCH',
    });
  });

  it('surfaces another customer payment as a not found', async () => {
    mockFetch(
      jsonResponse(404, {
        error: { code: 'PAYMENT_NOT_FOUND', message: 'That payment could not be found.', details: {} },
      }),
    );

    await expect(fetchPayment(PAYMENT_ID)).rejects.toMatchObject({
      code: 'PAYMENT_NOT_FOUND',
      status: 404,
    });
  });

  it('treats a dropped connection as unknown rather than paid', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;

    await expect(verifyPayment(PAYMENT_ID)).rejects.toMatchObject({
      code: 'NETWORK_UNAVAILABLE',
    });
  });
});

describe('paymentStatusLabel', () => {
  it('says where the money is, in the customer terms', () => {
    expect(paymentStatusLabel('INITIALIZED')).toBe('Waiting for payment');
    expect(paymentStatusLabel('SUCCESSFUL')).toBe('Paid');
    expect(paymentStatusLabel('FAILED')).toBe('Not paid');
  });

  it('falls back to the raw code rather than rendering nothing', () => {
    expect(paymentStatusLabel('SOMETHING_NEW' as never)).toBe('SOMETHING_NEW');
  });
});
