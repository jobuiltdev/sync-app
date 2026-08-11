import {
  api,
  resetAuthPlumbing,
  setAccessTokenProvider,
  setTokenRefresher,
} from '@/api/client';

const BASE_URL = 'http://192.168.1.24:8000';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

const UNAUTHORIZED = () =>
  jsonResponse(401, {
    error: { code: 'NOT_AUTHENTICATED', message: 'Authentication credentials were not provided.' },
  });

function authHeaderOf(fetchMock: jest.Mock, call: number): string | undefined {
  return fetchMock.mock.calls[call][1].headers.Authorization;
}

describe('transparent token refresh', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    process.env.EXPO_PUBLIC_API_URL = BASE_URL;
    resetAuthPlumbing();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('renews and replays once when the access token has expired', async () => {
    let token = 'stale';
    setAccessTokenProvider(() => token);
    setTokenRefresher(async () => {
      token = 'fresh';
      return true;
    });

    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(jsonResponse(200, { email: 'ada@example.com' }));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(api.get('/api/v1/auth/me/')).resolves.toEqual({ email: 'ada@example.com' });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(authHeaderOf(fetchMock, 0)).toBe('Bearer stale');
    expect(authHeaderOf(fetchMock, 1)).toBe('Bearer fresh');
  });

  it('surfaces the 401 when the session cannot be renewed', async () => {
    setAccessTokenProvider(() => 'stale');
    setTokenRefresher(async () => false);

    const fetchMock = jest.fn().mockResolvedValue(UNAUTHORIZED());
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(api.get('/api/v1/auth/me/')).rejects.toMatchObject({
      code: 'NOT_AUTHENTICATED',
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry more than once, so a persistent 401 cannot loop', async () => {
    setAccessTokenProvider(() => 'stale');
    setTokenRefresher(async () => true);

    const fetchMock = jest.fn().mockResolvedValue(UNAUTHORIZED());
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(api.get('/api/v1/auth/me/')).rejects.toMatchObject({ status: 401 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('refreshes once when several requests fail at the same time', async () => {
    // Each refresh spends a single-use refresh token, so concurrent 401s must not
    // each trigger one or all but the first would be blacklisted mid-flight.
    setAccessTokenProvider(() => 'stale');
    const refresher = jest.fn().mockResolvedValue(true);
    setTokenRefresher(refresher);

    const fetchMock = jest
      .fn()
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValueOnce(UNAUTHORIZED())
      .mockResolvedValue(jsonResponse(200, {}));
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await Promise.all([
      api.get('/api/v1/auth/me/'),
      api.get('/api/v1/auth/me/'),
      api.get('/api/v1/auth/me/'),
    ]);

    expect(refresher).toHaveBeenCalledTimes(1);
  });

  it('never tries to refresh a call that opted out', async () => {
    // The refresh endpoint itself opts out. If it did not, a failing refresh would
    // trigger another refresh, forever.
    const refresher = jest.fn().mockResolvedValue(true);
    setTokenRefresher(refresher);

    const fetchMock = jest.fn().mockResolvedValue(UNAUTHORIZED());
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    await expect(
      api.post('/api/v1/auth/refresh/', { refresh: 'x' }, { skipAuthRefresh: true }),
    ).rejects.toMatchObject({ status: 401 });

    expect(refresher).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('leaves non-401 failures alone', async () => {
    setAccessTokenProvider(() => 'good');
    const refresher = jest.fn().mockResolvedValue(true);
    setTokenRefresher(refresher);

    globalThis.fetch = jest.fn().mockResolvedValue(
      jsonResponse(403, { error: { code: 'ACCOUNT_INACTIVE', message: 'Deactivated.' } }),
    ) as unknown as typeof fetch;

    await expect(api.get('/api/v1/auth/me/')).rejects.toMatchObject({ code: 'ACCOUNT_INACTIVE' });
    expect(refresher).not.toHaveBeenCalled();
  });
});
