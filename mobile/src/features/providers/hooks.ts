import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type ProviderProfileInput,
  type StartVerificationInput,
  fetchVerification,
  fetchVerificationChecklist,
  fetchVerificationHistory,
  resubmitVerification,
  startVerification,
  addProviderArea,
  addProviderService,
  createProviderProfile,
  fetchProviderAreas,
  fetchProviderProfile,
  fetchProviderServices,
  providerKeys,
  removeProviderArea,
  removeProviderService,
  updateProviderProfile,
} from '@/api/endpoints/providers';

/**
 * The provider profile, where not having one is a normal state.
 *
 * An account without a provider side gets a 404 from this endpoint, which is
 * the correct answer rather than an error: most accounts are customers. It is
 * not retried, because retrying a definitive answer three times only makes the
 * onboarding screen slower to render.
 */
export function useProviderProfile() {
  return useQuery({
    queryKey: providerKeys.profile,
    queryFn: ({ signal }) => fetchProviderProfile(signal),
    retry: false,
  });
}

export function useProviderServices(enabled = true) {
  return useQuery({
    queryKey: providerKeys.services,
    queryFn: ({ signal }) => fetchProviderServices(signal),
    enabled,
    retry: false,
  });
}

export function useProviderAreas(enabled = true) {
  return useQuery({
    queryKey: providerKeys.areas,
    queryFn: ({ signal }) => fetchProviderAreas(signal),
    enabled,
    retry: false,
  });
}

export function useCreateProviderProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: ProviderProfileInput) => createProviderProfile(input),
    onSuccess: (profile) => {
      queryClient.setQueryData(providerKeys.profile, profile);
      // Services and areas were not fetched while there was no profile.
      void queryClient.invalidateQueries({ queryKey: providerKeys.services });
      void queryClient.invalidateQueries({ queryKey: providerKeys.areas });
    },
  });
}

export function useUpdateProviderProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: Partial<ProviderProfileInput>) => updateProviderProfile(input),
    onSuccess: (profile) => queryClient.setQueryData(providerKeys.profile, profile),
  });
}

export function useAddProviderService() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (serviceSlug: string) => addProviderService(serviceSlug),
    onSettled: () => queryClient.invalidateQueries({ queryKey: providerKeys.services }),
  });
}

export function useRemoveProviderService() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => removeProviderService(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: providerKeys.services }),
  });
}

export function useAddProviderArea() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ state, lga }: { state: string; lga?: string }) =>
      addProviderArea(state, lga ?? ''),
    onSettled: () => queryClient.invalidateQueries({ queryKey: providerKeys.areas }),
  });
}

export function useRemoveProviderArea() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => removeProviderArea(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: providerKeys.areas }),
  });
}

/**
 * Identity verification.
 *
 * The checklist is the source of truth for what to render and whether the
 * provider may start. Nothing here works out progress from the other queries:
 * a client computing its own is a client that eventually disagrees with the
 * server about whether somebody may begin a paid check.
 */
export function useVerificationChecklist(enabled = true) {
  return useQuery({
    queryKey: providerKeys.verificationChecklist,
    queryFn: ({ signal }) => fetchVerificationChecklist(signal),
    enabled,
    retry: false,
  });
}

/**
 * The current attempt, or null when there has never been one.
 *
 * Never having started is a normal answer rather than an error, and
 * `fetchVerification` resolves it to null, so this query succeeds with no data
 * instead of leaving the screen in an error state. Not retried, for the same
 * reason the profile query is not.
 *
 * The null matters downstream and must not be flattened away: it is what tells
 * a provider approved before verification existed apart from one whose attempt
 * has simply not loaded yet.
 */
export function useVerificationAttempt(enabled = true) {
  return useQuery({
    queryKey: providerKeys.verification,
    queryFn: ({ signal }) => fetchVerification(signal),
    enabled,
    retry: false,
  });
}

export function useVerificationHistory(enabled = true) {
  return useQuery({
    queryKey: providerKeys.verificationHistory,
    queryFn: ({ signal }) => fetchVerificationHistory(signal),
    enabled,
    retry: false,
  });
}

/** Everything a verification action can change, refetched together. */
function useVerificationRefresh() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: providerKeys.verification });
    void client.invalidateQueries({ queryKey: providerKeys.verificationChecklist });
    void client.invalidateQueries({ queryKey: providerKeys.verificationHistory });
    // The profile carries `verification_status`, which a passed check moves to
    // UNDER_REVIEW.
    void client.invalidateQueries({ queryKey: providerKeys.profile });
  };
}

export function useStartVerification() {
  const refresh = useVerificationRefresh();
  return useMutation({
    mutationFn: (input: StartVerificationInput) => startVerification(input),
    onSuccess: refresh,
  });
}

export function useResubmitVerification() {
  const refresh = useVerificationRefresh();
  return useMutation({
    mutationFn: () => resubmitVerification(),
    onSuccess: refresh,
  });
}
