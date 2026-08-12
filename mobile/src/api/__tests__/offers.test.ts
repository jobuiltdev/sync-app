import { resetAuthPlumbing, setAccessTokenProvider } from '@/api/client';
import {
  acceptOffer,
  declineOffer,
  fetchOffer,
  fetchOffers,
  offerStatusLabel,
} from '@/api/endpoints/offers';

const BASE_URL = 'http://192.168.1.24:8000';
const OFFER_ID = 'aaaaaaaa-0000-4000-8000-000000000000';

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

describe('offers api', () => {
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

  it('lists the pending inbox by default', async () => {
    const fetchMock = mockFetch(jsonResponse(200, EMPTY_PAGE));

    await expect(fetchOffers()).resolves.toMatchObject({ count: 0 });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/offers/`);
  });

  it('asks for history explicitly', async () => {
    const fetchMock = mockFetch(jsonResponse(200, EMPTY_PAGE));

    await fetchOffers({ all: true });

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/offers/?status=all`);
  });

  it('reads one offer', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: OFFER_ID }));

    await fetchOffer(OFFER_ID);

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/provider/offers/${OFFER_ID}/`);
  });

  it('accepts through its own action route, never by sending a status', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { status: 'ASSIGNED' }));

    await acceptOffer(OFFER_ID);

    expect(fetchMock.mock.calls[0][0]).toContain('/accept/');
    expect(fetchMock.mock.calls[0][1].method).toBe('POST');
    expect(fetchMock.mock.calls[0][1].body).not.toContain('status');
  });

  it('sends a decline reason', async () => {
    const fetchMock = mockFetch(jsonResponse(200, { status: 'DECLINED' }));

    await declineOffer(OFFER_ID, 'Too far');

    expect(fetchMock.mock.calls[0][0]).toContain('/decline/');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: 'Too far' });
  });

  it('surfaces a job taken by someone else', async () => {
    mockFetch(
      jsonResponse(409, {
        error: {
          code: 'BOOKING_NO_LONGER_AVAILABLE',
          message: 'This job is no longer available.',
          details: {},
        },
      }),
    );

    await expect(acceptOffer(OFFER_ID)).rejects.toMatchObject({
      code: 'BOOKING_NO_LONGER_AVAILABLE',
      status: 409,
    });
  });

  it('surfaces an expired offer', async () => {
    mockFetch(
      jsonResponse(410, {
        error: { code: 'OFFER_EXPIRED', message: 'This offer has expired.', details: {} },
      }),
    );

    await expect(acceptOffer(OFFER_ID)).rejects.toMatchObject({ code: 'OFFER_EXPIRED' });
  });

  it('surfaces a verification refusal', async () => {
    mockFetch(
      jsonResponse(403, {
        error: {
          code: 'EMAIL_VERIFICATION_REQUIRED',
          message: 'Verify your email address to continue.',
          details: { unmet: ['EMAIL_VERIFIED'] },
        },
      }),
    );

    await expect(acceptOffer(OFFER_ID)).rejects.toMatchObject({
      code: 'EMAIL_VERIFICATION_REQUIRED',
      status: 403,
    });
  });
});

describe('offerStatusLabel', () => {
  it('says who did what, from the provider point of view', () => {
    expect(offerStatusLabel('PENDING')).toBe('Awaiting your answer');
    expect(offerStatusLabel('ACCEPTED')).toBe('You accepted');
    expect(offerStatusLabel('DECLINED')).toBe('You declined');
  });

  it('does not blame the provider for losing a race', () => {
    // They did nothing; somebody else was quicker.
    expect(offerStatusLabel('SUPERSEDED')).toBe('Taken by someone else');
  });

  it('falls back to the raw code rather than rendering nothing', () => {
    expect(offerStatusLabel('SOMETHING_NEW' as never)).toBe('SOMETHING_NEW');
  });
});
