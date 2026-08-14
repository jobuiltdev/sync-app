import { api } from '@/api/client';
import type { Paginated } from '@/api/pagination';

export type PaymentStatus = 'INITIALIZED' | 'SUCCESSFUL' | 'FAILED';

/**
 * One attempt to pay for a booking.
 *
 * `status` is written by the server against what the payment provider reported.
 * The app never asserts it, and there is no endpoint that would accept it if the
 * app tried: after checkout the app asks the server to check, and the server
 * asks the provider.
 */
export interface PaymentIntent {
  id: string;
  reference: string;
  booking: string;
  booking_reference: string;
  amount_kobo: number;
  currency: string;
  status: PaymentStatus;
  /** Card, transfer, USSD. Blank until the provider says. */
  method: string;
  /** Where to send the customer to pay. A single-use checkout link scoped to
   *  this transaction, not a credential. */
  authorization_url: string;
  is_payable: boolean;
  paid_at: string | null;
  failed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Starts collecting payment for a booking. The amount comes from the booking's
 *  own agreed total, so nothing about it is sent from here. */
export function startPayment(
  bookingId: string,
  idempotencyKey: string,
): Promise<PaymentIntent> {
  return api.post<PaymentIntent>(
    `/api/v1/customer/bookings/${bookingId}/pay/`,
    {},
    { idempotencyKey },
  );
}

/**
 * Asks the server to check with the payment provider.
 *
 * Deliberately sends an empty body. The endpoint ignores whatever it is given,
 * and sending a status would be writing a claim the server is right to disregard.
 */
export function verifyPayment(id: string): Promise<PaymentIntent> {
  return api.post<PaymentIntent>(`/api/v1/customer/payments/${id}/verify/`, {});
}

export function fetchPayment(id: string, signal?: AbortSignal): Promise<PaymentIntent> {
  return api.get<PaymentIntent>(`/api/v1/customer/payments/${id}/`, { signal });
}

export function fetchPayments(signal?: AbortSignal): Promise<Paginated<PaymentIntent>> {
  return api.get<Paginated<PaymentIntent>>('/api/v1/customer/payments/', { signal });
}

export const paymentKeys = {
  all: ['payments'] as const,
  detail: (id: string) => ['payments', id] as const,
};

const STATUS_LABELS: Record<PaymentStatus, string> = {
  INITIALIZED: 'Waiting for payment',
  SUCCESSFUL: 'Paid',
  FAILED: 'Not paid',
};

export function paymentStatusLabel(status: PaymentStatus): string {
  return STATUS_LABELS[status] ?? status;
}
