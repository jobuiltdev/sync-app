/**
 * How a lifecycle status should look and read.
 *
 * Pure functions, deliberately. Presentation for four separate lifecycles lives
 * in one place so a booking, an offer, a payment and a payout that are all
 * "waiting" look consistently like waiting, and so all of it is unit-testable
 * without rendering anything.
 *
 * **These map presentation only.** What a user may *do* to a booking comes from
 * the server's `allowed_transitions` and nowhere else. Nothing here decides an
 * action, and adding a decision to this file would be re-implementing the
 * lifecycle on the client, which is exactly what the server exists to prevent.
 */

import type { BookingStatus } from '@/api/endpoints/bookings';
import type { OfferStatus } from '@/api/endpoints/offers';
import type { PaymentStatus } from '@/api/endpoints/payments-customer';
import type { PayoutStatus } from '@/api/endpoints/payments';
import type { VerificationStatus } from '@/api/endpoints/providers';

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'live';

export interface StatusView {
  label: string;
  tone: Tone;
  /** A dot marks something still moving, so live state is distinguishable
   *  without relying on the colour being perceived. */
  live: boolean;
  /** One sentence of plain explanation, where the label alone leaves a real
   *  question unanswered. */
  detail?: string;
}

// --- bookings, as the customer sees them -----------------------------------

const BOOKING: Record<BookingStatus, StatusView> = {
  MATCHING: {
    label: 'Finding a provider',
    tone: 'live',
    live: true,
    detail: 'We are offering this to providers near you.',
  },
  ASSIGNED: {
    label: 'Booked',
    tone: 'primary',
    live: false,
    detail: 'A provider has taken this job.',
  },
  EN_ROUTE: {
    label: 'On the way',
    tone: 'live',
    live: true,
    detail: 'Your provider is travelling to you.',
  },
  IN_PROGRESS: { label: 'In progress', tone: 'live', live: true, detail: 'Work has started.' },
  AWAITING_CONFIRMATION: {
    label: 'Confirm it is done',
    tone: 'warning',
    live: true,
    detail: 'Your provider says the work is finished. Confirm to complete the booking.',
  },
  COMPLETED: { label: 'Completed', tone: 'success', live: false },
  CANCELLED: { label: 'Cancelled', tone: 'neutral', live: false },
  EXPIRED: {
    label: 'No provider available',
    tone: 'neutral',
    live: false,
    detail: 'Nobody took this job in time. You can request it again.',
  },
};

export function bookingStatusView(status: BookingStatus): StatusView {
  return BOOKING[status] ?? { label: status, tone: 'neutral', live: false };
}

/** The same booking from the provider's side, where the wording differs. */
const JOB: Partial<Record<BookingStatus, StatusView>> = {
  ASSIGNED: {
    label: 'Not started',
    tone: 'primary',
    live: false,
    detail: 'Tell the customer when you set off.',
  },
  EN_ROUTE: { label: 'On your way', tone: 'live', live: true },
  IN_PROGRESS: { label: 'Working', tone: 'live', live: true },
  AWAITING_CONFIRMATION: {
    label: 'Waiting on the customer',
    tone: 'warning',
    live: true,
    detail: 'You marked this finished. It completes when the customer confirms.',
  },
};

export function jobStatusView(status: BookingStatus): StatusView {
  return JOB[status] ?? bookingStatusView(status);
}

/** Whether a booking is still going somewhere. Drives which list it appears in. */
export function isBookingOpen(status: BookingStatus): boolean {
  return (
    status === 'MATCHING' ||
    status === 'ASSIGNED' ||
    status === 'EN_ROUTE' ||
    status === 'IN_PROGRESS' ||
    status === 'AWAITING_CONFIRMATION'
  );
}

// --- offers ----------------------------------------------------------------

