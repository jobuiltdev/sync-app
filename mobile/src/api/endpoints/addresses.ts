import { api } from '@/api/client';
import type { Paginated } from '@/api/pagination';

export type AddressLabel = 'HOME' | 'WORK' | 'OTHER';

export interface Address {
  id: string;
  label: AddressLabel;
  street_address: string;
  /** Required by the API. Street addresses are frequently unusable here, and a
   *  landmark is what a provider actually navigates by. */
  landmark: string;
  area: string;
  lga: string;
  state: string;
  latitude: string | null;
  longitude: string | null;
  directions_note: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface AddressInput {
  label?: AddressLabel;
  street_address: string;
  landmark: string;
  area?: string;
  lga?: string;
  state: string;
  directions_note?: string;
  is_default?: boolean;
  /**
   * The map pin, sent as strings.
   *
   * The API has always accepted these and validated them as a pair; nothing on
   * the client ever sent them, so every address and therefore every booking
   * snapshot had no coordinates and the dispatch map had nothing to plot.
   *
   * Strings rather than numbers because the column is a fixed-precision decimal
   * and a float is not a safe carrier for one. They must be sent together or
   * not at all: the serializer refuses a half-set pair.
   */
  latitude?: string | null;
  longitude?: string | null;
}

export function fetchAddresses(signal?: AbortSignal): Promise<Paginated<Address>> {
  return api.get<Paginated<Address>>('/api/v1/customer/addresses/', { signal });
}

export function createAddress(input: AddressInput): Promise<Address> {
  return api.post<Address>('/api/v1/customer/addresses/', input);
}

export function updateAddress(id: string, input: Partial<AddressInput>): Promise<Address> {
  return api.patch<Address>(`/api/v1/customer/addresses/${id}/`, input);
}

export function deleteAddress(id: string): Promise<void> {
  return api.delete<void>(`/api/v1/customer/addresses/${id}/`);
}

export const addressKeys = {
  all: ['addresses'] as const,
};
