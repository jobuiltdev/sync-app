/**
 * How verification state should read to a provider.
 *
 * Pure functions, kept apart from the screen so every phrasing decision is
 * unit-testable without rendering anything. Same arrangement as
 * `features/status/presentation`.
 *
 * **Nothing here decides what a provider may do.** Whether they can start a
 * check comes from the server's `can_start_identity_check` and nowhere else.
 * Working it out from the individual booleans would be reimplementing the rule
 * on the client, which is exactly the disagreement the server-computed checklist
 * exists to prevent.
 */

import type {
  AttemptStatus,
  CheckStatus,
  ProviderVerification,
  VerificationChecklist,
} from '@/api/endpoints/providers';
import type { StatusView, Tone } from '@/features/status/presentation';

/** What the provider is looking at, once everything is taken together. */
export type VerificationStage =
  | 'CONTACTS'
  | 'READY'
  | 'CHECKING'
  | 'RETRY'
  | 'AWAITING_REVIEW'
  | 'REJECTED'
  | 'APPROVED'
  | 'APPROVED_WITHOUT_CHECK'
  | 'SUSPENDED';

const ATTEMPT: Record<AttemptStatus, StatusView> = {
  DRAFT: { label: 'Not started', tone: 'neutral', live: false },
  CHECKING: {
    label: 'Checking',
    tone: 'live',
    live: true,
    detail: 'Confirming your identity with NIMC.',
  },
  CHECK_FAILED: {
    label: 'Could not confirm',
    tone: 'warning',
    live: false,
    detail: 'Nothing has been sent for review. You can try again.',
  },
  UNDER_REVIEW: {
    label: 'With the Sync team',
    tone: 'primary',
    live: true,
    detail: 'Your checks passed. Someone is looking at your submission.',
  },
  APPROVED: { label: 'Approved', tone: 'success', live: false },
  REJECTED: {
    label: 'Not approved',
    tone: 'danger',
    live: false,
    detail: 'Read the reason below, fix it, and submit again.',
  },
};

export function attemptStatusView(status: AttemptStatus): StatusView {
  return ATTEMPT[status] ?? { label: status, tone: 'neutral', live: false };
}

const CHECK: Record<CheckStatus, { label: string; tone: Tone }> = {
  PENDING: { label: 'Not checked yet', tone: 'neutral' },
  PASSED: { label: 'Passed', tone: 'success' },
  FAILED: { label: 'Failed', tone: 'danger' },
  UNAVAILABLE: { label: 'Could not be checked', tone: 'warning' },
};

export function checkStatusView(status: CheckStatus) {
  return CHECK[status] ?? CHECK.PENDING;
}

/**
 * Why an external check refused, in words a provider can act on.
 *
 * A closed set, mirroring the server's. A vendor's own message would leak both
 * their vocabulary and, occasionally, details of somebody's record, so the
 * server never sends one and this never renders one.
 */
const REJECTION: Record<string, string> = {
  IDENTITY_NOT_FOUND:
    'We could not find that record. Check the details you gave the identity service and try again.',
  IDENTITY_MISMATCH:
    'The details did not match the record. Make sure your name matches the one on your NIN.',
  FACE_MISMATCH:
    'Your photo did not match the record. Try again somewhere with even lighting and no hat or sunglasses.',
  LIVENESS_FAILED:
    'We could not confirm a live person. Follow the prompts on screen and keep your face in frame.',
  CONSENT_DECLINED: 'You did not approve the check. It cannot run without your consent.',
  AUTHORIZATION_EXPIRED: 'That approval expired before we could use it. Start again.',
  IDENTITY_ALREADY_USED: 'That identity is already linked to another Sync account.',
  VENDOR_UNAVAILABLE: 'The identity service was unreachable. Nothing was recorded. Try again shortly.',
};

export function rejectionMessage(code: string): string {
  if (!code) return '';
  return REJECTION[code] ?? 'That check did not pass. Try again, or contact support.';
}

/**
 * The single question the screen is organised around: what is happening now.
 *
 * Derived from the server's checklist and the latest attempt together, because
 * neither alone answers it. The checklist knows whether a provider may start;
 * the attempt knows what happened last time.
 *
 * `attempt` distinguishes three things and they are not interchangeable:
 * an attempt, `null` for a provider who has definitively never made one, and
 * `undefined` while the query is still in flight. Collapsing null into undefined
 * would make a loading screen indistinguishable from a real answer.
 */
export function verificationStage(
  checklist: VerificationChecklist | undefined,
  attempt: ProviderVerification | null | undefined,
): VerificationStage {
  if (!checklist) return 'CONTACTS';

  if (checklist.verification_status === 'APPROVED') {
    // Approved with nothing behind it. These are accounts approved before
    // identity verification existed, or approved by hand in a test database.
    // Saying "verified" here would be claiming a NIN, face and liveness check
    // that never ran, so it gets its own stage and its own words.
    return attempt === null ? 'APPROVED_WITHOUT_CHECK' : 'APPROVED';
  }
  if (checklist.verification_status === 'SUSPENDED') return 'SUSPENDED';
  if (checklist.blocked_reason === 'CONTACT_NOT_VERIFIED') return 'CONTACTS';

  if (attempt) {
    if (attempt.status === 'UNDER_REVIEW') return 'AWAITING_REVIEW';
    if (attempt.status === 'REJECTED') return 'REJECTED';
    if (attempt.status === 'CHECKING') return 'CHECKING';
    if (attempt.status === 'CHECK_FAILED') return 'RETRY';
  }

  return 'READY';
}

/** The heading and one line of explanation for each stage. */
export const STAGE_COPY: Record<VerificationStage, { title: string; body: string }> = {
  CONTACTS: {
    title: 'Confirm how we reach you',
    body: 'Verify your phone number and email address first. Identity verification cannot start until both are done.',
  },
  READY: {
    title: 'Verify your identity',
    body: 'You approve the check at NIMC. Sync never sees or stores your NIN, only that the check passed and four digits for support.',
  },
  CHECKING: {
    title: 'Checking your identity',
    body: 'This usually takes a few seconds.',
  },
  RETRY: {
    title: 'That did not go through',
    body: 'Nothing has been sent for review. Read what happened below and try again.',
  },
  AWAITING_REVIEW: {
    title: 'With the Sync team',
    body: 'Your checks passed. Someone reviews every provider before they can take work, so this is a person rather than a machine.',
  },
  REJECTED: {
    title: 'Not approved',
    body: 'Read the reason below, put it right, and submit again. Your earlier submissions stay on your record.',
  },
  APPROVED: {
    title: 'You are verified',
    body: 'You can take work. Turn yourself on in the provider workspace when you are ready.',
  },
  APPROVED_WITHOUT_CHECK: {
    title: 'Approved to take work',
    body: 'Your account was approved by the Sync team. It predates identity verification, so no NIN, face match or liveness check is on file. You can take work as normal, and we will let you know if that changes.',
  },
  SUSPENDED: {
    title: 'Your account is suspended',
    body: 'You cannot take work at the moment. Contact support to find out what happens next.',
  },
};
