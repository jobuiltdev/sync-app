import type { BookingSummary } from '@/api/endpoints/bookings';
import type { OfferSummary } from '@/api/endpoints/offers';
import { answerableOffers, bucketBookings } from '@/features/activity/hooks';

function booking(overrides: Partial<BookingSummary>): BookingSummary {
  return {
    id: 'b1',
    reference: 'SY-1',
    status: 'MATCHING',
    service_slug: 'standard-clean',
    service_name: 'Standard clean',
    provider_name: null,
    address_summary: 'Victoria Island',
    total_kobo: 2_000_000,
    scheduled_for: null,
    created_at: '2026-08-01T10:00:00Z',
    ...overrides,
  };
}

function offer(overrides: Partial<OfferSummary>): OfferSummary {
  return {
    id: 'o1',
    kind: 'BROADCAST',
    status: 'PENDING',
    booking_reference: 'SY-1',
    booking_status: 'MATCHING',
    service_name: 'Standard clean',
    service_slug: 'standard-clean',
    area: 'Victoria Island',
    lga: 'Eti-Osa',
    state: 'LAGOS',
    scheduled_for: null,
    sent_at: '2026-08-01T10:00:00Z',
    expires_at: '2026-08-01T10:15:00Z',
    responded_at: null,
    is_actionable: true,
    ...overrides,
  };
}

describe('bucketing bookings for Activity', () => {
  it('keeps everything still moving in the open bucket', () => {
    const { open, past } = bucketBookings([
      booking({ id: 'a', status: 'MATCHING' }),
      booking({ id: 'b', status: 'EN_ROUTE' }),
      booking({ id: 'c', status: 'AWAITING_CONFIRMATION' }),
    ]);

    expect(open.map((b) => b.id)).toEqual(['a', 'b', 'c']);
    expect(past).toHaveLength(0);
  });

  it('moves finished bookings to past', () => {
    const { open, past } = bucketBookings([
      booking({ id: 'a', status: 'COMPLETED' }),
      booking({ id: 'b', status: 'CANCELLED' }),
      booking({ id: 'c', status: 'EXPIRED' }),
    ]);

    expect(open).toHaveLength(0);
    expect(past.map((b) => b.id)).toEqual(['a', 'b', 'c']);
  });

  it('handles an empty list', () => {
    expect(bucketBookings([])).toEqual({ open: [], past: [] });
  });
});

describe('choosing which offers to surface', () => {
  it('drops offers the server no longer considers answerable', () => {
    // Never recomputed from expires_at against the device clock: a phone with a
    // wrong clock would show a button that is guaranteed to fail.
    const result = answerableOffers([
      offer({ id: 'live', is_actionable: true }),
      offer({ id: 'gone', is_actionable: false, status: 'SUPERSEDED' }),
    ]);

    expect(result.map((o) => o.id)).toEqual(['live']);
  });

  it('puts the offer closest to lapsing first', () => {
    const result = answerableOffers([
      offer({ id: 'later', expires_at: '2026-08-01T11:00:00Z' }),
      offer({ id: 'sooner', expires_at: '2026-08-01T10:05:00Z' }),
    ]);

    expect(result.map((o) => o.id)).toEqual(['sooner', 'later']);
  });

  it('does not mutate the list it was given', () => {
    const offers = [
      offer({ id: 'later', expires_at: '2026-08-01T11:00:00Z' }),
      offer({ id: 'sooner', expires_at: '2026-08-01T10:05:00Z' }),
    ];

    answerableOffers(offers);

    expect(offers.map((o) => o.id)).toEqual(['later', 'sooner']);
  });
});
