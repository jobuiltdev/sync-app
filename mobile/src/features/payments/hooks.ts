import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type PaymentIntent,
  fetchPayment,
  paymentKeys as customerPaymentKeys,
  startPayment,
  verifyPayment,
} from '@/api/endpoints/payments-customer';
import {
  type PayoutDestinationInput,
  cancelPayout,
  isPayoutSettling,
  fetchBanks,
  fetchEarnings,
  fetchPayout,
  fetchPayoutDestination,
  fetchPayouts,
  fetchSettlements,
  paymentKeys,
  requestPayout,
  savePayoutDestination,
  verifyPayoutDestination,
} from '@/api/endpoints/payments';
import { bookingKeys } from '@/api/endpoints/bookings';

export function useEarnings() {
  return useQuery({
    queryKey: paymentKeys.earnings,
    queryFn: ({ signal }) => fetchEarnings(signal),
  });
}

export function useSettlements() {
  return useQuery({
    queryKey: paymentKeys.settlements,
    queryFn: ({ signal }) => fetchSettlements(signal),
  });
}

export function usePayouts() {
  return useQuery({
    queryKey: paymentKeys.payouts,
    queryFn: ({ signal }) => fetchPayouts(signal),
  });
}

/**
 * One payout, refetched while it is still moving.
 *
 * A submitted transfer is resolved by a background task within minutes, and the
 * provider has nothing to do but wait, so the screen asks for them rather than
 * making them pull to refresh. Polling stops the moment it reaches a terminal
 * state, and the server decides which those are.
 */
export function usePayout(id: string) {
  return useQuery({
    queryKey: paymentKeys.payout(id),
    queryFn: ({ signal }) => fetchPayout(id, signal),
    enabled: Boolean(id),
    refetchInterval: (query) => (isPayoutSettling(query.state.data) ? 15_000 : false),
    refetchOnWindowFocus: true,
  });
}

/** Missing is a normal state rather than an error, so a provider who has not
 *  added an account yet sees the form instead of a failure. */
export function usePayoutDestination() {
  return useQuery({
    queryKey: paymentKeys.destination,
    queryFn: ({ signal }) => fetchPayoutDestination(signal),
    retry: false,
  });
}

/**
 * Asks to be paid.
 *
 * The caller supplies the idempotency key and holds it steady across attempts.
 * Generating one here would mint a fresh key on every send, which is the one
 * thing that would make the mechanism useless.
 */
export function useRequestPayout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      amountKobo,
      idempotencyKey,
    }: {
      amountKobo: number;
      idempotencyKey: string;
    }) => requestPayout(amountKobo, idempotencyKey),
    onSuccess: (payout) => {
      queryClient.setQueryData(paymentKeys.payout(payout.id), payout);
      // The balance moved, so anything showing it is stale. Refetched rather
      // than adjusted by hand: the server owns that arithmetic.
      void queryClient.invalidateQueries({ queryKey: paymentKeys.earnings });
      void queryClient.invalidateQueries({ queryKey: paymentKeys.payouts });
    },
  });
}

export function useCancelPayout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => cancelPayout(id),
    onSuccess: (payout) => {
      queryClient.setQueryData(paymentKeys.payout(payout.id), payout);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.earnings });
      void queryClient.invalidateQueries({ queryKey: paymentKeys.payouts });
    },
  });
}

export function useSavePayoutDestination() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: PayoutDestinationInput) => savePayoutDestination(input),
    onSuccess: (destination) => {
      queryClient.setQueryData(paymentKeys.destination, destination);
    },
  });
}

export function useBanks() {
  return useQuery({
    queryKey: paymentKeys.banks,
    queryFn: ({ signal }) => fetchBanks(signal),
    // Bank lists change when a bank merges or a new one is licensed, which is
    // not often. Refetching on every visit would spend a request for nothing.
    staleTime: 24 * 60 * 60 * 1000,
  });
}

/** Confirms the account with the bank. The number is sent again because the
 *  server does not store it. */
export function useVerifyPayoutDestination() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (accountNumber: string) => verifyPayoutDestination(accountNumber),
    onSuccess: (destination) => {
      queryClient.setQueryData(paymentKeys.destination, destination);
      // Whether a payout can be requested has just changed.
      void queryClient.invalidateQueries({ queryKey: paymentKeys.earnings });
    },
  });
}

// --- customer payments -----------------------------------------------------

/**
 * Starts paying for a booking.
 *
 * The caller holds the idempotency key steady across attempts, for the same
 * reason a payout request does: a tap that times out may well have been
 * received, and a fresh key would turn the retry into a second collection.
 */
export function useStartPayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      bookingId,
      idempotencyKey,
    }: {
      bookingId: string;
      idempotencyKey: string;
    }) => startPayment(bookingId, idempotencyKey),
    onSuccess: (payment) => {
      queryClient.setQueryData(customerPaymentKeys.detail(payment.id), payment);
    },
  });
}

/**
 * Asks the server to check with the payment provider.
 *
 * Sends nothing. The server ignores any body, so there is nothing useful to put
 * in one, and a status here would be a claim the server is right to disregard.
 */
export function useVerifyPayment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => verifyPayment(id),
    onSuccess: (payment: PaymentIntent) => {
      queryClient.setQueryData(customerPaymentKeys.detail(payment.id), payment);
      // A successful payment can settle a completed booking, so the booking the
      // customer is looking at may have changed too.
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}

export function usePayment(id: string) {
  return useQuery({
    queryKey: customerPaymentKeys.detail(id),
    queryFn: ({ signal }) => fetchPayment(id, signal),
    enabled: Boolean(id),
  });
}
