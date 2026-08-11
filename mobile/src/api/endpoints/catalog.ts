import { api } from '@/api/client';

export type BookingMode = 'ON_DEMAND' | 'SCHEDULED' | 'BOTH';

export type PricingModel = 'FIXED' | 'PER_HOUR' | 'PER_ITEM' | 'DISTANCE' | 'QUOTE_ON_SITE';

export interface ServiceSummary {
  id: string;
  slug: string;
  name: string;
  summary: string;
  category_slug: string;
  booking_modes: BookingMode;
  pricing_model: PricingModel;
  base_price_kobo: number;
}

export interface ServiceCategory {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon_key: string;
  sort_order: number;
  services: ServiceSummary[];
}

export interface ServiceOption {
  id: string;
  key: string;
  label: string;
  kind: 'BOOLEAN' | 'QUANTITY' | 'CHOICE';
  price_delta_kobo: number;
  sort_order: number;
}

/** Describes the vertical-specific fields a request must carry. Served by the API
 *  from the service's spec, so a new category needs no new app build. */
export interface DetailsField {
  name: string;
  type: string;
  required: boolean;
  label: string;
  choices: string[] | null;
}

export interface DetailsSchema {
  key: string;
  fields: DetailsField[];
}

export interface ServiceDetail extends Omit<ServiceSummary, 'summary'> {
  summary: string;
  description: string;
  options: ServiceOption[];
  details_schema: DetailsSchema;
}

export function fetchCategories(signal?: AbortSignal): Promise<ServiceCategory[]> {
  return api.get<ServiceCategory[]>('/api/v1/catalog/categories/', { signal });
}

export function fetchService(slug: string, signal?: AbortSignal): Promise<ServiceDetail> {
  return api.get<ServiceDetail>(`/api/v1/catalog/services/${slug}/`, { signal });
}

export const catalogKeys = {
  categories: ['catalog', 'categories'] as const,
  service: (slug: string) => ['catalog', 'service', slug] as const,
};
