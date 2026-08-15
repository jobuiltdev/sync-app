import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type BookingInput,
  bookingKeys,
  cancelBooking,
  cancelJob,
  confirmBooking,
  createBooking,
  fetchBooking,
  fetchBookings,
  fetchJob,
  fetchJobs,
  finishJob,
  jobKeys,
  markEnRoute,
  startJob,
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

// --- the provider side -----------------------------------------------------

export function useJobs() {
  return useQuery({
    queryKey: jobKeys.all,
    queryFn: ({ signal }) => fetchJobs(signal),
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: jobKeys.detail(id),
    queryFn: ({ signal }) => fetchJob(id, signal),
    enabled: Boolean(id),
  });
}

/**
 * Advancing a job.
 *
 * The response is the booking as the server now sees it, so it replaces the
 * cached copy rather than being patched locally: the lifecycle decides what a
 * booking becomes, and a client guessing would eventually guess wrong.
 */
function useJobAction(action: (id: string) => Promise<unknown>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => action(id),
    onSuccess: (booking, id) => {
      queryClient.setQueryData(jobKeys.detail(id), booking);
      void queryClient.invalidateQueries({ queryKey: jobKeys.all });
      // The customer's view of the same booking has changed too.
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}

export function useMarkEnRoute() {
  return useJobAction(markEnRoute);
}

export function useStartJob() {
  return useJobAction(startJob);
}

export function useFinishJob() {
  return useJobAction(finishJob);
}

export function useCancelJob() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => cancelJob(id, reason),
    onSuccess: (booking, { id }) => {
      queryClient.setQueryData(jobKeys.detail(id), booking);
      void queryClient.invalidateQueries({ queryKey: jobKeys.all });
      void queryClient.invalidateQueries({ queryKey: bookingKeys.all });
    },
  });
}
