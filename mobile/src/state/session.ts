import { create } from 'zustand';

import { SECURE_KEYS, secureStorage } from '@/lib/secure-storage';

/**
 * Holds the tokens for the current session and nothing else.
 *
 * Server data belongs to TanStack Query, not here. This store exists so the API
 * client has somewhere to read a token from, and so app startup can tell the
 * difference between "not signed in" and "not yet checked". The sign-in and
 * sign-out flows that populate it arrive with the M1 authentication work.
 */
interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  /** False until the keychain has been read, so the UI can hold its first paint. */
  isHydrated: boolean;

  hydrate: () => Promise<void>;
  setTokens: (tokens: { accessToken: string; refreshToken: string }) => Promise<void>;
  clear: () => Promise<void>;
}

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: null,
  refreshToken: null,
  isHydrated: false,

  hydrate: async () => {
    const [accessToken, refreshToken] = await Promise.all([
      secureStorage.get(SECURE_KEYS.accessToken),
      secureStorage.get(SECURE_KEYS.refreshToken),
    ]);
    set({ accessToken, refreshToken, isHydrated: true });
  },

  setTokens: async ({ accessToken, refreshToken }) => {
    await Promise.all([
      secureStorage.set(SECURE_KEYS.accessToken, accessToken),
      secureStorage.set(SECURE_KEYS.refreshToken, refreshToken),
    ]);
    set({ accessToken, refreshToken });
  },

  clear: async () => {
    await Promise.all([
      secureStorage.remove(SECURE_KEYS.accessToken),
      secureStorage.remove(SECURE_KEYS.refreshToken),
    ]);
    set({ accessToken: null, refreshToken: null });
  },
}));

export function getAccessToken(): string | null {
  return useSessionStore.getState().accessToken;
}
