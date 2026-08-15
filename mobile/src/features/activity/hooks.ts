/**
 * The Activity surface.
 *
 * Activity replaced three separate screens in M9: the customer's bookings, the
 * provider's jobs and the provider's offer inbox. They were three lists of the
 * same thing, "work that is happening", split by which side of it you were on,
 * and a person who is both had to remember which screen to open.
 *
 * Nothing new is fetched to build it. It composes the existing booking, job and
 * offer queries, which is what keeps it from becoming a second source of truth
 * about state the server already owns.
 */

import { useMemo } from 'react';

import type { BookingSummary } from '@/api/endpoints/bookings';
import type { OfferSummary } from '@/api/endpoints/offers';
import { useBookings, useJobs } from '@/features/bookings/hooks';
import { useOffers } from '@/features/offers/hooks';
import { useProviderProfile } from '@/features/providers/hooks';
import { isBookingOpen } from '@/features/status/presentation';

export type ActivityScope = 'customer' | 'provider';

/**
 * How many things are waiting on this person right now.
 *
 * Drives the badge on the Activity tab. Counts only what somebody must *act*
 * on, not everything in flight: a job that is merely in progress needs nothing
 * from anybody, and badging it would train people to ignore the badge.
 */
export function useActivityAttention(): number {
  const profile = useProviderProfile();
  const isProvider = Boolean(profile.data);

  const bookings = useBookings();
  const offers = useOffers(false);

  return useMemo(() => {
    const toConfirm = (bookings.data?.results ?? []).filter(
      (booking) => booking.status === 'AWAITING_CONFIRMATION',
    ).length;

    // Only offers the server still considers answerable. Recomputing from
    // `expires_at` against the device clock would badge offers that are already
    // gone.
    const answerable = isProvider
      ? (offers.data?.results ?? []).filter((offer) => offer.is_actionable).length
      : 0;

    return toConfirm + answerable;
  }, [bookings.data, offers.data, isProvider]);
}

export interface ActivityBuckets {
  open: BookingSummary[];
  past: BookingSummary[];
}

/** Splits a booking list into what is still happening and what is finished. */
export function bucketBookings(bookings: BookingSummary[]): ActivityBuckets {
  const open: BookingSummary[] = [];
  const past: BookingSummary[] = [];

  for (const booking of bookings) {
    (isBookingOpen(booking.status) ? open : past).push(booking);
  }

  return { open, past };
}

/** Offers worth showing at the top of the provider's activity: still answerable,
 *  soonest to lapse first, so the one about to disappear is the one in view. */
export function answerableOffers(offers: OfferSummary[]): OfferSummary[] {
  return offers
    .filter((offer) => offer.is_actionable)
    .sort((a, b) => a.expires_at.localeCompare(b.expires_at));
}

/** Everything the customer half of Activity needs. */
export function useCustomerActivity() {
  const bookings = useBookings();

  const buckets = useMemo(
    () => bucketBookings(bookings.data?.results ?? []),
    [bookings.data],
  );

  return { query: bookings, ...buckets };
}

/** Everything the provider half needs. */
export function useProviderActivity() {
  const jobs = useJobs();
  const offers = useOffers(false);

  const value = useMemo(() => {
    const all = jobs.data?.results ?? [];
    return {
      offers: answerableOffers(offers.data?.results ?? []),
      active: all.filter((job) => isBookingOpen(job.status)),
      past: all.filter((job) => !isBookingOpen(job.status)),
    };
  }, [jobs.data, offers.data]);

  return { jobsQuery: jobs, offersQuery: offers, ...value };
}

/** Whether this account has a provider side, which decides whether Activity
 *  offers the provider scope at all. */
export function useIsProvider(): boolean {
  return Boolean(useProviderProfile().data);
}
