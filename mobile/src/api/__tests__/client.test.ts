import { api, setAccessTokenProvider } from '@/api/client';
import { ApiError } from '@/api/errors';

const BASE_URL = 'http://192.168.1.24:8000';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function mockFetch(implementation: jest.Mock) {
  globalThis.fetch = implementation as unknown as typeof fetch;
  return implementation;
}

/** The headers the client passed on its first call. */
function sentHeaders(fetchMock: jest.Mock): Record<string, string> {
  return fetchMock.mock.calls[0][1].headers;
}

describe('api client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    setAccessTokenProvider(() => null);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('requests the configured base URL and returns the parsed body', async () => {
    const fetchMock = mockFetch(jest.fn().mockResolvedValue(jsonResponse(200, { status: 'ok' })));

    await expect(api.get('/api/v1/health/')).resolves.toEqual({ status: 'ok' });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/health/`);
  });

  it('tolerates a base URL with a trailing slash', async () => {
    process.env.EXPO_PUBLIC_API_URL = `${BASE_URL}/`;
    const fetchMock = mockFetch(jest.fn().mockResolvedValue(jsonResponse(200, {})));

    await api.get('/api/v1/health/');

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE_URL}/api/v1/health/`);
  });

  it('attaches the bearer token when one is available', async () => {
    setAccessTokenProvider(() => 'token-123');
    const fetchMock = mockFetch(jest.fn().mockResolvedValue(jsonResponse(200, {})));

    await api.get('/api/v1/health/');

    expect(sentHeaders(fetchMock).Authorization).toBe('Bearer token-123');
  });

  it('sends no Authorization header when there is no session', async () => {
    const fetchMock = mockFetch(jest.fn().mockResolvedValue(jsonResponse(200, {})));

    await api.get('/api/v1/health/');

    expect(sentHeaders(fetchMock).Authorization).toBeUndefined();
  });

  it('sends an idempotency key when the caller supplies one', async () => {
    const fetchMock = mockFetch(jest.fn().mockResolvedValue(jsonResponse(201, {})));

    await api.post('/api/v1/customer/bookings', { quote: 'q1' }, { idempotencyKey: 'key-1' });

    expect(sentHeaders(fetchMock)['Idempotency-Key']).toBe('key-1');
  });

  it('turns an error response into an ApiError carrying the machine code', async () => {
    mockFetch(
      jest.fn().mockResolvedValue(
        jsonResponse(403, {
          error: { code: 'EMAIL_VERIFICATION_REQUIRED', message: 'Verify your email.' },
        }),
      ),
    );

    await expect(api.post('/api/v1/customer/bookings')).rejects.toMatchObject({
      code: 'EMAIL_VERIFICATION_REQUIRED',
      status: 403,
    });
  });

  it('reports a failed connection as a connectivity error', async () => {
    mockFetch(jest.fn().mockRejectedValue(new TypeError('Network request failed')));

    const caught: unknown = await api.get('/api/v1/health/').catch((error: unknown) => error);

    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe('NETWORK_UNAVAILABLE');
    expect((caught as ApiError).isConnectivityError).toBe(true);
  });

  it('fails loudly when the API URL has not been configured', async () => {
    delete process.env.EXPO_PUBLIC_API_URL;
    const fetchMock = mockFetch(jest.fn());

    // A configuration mistake must not be reported as the network being down.
    await expect(api.get('/api/v1/health/')).rejects.toThrow(/EXPO_PUBLIC_API_URL/);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
