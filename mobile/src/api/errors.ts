/**
 * The client side of the API's error envelope.
 *
 * The backend returns every error as
 *   {"error": {"code": "...", "message": "...", "details": {...}}}
 * and this module turns both that and the failure modes that never reach the
 * backend (timeout, no connection, a proxy returning HTML) into one type the app
 * can branch on. Screens should never have to inspect a raw response.
 */

export type ApiErrorCode =
  | 'NETWORK_UNAVAILABLE'
  | 'TIMEOUT'
  | 'UNEXPECTED_RESPONSE'
  | (string & {});

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;
  readonly details: Record<string, unknown>;

  constructor(params: {
    code: ApiErrorCode;
    message: string;
    status?: number | null;
    details?: Record<string, unknown>;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.code = params.code;
    this.status = params.status ?? null;
    this.details = params.details ?? {};
  }

  /**
   * True when the request never reached the server, so retrying is reasonable
   * and the failure is not the user's doing.
   */
  get isConnectivityError(): boolean {
    return this.code === 'NETWORK_UNAVAILABLE' || this.code === 'TIMEOUT';
  }
}

function isEnvelope(body: unknown): body is ApiErrorEnvelope {
  if (typeof body !== 'object' || body === null || !('error' in body)) return false;
  const error = (body as ApiErrorEnvelope).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof error.code === 'string' &&
    typeof error.message === 'string'
  );
}

/**
 * Builds an ApiError from a non-2xx response. A body that does not match the
 * envelope is treated as UNEXPECTED_RESPONSE rather than being guessed at, since
 * that usually means something between the app and Django answered instead.
 */
export function toApiError(status: number, body: unknown): ApiError {
  if (isEnvelope(body)) {
    return new ApiError({
      code: body.error.code,
      message: body.error.message,
      status,
      details: body.error.details,
    });
  }

  return new ApiError({
    code: 'UNEXPECTED_RESPONSE',
    message: 'Something went wrong. Please try again.',
    status,
  });
}

// --- reading an error in the UI --------------------------------------------

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** True when the request never reached the server. Worth an immediate retry,
 *  and worth saying "no connection" rather than blaming the request. */
export function isNetworkError(error: unknown): boolean {
  return isApiError(error) && error.isConnectivityError;
}

/** The stable machine code, for the few places that branch on a specific one. */
export function codeOf(error: unknown): string | null {
  return isApiError(error) ? error.code : null;
}

/**
 * What to show a person.
 *
 * The server's own message is preferred over anything written here, because it
 * is the only thing that knows what actually happened: "Provider not available
 * for this service in your area" is worth infinitely more than a generic
 * apology, and replacing it would be discarding the useful half of the failure.
 * The fallback exists for errors that never reached the API layer at all.
 */
export function messageFor(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === 'NETWORK_UNAVAILABLE') {
      return 'No connection. Check your data or Wi-Fi and try again.';
    }
    if (error.code === 'TIMEOUT') {
      return 'That took too long. Your connection may be slow.';
    }
    return error.message;
  }

  if (error instanceof Error && error.message) return error.message;

  return 'Something went wrong. Please try again.';
}

/**
 * Field-level messages from a validation failure.
 *
 * DRF reports per-field errors in `details`, each an array of strings. Forms use
 * this to put the message on the field it belongs to rather than dumping a
 * summary at the top.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!isApiError(error)) return {};

  const result: Record<string, string> = {};
  for (const [field, value] of Object.entries(error.details)) {
    if (typeof value === 'string') result[field] = value;
    else if (Array.isArray(value) && typeof value[0] === 'string') result[field] = value[0];
  }
  return result;
}
