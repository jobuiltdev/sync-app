import { ApiError } from '@/api/errors';

/**
 * Why an accept or decline did not go through, in the provider's terms.
 *
 * Named for what happened rather than for a status code, so the screen reacts to
 * the domain and not to HTTP. Every one of these is a normal outcome in a market
 * where several providers see the same job.
 */
export type OfferFailure =
  | 'GONE'
  | 'ALREADY_RESPONDED'
  | 'EXPIRED'
  | 'TAKEN'
  | 'VERIFICATION_REQUIRED'
  | 'CONNECTION'
  | 'UNKNOWN';

export interface OfferOutcome {
  failure: OfferFailure;
  message: string;
  /** Requirements still outstanding, when the refusal was a capability one. */
  unmet: string[];
  /** True when the offer is finished and the list should drop it. */
  isFinal: boolean;
}

const BY_CODE: Record<string, OfferFailure> = {
  OFFER_NOT_FOUND: 'GONE',
  OFFER_ALREADY_RESPONDED: 'ALREADY_RESPONDED',
  OFFER_EXPIRED: 'EXPIRED',
  BOOKING_NO_LONGER_AVAILABLE: 'TAKEN',
  VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  PHONE_VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  EMAIL_VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
};

//: Everything except a verification or connection problem means this offer is
//: over. The provider should be shown the inbox again rather than a retry button.
const FINAL: ReadonlySet<OfferFailure> = new Set<OfferFailure>([
  'GONE',
  'ALREADY_RESPONDED',
  'EXPIRED',
  'TAKEN',
]);

export function toOfferOutcome(error: unknown): OfferOutcome | null {
  if (error === null || error === undefined) return null;

  if (!(error instanceof ApiError)) {
    return {
      failure: 'UNKNOWN',
      message: 'Something went wrong. Please try again.',
      unmet: [],
      isFinal: false,
    };
  }

  if (error.isConnectivityError) {
    return { failure: 'CONNECTION', message: error.message, unmet: [], isFinal: false };
  }

  const failure = BY_CODE[error.code] ?? 'UNKNOWN';
  const unmet = Array.isArray(error.details.unmet)
    ? error.details.unmet.filter((value): value is string => typeof value === 'string')
    : [];

  return {
    failure,
    message: error.message,
    unmet,
    isFinal: FINAL.has(failure),
  };
}

export function needsVerification(outcome: OfferOutcome | null): boolean {
  return outcome !== null && outcome.failure === 'VERIFICATION_REQUIRED';
}
