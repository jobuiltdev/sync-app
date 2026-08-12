import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type BookingInput,
  bookingKeys,
  cancelBooking,
  confirmBooking,
  createBooking,
  fetchBooking,
  fetchBookings,
} from '@/api/endpoints/bookings';

export function useBookings() {
  return useQuery({
    queryKey: bookingKeys.all,
    queryFn: ({ signal }) => fetchBookings(signal),
  });
}

export function useBooking(id: string) {
  return useQuery({
    queryKey: bookingKeys.detail(id),
    queryFn: ({ signal }) => fetchBooking(id, signal),
    enabled: Boolean(id),
  });
}

export function useCreateBooking() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: BookingInput) => createBooking(input),
    onSuccess: (booking) => {
      queryClient.setQueryData(bookingKeys.detail(booking.id), booking);
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}

/** Cancel and confirm both move the booking's status server-side, so the cached
 *  copy is replaced with what came back rather than patched locally. */
function useBookingAction(action: (id: string, reason?: string) => Promise<unknown>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => action(id, reason),
    onSuccess: (booking, { id }) => {
      queryClient.setQueryData(bookingKeys.detail(id), booking);
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}

export function useCancelBooking() {
  return useBookingAction(cancelBooking);
}

export function useConfirmBooking() {
  return useBookingAction((id) => confirmBooking(id));
}
