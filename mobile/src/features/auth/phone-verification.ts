import { ApiError } from '@/api/errors';

/**
 * The verification states the UI reacts to.
 *
 * Named for the domain, not for HTTP or for a vendor. The screen renders these;
 * it never inspects a status code and never knows who sends the message.
 */
export type VerificationFailure =
  | 'PHONE_NOT_SET'
  | 'ALREADY_VERIFIED'
  | 'COOLDOWN'
  | 'EXPIRED'
  | 'EXHAUSTED'
  | 'INVALID_CODE'
  | 'CHALLENGE_GONE'
  | 'CONNECTION'
  | 'UNKNOWN';

export interface VerificationState {
  failure: VerificationFailure;
  message: string;
  /** Seconds until a resend is allowed, when the server told us. */
  retryAfterSeconds: number | null;
  /** Guesses left on the current challenge, when the server told us. */
  attemptsRemaining: number | null;
}

// Phone and email share one flow server-side, so they share one state map here.
const BY_CODE: Record<string, VerificationFailure> = {
  PHONE_NOT_SET: 'PHONE_NOT_SET',
  PHONE_ALREADY_VERIFIED: 'ALREADY_VERIFIED',
  PHONE_VERIFICATION_COOLDOWN: 'COOLDOWN',
  PHONE_VERIFICATION_EXPIRED: 'EXPIRED',
  PHONE_VERIFICATION_EXHAUSTED: 'EXHAUSTED',
  INVALID_PHONE_VERIFICATION_CODE: 'INVALID_CODE',
  EMAIL_ALREADY_VERIFIED: 'ALREADY_VERIFIED',
  EMAIL_VERIFICATION_COOLDOWN: 'COOLDOWN',
  EMAIL_VERIFICATION_EXPIRED: 'EXPIRED',
  EMAIL_VERIFICATION_EXHAUSTED: 'EXHAUSTED',
  INVALID_EMAIL_VERIFICATION_CODE: 'INVALID_CODE',
  VERIFICATION_CHALLENGE_NOT_FOUND: 'CHALLENGE_GONE',
};

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' ? value : null;
}

export function toVerificationState(error: unknown): VerificationState | null {
  if (error === null || error === undefined) return null;

  if (!(error instanceof ApiError)) {
    return {
      failure: 'UNKNOWN',
      message: 'Something went wrong. Please try again.',
      retryAfterSeconds: null,
      attemptsRemaining: null,
    };
  }

  if (error.isConnectivityError) {
    return {
      failure: 'CONNECTION',
      message: error.message,
      retryAfterSeconds: null,
      attemptsRemaining: null,
    };
  }

  return {
    // The server's timings are authoritative. Recomputing a cooldown in the
    // client would mean two sets of rules that drift apart.
    failure: BY_CODE[error.code] ?? 'UNKNOWN',
    message: error.message,
    retryAfterSeconds: numberOrNull(error.details.retry_after_seconds),
    attemptsRemaining: numberOrNull(error.details.attempts_remaining),
  };
}

/** Whether the current challenge is finished and a new code is the way forward. */
export function needsNewCode(state: VerificationState | null): boolean {
  return (
    state !== null &&
    (state.failure === 'EXPIRED' ||
      state.failure === 'EXHAUSTED' ||
      state.failure === 'CHALLENGE_GONE')
  );
}
