import { api } from '@/api/client';
import type { BookingDetail, BookingStatus } from '@/api/endpoints/bookings';
import type { Paginated } from '@/api/pagination';

export type OfferKind = 'DIRECT' | 'BROADCAST';

export type OfferStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'EXPIRED' | 'SUPERSEDED';

export interface OfferSummary {
  id: string;
  kind: OfferKind;
  status: OfferStatus;
  booking_reference: string;
  booking_status: BookingStatus;
  service_name: string;
  service_slug: string;
  area: string;
  lga: string;
  state: string;
  scheduled_for: string | null;
  sent_at: string;
  expires_at: string;
  responded_at: string | null;
  /** Whether the server considers this offer still answerable. Derived there, not
   *  recomputed here, so a stale clock cannot enable a button that will fail. */
  is_actionable: boolean;
}

export interface OfferDetail extends OfferSummary {
  street_address: string;
  landmark: string;
  directions_note: string;
  spec_key: string;
  details: Record<string, unknown>;
  decline_reason: string;
}

export function fetchOffers(
  params: { all?: boolean } = {},
  signal?: AbortSignal,
): Promise<Paginated<OfferSummary>> {
  const query = params.all ? '?status=all' : '';
  return api.get<Paginated<OfferSummary>>(`/api/v1/provider/offers/${query}`, { signal });
}

export function fetchOffer(id: string, signal?: AbortSignal): Promise<OfferDetail> {
  return api.get<OfferDetail>(`/api/v1/provider/offers/${id}/`, { signal });
}

/** Returns the booking, now assigned to this provider. */
export function acceptOffer(id: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/provider/offers/${id}/accept/`, {});
}

export function declineOffer(id: string, reason?: string): Promise<OfferDetail> {
  return api.post<OfferDetail>(`/api/v1/provider/offers/${id}/decline/`, { reason });
}

export const offerKeys = {
  all: ['offers'] as const,
  list: (showAll: boolean) => ['offers', 'list', showAll] as const,
  detail: (id: string) => ['offers', id] as const,
};

const STATUS_LABELS: Record<OfferStatus, string> = {
  PENDING: 'Awaiting your answer',
  ACCEPTED: 'You accepted',
  DECLINED: 'You declined',
  EXPIRED: 'Lapsed',
  SUPERSEDED: 'Taken by someone else',
};

export function offerStatusLabel(status: OfferStatus): string {
  return STATUS_LABELS[status] ?? status;
}
