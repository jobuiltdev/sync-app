import { api } from '@/api/client';
import type { Paginated } from '@/api/pagination';

export type BookingStatus =
  | 'ASSIGNED'
  | 'EN_ROUTE'
  | 'IN_PROGRESS'
  | 'AWAITING_CONFIRMATION'
  | 'COMPLETED'
  | 'CANCELLED';

export type ActorType = 'CUSTOMER' | 'PROVIDER' | 'SYSTEM' | 'ADMIN';

/** The address as it was when the booking was made. Not a live reference: editing
 *  or deleting the saved address leaves this untouched. */
export interface BookingAddress {
  label: string;
  street_address: string;
  landmark: string;
  area: string;
  lga: string;
  state: string;
  latitude: string | null;
  longitude: string | null;
  directions_note: string;
}

export interface BookingStatusEvent {
  id: string;
  from_status: BookingStatus | '';
  to_status: BookingStatus;
  actor_type: ActorType;
  reason: string;
  created_at: string;
}

export interface BookingSummary {
  id: string;
  reference: string;
  status: BookingStatus;
  service_slug: string;
  service_name: string;
  /** Null while the booking is still MATCHING and nobody has taken it. */
  provider_name: string | null;
  address_summary: string;
  /** What the customer agreed to pay, fixed when the booking was made. */
  total_kobo: number;
  scheduled_for: string | null;
  created_at: string;
}

export interface BookingDetail extends Omit<BookingSummary, 'address_summary'> {
  customer_name: string;
  spec_key: string;
  details: Record<string, unknown>;
  address: BookingAddress;
  completed_at: string | null;
  cancelled_at: string | null;
  updated_at: string;
  events: BookingStatusEvent[];
  /** What the booking could move to next. Advisory: whether this user may perform
   *  one is decided server-side by the action endpoints. */
  allowed_transitions: BookingStatus[];
}

export interface BookingInput {
  service_slug: string;
  provider_id: string;
  address_id: string;
  details: Record<string, unknown>;
  scheduled_for?: string | null;
}

export function fetchBookings(signal?: AbortSignal): Promise<Paginated<BookingSummary>> {
  return api.get<Paginated<BookingSummary>>('/api/v1/customer/bookings/', { signal });
}

export function fetchBooking(id: string, signal?: AbortSignal): Promise<BookingDetail> {
  return api.get<BookingDetail>(`/api/v1/customer/bookings/${id}/`, { signal });
}

export function createBooking(input: BookingInput): Promise<BookingDetail> {
  return api.post<BookingDetail>('/api/v1/customer/bookings/', input);
}

export function cancelBooking(id: string, reason?: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/customer/bookings/${id}/cancel/`, { reason });
}

export function confirmBooking(id: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/customer/bookings/${id}/confirm/`, {});
}

export const bookingKeys = {
  all: ['bookings'] as const,
  detail: (id: string) => ['bookings', id] as const,
};

const STATUS_LABELS: Record<BookingStatus, string> = {
  ASSIGNED: 'Booked',
  EN_ROUTE: 'On the way',
  IN_PROGRESS: 'In progress',
  AWAITING_CONFIRMATION: 'Awaiting your confirmation',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
};

/** Status codes are for branching; this is what a customer reads. */
export function statusLabel(status: BookingStatus): string {
  return STATUS_LABELS[status] ?? status;
}
