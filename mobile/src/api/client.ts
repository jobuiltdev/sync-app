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
}

/**
 * Supplies the bearer token for authenticated requests.
 *
 * The session store registers its getter at startup. Keeping it as a hook rather
 * than importing the store directly stops the API layer depending on app state,
 * which keeps it trivially testable.
 */
type TokenProvider = () => string | null | Promise<string | null>;

let getAccessToken: TokenProvider = () => null;

export function setAccessTokenProvider(provider: TokenProvider): void {
  getAccessToken = provider;
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

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, idempotencyKey, signal, timeoutMs = API_TIMEOUT_MS } = options;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Client-Version': appVersion,
  };

  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  const token = await getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  // Resolved before the try block on purpose: a missing EXPO_PUBLIC_API_URL is a
  // configuration mistake, and catching it below would disguise it as the network
  // being down, which sends whoever hits it looking in entirely the wrong place.
  const url = `${resolveApiBaseUrl()}${path}`;

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

  const payload = await parseBody(response);

  if (!response.ok) {
    throw toApiError(response.status, payload);
  }

  return payload as T;
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
