import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { bookingKeys } from '@/api/endpoints/bookings';
import {
  acceptOffer,
  declineOffer,
  fetchOffer,
  fetchOffers,
  offerKeys,
} from '@/api/endpoints/offers';

/** The provider inbox.
 *
 *  Refetched on an interval rather than pushed: there is no notification
 *  infrastructure yet, and an offer the provider never sees is a job lost. The
 *  interval is short because offers expire. */
export function useOffers(showAll = false) {
  return useQuery({
    queryKey: offerKeys.list(showAll),
    queryFn: ({ signal }) => fetchOffers({ all: showAll }, signal),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useOffer(id: string) {
  return useQuery({
    queryKey: offerKeys.detail(id),
    queryFn: ({ signal }) => fetchOffer(id, signal),
    enabled: Boolean(id),
  });
}

/** Both responses change the inbox and may change the provider's job list, so
 *  everything touching either is refetched rather than patched by hand. */
function useOfferResponse<T>(respond: (id: string) => Promise<T>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id }: { id: string; reason?: string }) => respond(id),
    onSettled: (_data, _error, { id }) => {
      void queryClient.invalidateQueries({ queryKey: offerKeys.all });
      void queryClient.invalidateQueries({ queryKey: offerKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}

export function useAcceptOffer() {
  return useOfferResponse((id) => acceptOffer(id));
}

export function useDeclineOffer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => declineOffer(id, reason),
    onSettled: (_data, _error, { id }) => {
      void queryClient.invalidateQueries({ queryKey: offerKeys.all });
      void queryClient.invalidateQueries({ queryKey: offerKeys.detail(id) });
    },
  });
}
