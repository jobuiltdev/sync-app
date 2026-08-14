import { api } from '@/api/client';
import type { Paginated } from '@/api/pagination';

export type PayoutStatus = 'REQUESTED' | 'PROCESSING' | 'PAID' | 'FAILED' | 'CANCELLED';

export type SettlementStatus = 'PAYABLE';

/**
 * The provider's financial position.
 *
 * Every figure is derived server-side from settlements and payouts on each
 * request. Nothing here is cached arithmetic the app could recompute, and it
 * should not try: the balance is whatever the server last said it was.
 */
export interface Earnings {
  currency: string;
  settlement_count: number;
  gross_earned_kobo: number;
  commission_kobo: number;
  net_earned_kobo: number;
  /** Asked for and not yet resolved. Not spent, and not available either. */
  reserved_kobo: number;
  paid_out_kobo: number;
  available_kobo: number;
}

export interface Settlement {
  id: string;
  booking_reference: string;
  service_name: string;
  gross_amount_kobo: number;
  commission_amount_kobo: number;
  provider_amount_kobo: number;
  commission_rate_bps: number;
  currency: string;
  status: SettlementStatus;
  completed_at: string | null;
  created_at: string;
}

export interface Payout {
  id: string;
  amount_kobo: number;
  currency: string;
  status: PayoutStatus;
  requested_at: string;
  processed_at: string | null;
  failure_reason: string;
  /** Whether the server will accept a cancel. Read, never recomputed: the
   *  lifecycle rules live in one place and it is not this one. */
  is_cancellable: boolean;
  allowed_transitions: PayoutStatus[];
  created_at: string;
  updated_at: string;
}

export interface PayoutDestination {
  id: string;
  bank_code: string;
  bank_name: string;
  account_name: string;
  /** All the app ever sees of the account number. The rest is not stored. */
  account_number_last4: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PayoutDestinationInput {
  bank_code: string;
  bank_name: string;
  account_name: string;
  account_number: string;
}

export function fetchEarnings(signal?: AbortSignal): Promise<Earnings> {
  return api.get<Earnings>('/api/v1/provider/earnings/', { signal });
}

export function fetchSettlements(signal?: AbortSignal): Promise<Paginated<Settlement>> {
  return api.get<Paginated<Settlement>>('/api/v1/provider/earnings/settlements/', { signal });
}

export function fetchPayouts(signal?: AbortSignal): Promise<Paginated<Payout>> {
  return api.get<Paginated<Payout>>('/api/v1/provider/payouts/', { signal });
}

export function fetchPayout(id: string, signal?: AbortSignal): Promise<Payout> {
  return api.get<Payout>(`/api/v1/provider/payouts/${id}/`, { signal });
}

/**
 * Asks to be paid.
 *
 * The idempotency key is what makes this safe to retry over a Nigerian mobile
 * connection: a request that timed out may well have been received, and without
 * the key a retry would be a second withdrawal.
 */
export function requestPayout(amountKobo: number, idempotencyKey: string): Promise<Payout> {
  return api.post<Payout>(
    '/api/v1/provider/payouts/request/',
    { amount_kobo: amountKobo },
    { idempotencyKey },
  );
}

export function cancelPayout(id: string): Promise<Payout> {
  return api.post<Payout>(`/api/v1/provider/payouts/${id}/cancel/`, {});
}

export function fetchPayoutDestination(signal?: AbortSignal): Promise<PayoutDestination> {
  return api.get<PayoutDestination>('/api/v1/provider/payout-destination/', { signal });
}

export function savePayoutDestination(
  input: PayoutDestinationInput,
): Promise<PayoutDestination> {
  return api.put<PayoutDestination>('/api/v1/provider/payout-destination/', input);
}

export const paymentKeys = {
  earnings: ['earnings'] as const,
  settlements: ['earnings', 'settlements'] as const,
  payouts: ['payouts'] as const,
  payout: (id: string) => ['payouts', id] as const,
  destination: ['payout-destination'] as const,
};

const STATUS_LABELS: Record<PayoutStatus, string> = {
  REQUESTED: 'Requested',
  PROCESSING: 'On its way',
  PAID: 'Paid',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
};

/** Status codes are for branching; this is what a provider reads. */
export function payoutStatusLabel(status: PayoutStatus): string {
  return STATUS_LABELS[status] ?? status;
}
