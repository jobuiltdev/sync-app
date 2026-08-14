import { ApiError } from '@/api/errors';

/**
 * Why a payout action did not go through, in the provider's terms.
 *
 * Named for what happened rather than for a status code. A provider being told
 * "422" about their own money is a provider who calls support, so every one of
 * these carries the message the server sent and a flag saying whether trying
 * again could possibly help.
 */
export type PayoutFailure =
  | 'VERIFICATION_REQUIRED'
  | 'NO_DESTINATION'
  | 'INSUFFICIENT_BALANCE'
  | 'ALREADY_REQUESTED'
  | 'NOT_ACTIONABLE'
  | 'GONE'
  | 'INVALID_AMOUNT'
  | 'CONNECTION'
  | 'UNKNOWN';

export interface PayoutOutcome {
  failure: PayoutFailure;
  message: string;
  /** Requirements still outstanding, when the refusal was a capability one. */
  unmet: string[];
  /** What the server says is available, when it told us. Kobo. */
  availableKobo: number | null;
  /** Whether sending the same request again could succeed. */
  isRetryable: boolean;
}

const BY_CODE: Record<string, PayoutFailure> = {
  VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  PHONE_VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  EMAIL_VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  INVALID_PAYOUT_DESTINATION: 'NO_DESTINATION',
  INSUFFICIENT_BALANCE: 'INSUFFICIENT_BALANCE',
  PAYOUT_ALREADY_REQUESTED: 'ALREADY_REQUESTED',
  PAYOUT_NOT_ACTIONABLE: 'NOT_ACTIONABLE',
  PAYOUT_NOT_FOUND: 'GONE',
  INVALID_PAYOUT_AMOUNT: 'INVALID_AMOUNT',
  VALIDATION_ERROR: 'INVALID_AMOUNT',
  PROVIDER_PROFILE_NOT_FOUND: 'GONE',
};

//: Only a dropped connection is worth sending again unchanged. Everything else
//: needs the provider to do something first, so offering a retry button would be
//: offering the same refusal a second time.
const RETRYABLE: ReadonlySet<PayoutFailure> = new Set<PayoutFailure>(['CONNECTION', 'UNKNOWN']);

function readAvailable(details: Record<string, unknown>): number | null {
  const value = details.available_kobo;
  return typeof value === 'number' ? value : null;
}

export function toPayoutOutcome(error: unknown): PayoutOutcome | null {
  if (error === null || error === undefined) return null;

  if (!(error instanceof ApiError)) {
    return {
      failure: 'UNKNOWN',
      message: 'Something went wrong. Please try again.',
      unmet: [],
      availableKobo: null,
      isRetryable: true,
    };
  }

  if (error.isConnectivityError) {
    return {
      failure: 'CONNECTION',
      message: error.message,
      unmet: [],
      availableKobo: null,
      isRetryable: true,
    };
  }

  const failure = BY_CODE[error.code] ?? 'UNKNOWN';
  const unmet = Array.isArray(error.details.unmet)
    ? error.details.unmet.filter((value): value is string => typeof value === 'string')
    : [];

  return {
    failure,
    message: error.message,
    unmet,
    availableKobo: readAvailable(error.details),
    isRetryable: RETRYABLE.has(failure),
  };
}

export function needsVerification(outcome: PayoutOutcome | null): boolean {
  return outcome !== null && outcome.failure === 'VERIFICATION_REQUIRED';
}

export function needsDestination(outcome: PayoutOutcome | null): boolean {
  return outcome !== null && outcome.failure === 'NO_DESTINATION';
}