const OFFER: Record<OfferStatus, StatusView> = {
  PENDING: { label: 'Awaiting your answer', tone: 'live', live: true },
  ACCEPTED: { label: 'You accepted', tone: 'success', live: false },
  DECLINED: { label: 'You declined', tone: 'neutral', live: false },
  EXPIRED: {
    label: 'Lapsed',
    tone: 'neutral',
    live: false,
    detail: 'This offer timed out before it was answered.',
  },
  SUPERSEDED: {
    label: 'Taken by someone else',
    tone: 'neutral',
    live: false,
    // A lost race is not a failure and must not read like one. Providers see
    // this often, and it should not feel like something went wrong.
    detail: 'Another provider accepted first. Your acceptance rate is not affected.',
  },
};

export function offerStatusView(status: OfferStatus): StatusView {
  return OFFER[status] ?? { label: status, tone: 'neutral', live: false };
}

// --- payments --------------------------------------------------------------

const PAYMENT: Record<PaymentStatus, StatusView> = {
  INITIALIZED: {
    label: 'Waiting for payment',
    tone: 'warning',
    live: true,
    // Never states that money moved. The server decides that, after asking the
    // gateway, and returning from a checkout page proves nothing.
    detail: 'We have not received this payment yet.',
  },
  SUCCESSFUL: { label: 'Paid', tone: 'success', live: false },
  FAILED: {
    label: 'Not paid',
    tone: 'danger',
    live: false,
    detail: 'No money left your account. You can try again.',
  },
};

export function paymentStatusView(status: PaymentStatus): StatusView {
  return PAYMENT[status] ?? { label: status, tone: 'neutral', live: false };
}

// --- payouts ---------------------------------------------------------------

/**
 * Payouts need the whole object rather than the status alone.
 *
 * `PROCESSING` means two genuinely different things depending on whether a
 * transfer reference has been reserved: either we are preparing to send, or we
 * have sent and are waiting for the bank to confirm. Collapsing those would
 * tell a provider their money is moving before it is.
 */
export function payoutStatusView(payout: {
  status: PayoutStatus;
  transfer_reference?: string;
  failure_reason?: string;
}): StatusView {
  switch (payout.status) {
    case 'REQUESTED':
      return {
        label: 'Requested',
        tone: 'warning',
        live: true,
        detail: 'Waiting to be sent. You can still cancel it.',
      };
    case 'PROCESSING':
      return payout.transfer_reference
        ? {
            label: 'Confirming',
            tone: 'live',
            live: true,
            detail: 'Sent to your bank. We are confirming it, which usually takes a few minutes.',
          }
        : { label: 'Preparing', tone: 'live', live: true, detail: 'Being prepared to send.' };
    case 'PAID':
      return { label: 'Paid', tone: 'success', live: false, detail: 'Sent to your bank account.' };
    case 'FAILED':
      return {
        label: 'Failed',
        tone: 'danger',
        live: false,
        detail: payout.failure_reason
          ? `${payout.failure_reason} The money is back in your balance.`
          : 'That transfer did not go through. The money is back in your balance.',
      };
    case 'CANCELLED':
      return {
        label: 'Cancelled',
        tone: 'neutral',
        live: false,
        detail: 'You cancelled this. The money is back in your balance.',
      };
    default:
      return { label: payout.status, tone: 'neutral', live: false };
  }
}

// --- provider verification -------------------------------------------------

const VERIFICATION: Record<VerificationStatus, StatusView> = {
  PENDING: {
    label: 'Not submitted',
    tone: 'neutral',
    live: false,
    detail: 'Sync reviews every provider before they can enter a customer home.',
  },
  UNDER_REVIEW: {
    label: 'Being reviewed',
    tone: 'warning',
    live: true,
    detail: 'We are checking your details. Nothing is needed from you.',
  },
  APPROVED: { label: 'Approved', tone: 'success', live: false },
  REJECTED: { label: 'Not approved', tone: 'danger', live: false },
  SUSPENDED: { label: 'Suspended', tone: 'danger', live: false },
};

export function verificationStatusView(status: VerificationStatus): StatusView {
  return VERIFICATION[status] ?? { label: status, tone: 'neutral', live: false };
}
