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
