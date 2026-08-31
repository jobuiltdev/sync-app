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
  /** One line under the field. Written by the vertical, not by the app. */
  help_text: string;
  /** How to render, never what to say. `yes_no` for a boolean that reads better
   *  as two buttons than a switch, `cards` for choices that need explaining,
   *  `multiline` for prose. Anything unrecognised falls back to the default. */
  style: string;
  placeholder: string;
  hint: string;
  /** Human labels for raw choice values, where the value is not presentable. */
  choice_labels: Record<string, string>;
  /** A line explaining each choice, for `cards`. */
  choice_help: Record<string, string>;
  /** What each answer adds to the price, in kobo. Keyed by choice value, or by
   *  `"true"` for a boolean. Absent means it costs nothing. The server computes
   *  the binding figure from the same mapping. */
  price_deltas: Record<string, number>;
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

/** Providers a customer can choose for a service. Discovery only: no ranking,
 *  no availability, no offers. Automatic matching arrives in M4. */
export interface ServiceProvider {
  id: string;
  display_name: string;
  bio: string;
  provider_type: string;
  experience_years: number | null;
  price_kobo: number;
}

export function fetchServiceProviders(
  slug: string,
  signal?: AbortSignal,
): Promise<ServiceProvider[]> {
  return api.get<ServiceProvider[]>(`/api/v1/catalog/services/${slug}/providers/`, { signal });
}

export const catalogKeys = {
  categories: ['catalog', 'categories'] as const,
  service: (slug: string) => ['catalog', 'service', slug] as const,
  providers: (slug: string) => ['catalog', 'service', slug, 'providers'] as const,
};
