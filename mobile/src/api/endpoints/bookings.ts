import { api } from '@/api/client';
import type { Paginated } from '@/api/pagination';

/**
 * Every status the server can send.
 *
 * `MATCHING` and `EXPIRED` were missing here until M9, which mattered more than
 * it looks: a booking *opens* in MATCHING, so the status a customer saw
 * immediately after requesting a job fell through the label lookup and rendered
 * as the raw code. The union now matches `apps.bookings.state.BookingStatus`
 * exactly.
 */
export type BookingStatus =
  | 'MATCHING'
  | 'ASSIGNED'
  | 'EN_ROUTE'
  | 'IN_PROGRESS'
  | 'AWAITING_CONFIRMATION'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'EXPIRED';

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

// --- the provider side of a booking ----------------------------------------
//
// The same booking, from the other end. A provider advances their own work; the
// customer confirms it is done. Which of these the server will accept is decided
// by the actor as well as the edge, so the app reads `allowed_transitions` and
// still lets the server refuse.

export function fetchJobs(signal?: AbortSignal): Promise<Paginated<BookingSummary>> {
  return api.get<Paginated<BookingSummary>>('/api/v1/provider/bookings/', { signal });
}

export function fetchJob(id: string, signal?: AbortSignal): Promise<BookingDetail> {
  return api.get<BookingDetail>(`/api/v1/provider/bookings/${id}/`, { signal });
}

/** Each action is its own route. The client never names a status, so there is no
 *  path by which it could ask for an arbitrary one. */
export function markEnRoute(id: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/provider/bookings/${id}/en-route/`, {});
}

export function startJob(id: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/provider/bookings/${id}/start/`, {});
}

export function finishJob(id: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/provider/bookings/${id}/finish/`, {});
}

export function cancelJob(id: string, reason?: string): Promise<BookingDetail> {
  return api.post<BookingDetail>(`/api/v1/provider/bookings/${id}/cancel/`, { reason });
}

export const jobKeys = {
  all: ['jobs'] as const,
  detail: (id: string) => ['jobs', id] as const,
};

export const bookingKeys = {
  all: ['bookings'] as const,
  detail: (id: string) => ['bookings', id] as const,
};

const STATUS_LABELS: Record<BookingStatus, string> = {
  MATCHING: 'Finding a provider',
  ASSIGNED: 'Booked',
  EN_ROUTE: 'On the way',
  IN_PROGRESS: 'In progress',
  AWAITING_CONFIRMATION: 'Awaiting your confirmation',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  EXPIRED: 'No provider available',
};

/** Status codes are for branching; this is what a customer reads. */
export function statusLabel(status: BookingStatus): string {
  return STATUS_LABELS[status] ?? status;
}
