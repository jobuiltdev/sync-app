import type { BookingStatus } from '@/api/endpoints/bookings';
import type { OfferStatus } from '@/api/endpoints/offers';
import type { PaymentStatus } from '@/api/endpoints/payments-customer';
import type { VerificationStatus } from '@/api/endpoints/providers';
import {
  bookingStatusView,
  isBookingOpen,
  jobStatusView,
  offerStatusView,
  paymentStatusView,
  payoutStatusView,
  verificationStatusView,
} from '@/features/status/presentation';

const ALL_BOOKING: BookingStatus[] = [
  'MATCHING',
  'ASSIGNED',
  'EN_ROUTE',
  'IN_PROGRESS',
  'AWAITING_CONFIRMATION',
  'COMPLETED',
  'CANCELLED',
  'EXPIRED',
];

describe('booking status presentation', () => {
  it('has a human label for every status the server can send', () => {
    for (const status of ALL_BOOKING) {
      const view = bookingStatusView(status);
      // The bug this guards: a status missing from the map used to fall through
      // and render the raw code, and MATCHING is the status every booking opens in.
      expect(view.label).not.toBe(status);
      expect(view.label.length).toBeGreaterThan(0);
    }
  });

  it('describes a booking that is still finding a provider', () => {
    const view = bookingStatusView('MATCHING');

    expect(view.label).toBe('Finding a provider');
    expect(view.live).toBe(true);
  });

  it('explains an expired booking rather than leaving it bare', () => {
    expect(bookingStatusView('EXPIRED').detail).toMatch(/nobody took|request it again/i);
  });

  it('marks live states with a dot so colour is not the only signal', () => {
    expect(bookingStatusView('EN_ROUTE').live).toBe(true);
    expect(bookingStatusView('COMPLETED').live).toBe(false);
  });

  it('falls back to the raw status for something it has never seen', () => {
    expect(bookingStatusView('WHAT' as BookingStatus).label).toBe('WHAT');
  });

  it('treats only unfinished statuses as open', () => {
    expect(isBookingOpen('MATCHING')).toBe(true);
    expect(isBookingOpen('AWAITING_CONFIRMATION')).toBe(true);
    expect(isBookingOpen('COMPLETED')).toBe(false);
    expect(isBookingOpen('CANCELLED')).toBe(false);
    expect(isBookingOpen('EXPIRED')).toBe(false);
  });
});

describe('job status presentation', () => {
  it('words the same status differently for the provider', () => {
    expect(jobStatusView('ASSIGNED').label).not.toBe(bookingStatusView('ASSIGNED').label);
  });

  it('tells a provider they are waiting on the customer', () => {
    expect(jobStatusView('AWAITING_CONFIRMATION').label).toMatch(/customer/i);
  });

  it('falls back to the customer wording where there is no provider variant', () => {
    expect(jobStatusView('COMPLETED')).toEqual(bookingStatusView('COMPLETED'));
  });
});

describe('offer status presentation', () => {
  const ALL: OfferStatus[] = ['PENDING', 'ACCEPTED', 'DECLINED', 'EXPIRED', 'SUPERSEDED'];

  it('covers every offer status', () => {
    for (const status of ALL) {
      expect(offerStatusView(status).label).not.toBe(status);
    }
  });

  it('presents a lost race as normal rather than as a failure', () => {
    const view = offerStatusView('SUPERSEDED');

    // Several providers see the same broadcast. Losing is the market working.
    expect(view.tone).not.toBe('danger');
    expect(view.detail).toMatch(/not affected/i);
  });
});

describe('payment status presentation', () => {
  const ALL: PaymentStatus[] = ['INITIALIZED', 'SUCCESSFUL', 'FAILED'];

  it('covers every payment status', () => {
    for (const status of ALL) {
      expect(paymentStatusView(status).label.length).toBeGreaterThan(0);
    }
  });

  it('never claims money moved while a payment is unresolved', () => {
    const view = paymentStatusView('INITIALIZED');

    expect(view.label).not.toMatch(/paid/i);
    expect(view.detail).toMatch(/not received/i);
  });

  it('reassures that a failed payment took no money', () => {
    expect(paymentStatusView('FAILED').detail).toMatch(/no money/i);
  });
});

describe('payout status presentation', () => {
  it('separates preparing from confirming by the transfer reference', () => {
    const preparing = payoutStatusView({ status: 'PROCESSING', transfer_reference: '' });
    const confirming = payoutStatusView({ status: 'PROCESSING', transfer_reference: 'SYT-1' });

    // The distinction matters: one of these means the money may already be gone.
    expect(preparing.label).toBe('Preparing');
    expect(confirming.label).toBe('Confirming');
    expect(confirming.detail).toMatch(/sent to your bank/i);
  });

  it('says the money came back when a payout failed', () => {
    const view = payoutStatusView({ status: 'FAILED', failure_reason: 'Account dormant.' });

    expect(view.tone).toBe('danger');
    expect(view.detail).toMatch(/back in your balance/i);
    expect(view.detail).toMatch(/Account dormant/);
  });

  it('still explains a failure the bank gave no reason for', () => {
    expect(payoutStatusView({ status: 'FAILED' }).detail).toMatch(/back in your balance/i);
  });

  it('marks a requested payout as cancellable in its wording', () => {
    expect(payoutStatusView({ status: 'REQUESTED' }).detail).toMatch(/cancel/i);
  });

  it('treats paid and cancelled as settled', () => {
    expect(payoutStatusView({ status: 'PAID' }).live).toBe(false);
    expect(payoutStatusView({ status: 'CANCELLED' }).live).toBe(false);
  });
});

describe('provider verification presentation', () => {
  const ALL: VerificationStatus[] = [
    'PENDING',
    'UNDER_REVIEW',
    'APPROVED',
    'REJECTED',
    'SUSPENDED',
  ];

  it('covers every verification status', () => {
    for (const status of ALL) {
      expect(verificationStatusView(status).label).not.toBe(status);
    }
  });

  it('does not present an unreviewed provider as rejected', () => {
    expect(verificationStatusView('PENDING').tone).toBe('neutral');
    expect(verificationStatusView('UNDER_REVIEW').tone).toBe('warning');
  });
});
