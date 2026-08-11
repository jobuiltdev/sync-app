import { API_TIMEOUT_MS, appVersion, resolveApiBaseUrl } from '@/api/config';
import { ApiError, toApiError } from '@/api/errors';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions {
  method?: HttpMethod;
  body?: unknown;
  /** Sent as Idempotency-Key. Required by the API on anything that creates a
   *  booking or moves money, so a retry over a flaky connection cannot duplicate. */
  idempotencyKey?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Opts out of the refresh-and-retry below. The auth endpoints set this: a
   *  refresh call that tried to refresh on failure would recurse forever. */
  skipAuthRefresh?: boolean;
}

/**
 * Supplies the bearer token for authenticated requests.
 *
 * The session store registers its getter at startup. Keeping it as a hook rather
 * than importing the store directly stops the API layer depending on app state,
 * which keeps it trivially testable.
 */
type TokenProvider = () => string | null | Promise<string | null>;

/** Renews the session. Resolves true when a new access token is available. */
type TokenRefresher = () => Promise<boolean>;

let getAccessToken: TokenProvider = () => null;
let refreshSession: TokenRefresher | null = null;

/** Shared so that several requests failing at once trigger one refresh, not one
 *  each. Without this, an authenticated screen firing four queries on resume
 *  would spend four refresh tokens and blacklist three of them. */
let refreshInFlight: Promise<boolean> | null = null;

export function setAccessTokenProvider(provider: TokenProvider): void {
  getAccessToken = provider;
}

export function setTokenRefresher(refresher: TokenRefresher | null): void {
  refreshSession = refresher;
}

/** Test seam. Clears the deduplication state between cases. */
export function resetAuthPlumbing(): void {
  getAccessToken = () => null;
  refreshSession = null;
  refreshInFlight = null;
}

async function refreshOnce(): Promise<boolean> {
  if (!refreshSession) return false;

  refreshInFlight ??= refreshSession().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) return null;

  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function send(
  url: string,
  options: RequestOptions,
  token: string | null,
): Promise<{ response: Response; payload: unknown }> {
  const { method = 'GET', body, idempotencyKey, signal, timeoutMs = API_TIMEOUT_MS } = options;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Client-Version': appVersion,
  };

  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
  if (token) headers.Authorization = `Bearer ${token}`;

  const timeoutController = new AbortController();
  const timeout = setTimeout(() => timeoutController.abort(), timeoutMs);

  // Either the caller cancelling or the timeout firing should abort the request.
  const onExternalAbort = () => timeoutController.abort();
  signal?.addEventListener('abort', onExternalAbort);

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: timeoutController.signal,
    });
  } catch (cause) {
    const timedOut = timeoutController.signal.aborted && !signal?.aborted;
    throw new ApiError({
      code: timedOut ? 'TIMEOUT' : 'NETWORK_UNAVAILABLE',
      message: timedOut
        ? 'The request took too long. Check your connection and try again.'
        : 'No connection. Check your network and try again.',
      details: { cause: String(cause) },
    });
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', onExternalAbort);
  }

  return { response, payload: await parseBody(response) };
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // Resolved before any request work on purpose: a missing EXPO_PUBLIC_API_URL is a
  // configuration mistake, and letting it fall into the network error path below
  // would disguise it as the network being down.
  const url = `${resolveApiBaseUrl()}${path}`;

  let attempt = await send(url, options, await getAccessToken());

  // A 401 on an authenticated call usually means the access token aged out rather
  // than that the session is over. Renew once and replay before surfacing it.
  if (attempt.response.status === 401 && !options.skipAuthRefresh && (await refreshOnce())) {
    attempt = await send(url, options, await getAccessToken());
  }

  if (!attempt.response.ok) {
    throw toApiError(attempt.response.status, attempt.payload);
  }

  return attempt.payload as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};
