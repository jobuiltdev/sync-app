import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type PayoutDestinationInput,
  cancelPayout,
  fetchEarnings,
  fetchPayout,
  fetchPayoutDestination,
  fetchPayouts,
  fetchSettlements,
  paymentKeys,
  requestPayout,
  savePayoutDestination,
} from '@/api/endpoints/payments';

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

export function usePayout(id: string) {
  return useQuery({
    queryKey: paymentKeys.payout(id),
    queryFn: ({ signal }) => fetchPayout(id, signal),
    enabled: Boolean(id),
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
