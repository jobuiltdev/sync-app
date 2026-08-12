import {
  type BookingInput,
  cancelBooking,
  confirmBooking,
  createBooking,
  fetchBooking,
  fetchBookings,
  statusLabel,
} from '@/api/endpoints/bookings';
import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';

const BASE_URL = 'http://192.168.1.24:8000';

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

const INPUT: BookingInput = {
  service_slug: 'standard-clean',
  provider_id: 'b1f2c3d4-0000-4000-8000-000000000000',
  address_id: 'a1f2c3d4-0000-4000-8000-000000000000',
  details: { property_type: 'APARTMENT', bedrooms: 3 },
};

describe('bookings api', () => {
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

  it('lists bookings from the paginated endpoint', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { count: 0, next: null, previous: null, results: [] }));

    await expect(fetchBookings()).resolves.toMatchObject({ count: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/customer/bookings/`);
  });

  it('reads one booking by id', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: 'abc' }));

    await fetchBooking('abc');

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/customer/bookings/abc/`);
  });

  it('posts a booking with the spec payload intact', async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: 'new' }));

    await createBooking(INPUT);

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.service_slug).toBe('standard-clean');
    expect(body.details).toEqual({ property_type: 'APARTMENT', bedrooms: 3 });
  });

  it('surfaces a verification refusal as an ApiError with its code', async () => {
    mockFetch(
      jsonResponse(403, {
        error: {
          code: 'PHONE_VERIFICATION_REQUIRED',
          message: 'Verify your phone number to continue.',
          details: { unmet: ['PHONE_VERIFIED'] },
        },
      }),
    );

    await expect(createBooking(INPUT)).rejects.toMatchObject({
      code: 'PHONE_VERIFICATION_REQUIRED',
      status: 403,
    });
  });

  it('surfaces an illegal transition as a conflict', async () => {
    mockFetch(
      jsonResponse(409, {
        error: {
          code: 'ILLEGAL_TRANSITION',
          message: 'This booking cannot move to that status.',
          details: { allowed_transitions: ['EN_ROUTE'] },
        },
      }),
    );

    await expect(confirmBooking('abc')).rejects.toMatchObject({
      code: 'ILLEGAL_TRANSITION',
      status: 409,
    });
  });

  it('sends a cancellation reason', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: 'abc', status: 'CANCELLED' }));

    await cancelBooking('abc', 'Changed my mind');

    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: 'Changed my mind' });
    expect(fetchMock.mock.calls[0][0]).toContain('/cancel/');
  });

  it('confirms completion through its own action route, never by sending a status', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: 'abc', status: 'COMPLETED' }));

    await confirmBooking('abc');

    expect(fetchMock.mock.calls[0][0]).toContain('/confirm/');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).not.toHaveProperty('status');
  });
});

describe('statusLabel', () => {
  it('turns codes into something a customer reads', () => {
    expect(statusLabel('ASSIGNED')).toBe('Booked');
    expect(statusLabel('AWAITING_CONFIRMATION')).toBe('Awaiting your confirmation');
    expect(statusLabel('EN_ROUTE')).toBe('On the way');
  });

  it('falls back to the raw code rather than rendering nothing', () => {
    expect(statusLabel('SOMETHING_NEW' as never)).toBe('SOMETHING_NEW');
  });
});
