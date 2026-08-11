import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  type AddressInput,
  addressKeys,
  createAddress,
  deleteAddress,
  fetchAddresses,
} from '@/api/endpoints/addresses';
import { catalogKeys, fetchCategories, fetchService } from '@/api/endpoints/catalog';

/** The catalog is public and changes rarely, so it is cached longer than the
 *  default and does not require a session. */
export function useCategories() {
  return useQuery({
    queryKey: catalogKeys.categories,
    queryFn: ({ signal }) => fetchCategories(signal),
    staleTime: 5 * 60 * 1000,
  });
}

export function useService(slug: string) {
  return useQuery({
    queryKey: catalogKeys.service(slug),
    queryFn: ({ signal }) => fetchService(slug, signal),
    staleTime: 5 * 60 * 1000,
    enabled: Boolean(slug),
  });
}

export function useAddresses() {
  return useQuery({
    queryKey: addressKeys.all,
    queryFn: ({ signal }) => fetchAddresses(signal),
  });
}

export function useCreateAddress() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: AddressInput) => createAddress(input),
    // Creating an address can demote another one's default flag server-side, so
    // the whole list is refetched rather than patched optimistically.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: addressKeys.all }),
  });
}

export function useDeleteAddress() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteAddress(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: addressKeys.all }),
  });
}
