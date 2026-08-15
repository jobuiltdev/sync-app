import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type ProviderProfileInput,
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
