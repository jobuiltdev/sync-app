import { api } from '@/api/client';

/**
 * The provider side of an account.
 *
 * Becoming a provider is not a separate signup: the account already exists and
 * this adds the provider side of it, which is what lets one person be both a
 * customer and a provider without two logins.
 */
export type VerificationStatus =
  | 'PENDING'
  | 'UNDER_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUSPENDED';

export type ProviderType = 'INDIVIDUAL' | 'BUSINESS';

export interface ProviderProfile {
  id: string;
  display_name: string;
  bio: string;
  provider_type: ProviderType;
  business_name: string;
  /** Adjudicated, never self-declared. The API refuses to let this be written,
   *  which is why nothing here sends it. */
  verification_status: VerificationStatus;
  /** The provider's own switch for taking work, separate from whether we allow
   *  them to. Conflating the two would mean reinstating a suspended provider
   *  silently puts them back on call. */
  is_accepting_jobs: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderProfileInput {
  display_name: string;
  bio?: string;
  provider_type?: ProviderType;
  business_name?: string;
  is_accepting_jobs?: boolean;
}

export interface ProviderService {
  id: string;
  service_slug: string;
  service_name: string;
  price_override_kobo: number | null;
  effective_price_kobo: number;
  experience_years: number | null;
  is_active: boolean;
}

export interface ProviderServiceArea {
  id: string;
  state: string;
  /** Blank means the whole state. */
  lga: string;
}

export function fetchProviderProfile(signal?: AbortSignal): Promise<ProviderProfile> {
  return api.get<ProviderProfile>('/api/v1/provider/profile/', { signal });
}

export function createProviderProfile(input: ProviderProfileInput): Promise<ProviderProfile> {
  return api.post<ProviderProfile>('/api/v1/provider/profile/create/', input);
}

/** PATCH rather than PUT: a full replace would make the client resend every
 *  field to change one, and anything it forgot would be silently reset. */
export function updateProviderProfile(
  input: Partial<ProviderProfileInput>,
): Promise<ProviderProfile> {
  return api.patch<ProviderProfile>('/api/v1/provider/profile/', input);
}

export function fetchProviderServices(signal?: AbortSignal): Promise<ProviderService[]> {
  return api.get<ProviderService[]>('/api/v1/provider/services/', { signal });
}

export function addProviderService(serviceSlug: string): Promise<ProviderService> {
  return api.post<ProviderService>('/api/v1/provider/services/', {
    service_slug: serviceSlug,
  });
}

export function removeProviderService(id: string): Promise<void> {
  return api.delete<void>(`/api/v1/provider/services/${id}/`);
}

export function fetchProviderAreas(signal?: AbortSignal): Promise<ProviderServiceArea[]> {
  return api.get<ProviderServiceArea[]>('/api/v1/provider/areas/', { signal });
}

export function addProviderArea(state: string, lga = ''): Promise<ProviderServiceArea> {
  return api.post<ProviderServiceArea>('/api/v1/provider/areas/', { state, lga });
}

export function removeProviderArea(id: string): Promise<void> {
  return api.delete<void>(`/api/v1/provider/areas/${id}/`);
}

export const providerKeys = {
  profile: ['provider', 'profile'] as const,
  services: ['provider', 'services'] as const,
  areas: ['provider', 'areas'] as const,
};

const STATUS_LABELS: Record<VerificationStatus, string> = {
  PENDING: 'Not submitted yet',
  UNDER_REVIEW: 'Being reviewed',
  APPROVED: 'Approved',
  REJECTED: 'Not approved',
  SUSPENDED: 'Suspended',
};

export function verificationStatusLabel(status: VerificationStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/**
 * Why a provider is not receiving offers, in their terms.
 *
 * Advisory only. The server decides eligibility, and this exists so a provider
 * can see what to fix rather than waiting silently for work that will never
 * arrive. Every condition below mirrors one the dispatch filter actually
 * applies, and none of them is checked here to gate anything.
 */
export interface EligibilityGap {
  reason: string;
  action: string;
  route: string;
}

export function eligibilityGaps(
  profile: ProviderProfile | undefined,
  services: ProviderService[] | undefined,
  areas: ProviderServiceArea[] | undefined,
  phoneVerified: boolean,
  emailVerified: boolean,
): EligibilityGap[] {
  const gaps: EligibilityGap[] = [];

  if (!profile) {
    return [
      {
        reason: 'You have not created a provider profile yet.',
        action: 'Create your profile',
        route: '/provider',
      },
    ];
  }

  if (profile.verification_status !== 'APPROVED') {
    gaps.push({
      reason: `Your provider verification is ${verificationStatusLabel(
        profile.verification_status,
      ).toLowerCase()}. Sync reviews every provider before they can enter a customer's home.`,
      action: 'Nothing to do here yet',
      route: '/provider',
    });
  }

  if (!profile.is_accepting_jobs) {
    gaps.push({
      reason: 'You are marked as not taking work.',
      action: 'Turn on taking work',
      route: '/provider',
    });
  }

  if (!services || services.filter((service) => service.is_active).length === 0) {
    gaps.push({
      reason: 'You have not listed any services.',
      action: 'Add a service',
      route: '/provider',
    });
  }

  if (!areas || areas.length === 0) {
    gaps.push({
      reason: 'You have not said where you work.',
      action: 'Add an area',
      route: '/provider',
    });
  }

  // Accepting a job needs both contact channels proven. Listed last because it
  // is the one a provider hits at the moment they try to accept rather than
  // while waiting.
  if (!phoneVerified || !emailVerified) {
    gaps.push({
      reason: 'Accepting a job needs a verified phone and email.',
      action: 'Verify your details',
      route: '/verify-phone',
    });
  }

  return gaps;
}
