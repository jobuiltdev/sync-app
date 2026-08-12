import { ApiError } from '@/api/errors';

/**
 * Reads the API's verification-required response.
 *
 * The server is the authority on what is required. The app must not predict it,
 * because the policy lives in one place server-side and a stale build guessing at
 * it would either block a customer who is fine or let one through who is not.
 */
export interface VerificationBlock {
  code: string;
  message: string;
  /** Requirements still outstanding, in the order the user should be asked. */
  unmet: string[];
  /** The requirement to resolve first. */
  next: string | null;
}

const VERIFICATION_CODES = new Set([
  'VERIFICATION_REQUIRED',
  'PHONE_VERIFICATION_REQUIRED',
  'EMAIL_VERIFICATION_REQUIRED',
]);

export function toVerificationBlock(error: unknown): VerificationBlock | null {
  if (!(error instanceof ApiError) || !VERIFICATION_CODES.has(error.code)) return null;

  const unmet = Array.isArray(error.details.unmet)
    ? error.details.unmet.filter((r): r is string => typeof r === 'string')
    : [];

  return {
    code: error.code,
    message: error.message,
    unmet,
    next: unmet[0] ?? null,
  };
}

export function isPhoneVerificationRequired(error: unknown): boolean {
  const block = toVerificationBlock(error);
  return block !== null && block.unmet.includes('PHONE_VERIFIED');
}
