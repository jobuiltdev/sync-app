import { api } from '@/api/client';

export interface AuthUser {
  id: string;
  email: string;
  phone: string | null;
  first_name: string;
  last_name: string;
  full_name: string;
  is_email_verified: boolean;
  is_phone_verified: boolean;
  email_verified_at: string | null;
  phone_verified_at: string | null;
  created_at: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface AuthSession {
  user: AuthUser;
  tokens: TokenPair;
}

export interface RegistrationInput {
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
  phone?: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export function register(input: RegistrationInput): Promise<AuthSession> {
  return api.post<AuthSession>('/api/v1/auth/register/', input, { skipAuthRefresh: true });
}

export function login(input: LoginInput): Promise<AuthSession> {
  return api.post<AuthSession>('/api/v1/auth/login/', input, { skipAuthRefresh: true });
}

/** Rotation is on server-side, so the returned refresh token replaces the one
 *  sent and the old one stops working. Callers must persist both. */
export function refreshTokens(refresh: string): Promise<TokenPair> {
  return api.post<TokenPair>('/api/v1/auth/refresh/', { refresh }, { skipAuthRefresh: true });
}

export function logout(refresh: string): Promise<void> {
  return api.post<void>('/api/v1/auth/logout/', { refresh }, { skipAuthRefresh: true });
}

export function fetchCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  return api.get<AuthUser>('/api/v1/auth/me/', { signal });
}

export const authKeys = {
  me: ['auth', 'me'] as const,
};

// --- phone verification ----------------------------------------------------

/** What the client needs to drive the code screen. Never carries the code. */
export interface VerificationChallenge {
  challenge_id: string;
  destination: string;
  expires_at: string;
  attempts_remaining: number;
  resend_available_in_seconds: number;
}

export function updatePhone(phone: string): Promise<AuthUser> {
  return api.put<AuthUser>('/api/v1/auth/phone/', { phone });
}

export function requestPhoneVerification(): Promise<VerificationChallenge> {
  return api.post<VerificationChallenge>('/api/v1/auth/phone/verification/request/', {});
}

export function confirmPhoneVerification(
  challengeId: string,
  code: string,
): Promise<AuthUser> {
  return api.post<AuthUser>('/api/v1/auth/phone/verification/confirm/', {
    challenge_id: challengeId,
    code,
  });
}
