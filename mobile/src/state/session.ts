import { create } from 'zustand';

import {
  type AuthSession,
  type AuthUser,
  logout as logoutRequest,
  refreshTokens,
} from '@/api/endpoints/auth';
import { SECURE_KEYS, secureStorage } from '@/lib/secure-storage';

export type SessionStatus = 'loading' | 'authenticated' | 'anonymous';

/**
 * The current session: who is signed in and the tokens proving it.
 *
 * Server data belongs to TanStack Query, not here. This store holds only what the
 * API client needs to authenticate a request and what the router needs to decide
 * which stack to show.
 */
interface SessionState {
  status: SessionStatus;
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;

  hydrate: () => Promise<void>;
  signIn: (session: AuthSession) => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (user: AuthUser) => void;
  /** Exchanges the stored refresh token for a new pair. Resolves false when the
   *  session is genuinely over, having cleared it. */
  renew: () => Promise<boolean>;
}

async function persist(tokens: { access: string; refresh: string }): Promise<void> {
  await Promise.all([
    secureStorage.set(SECURE_KEYS.accessToken, tokens.access),
    secureStorage.set(SECURE_KEYS.refreshToken, tokens.refresh),
  ]);
}

async function forget(): Promise<void> {
  await Promise.all([
    secureStorage.remove(SECURE_KEYS.accessToken),
    secureStorage.remove(SECURE_KEYS.refreshToken),
  ]);
}

export const useSessionStore = create<SessionState>((set, get) => ({
  status: 'loading',
  user: null,
  accessToken: null,
  refreshToken: null,

  hydrate: async () => {
    const [accessToken, refreshToken] = await Promise.all([
      secureStorage.get(SECURE_KEYS.accessToken),
      secureStorage.get(SECURE_KEYS.refreshToken),
    ]);

    // Tokens on disk mean the session is worth trying. Whether the access token is
    // still valid is settled by the first authenticated request, which refreshes
    // transparently if it is not, so there is no need to verify it here.
    set({
      accessToken,
      refreshToken,
      status: refreshToken ? 'authenticated' : 'anonymous',
    });
  },

  signIn: async ({ user, tokens }) => {
    await persist(tokens);
    set({
      user,
      accessToken: tokens.access,
      refreshToken: tokens.refresh,
      status: 'authenticated',
    });
  },

  signOut: async () => {
    const { refreshToken } = get();

    // Clear locally first. Signing out must succeed even with no connection, and a
    // user who taps sign out should never be left signed in because a request
    // failed. The server-side blacklist is best effort on top of that.
    await forget();
    set({ user: null, accessToken: null, refreshToken: null, status: 'anonymous' });

    if (refreshToken) {
      try {
        await logoutRequest(refreshToken);
      } catch {
        // The token expires on its own; nothing useful to tell the user here.
      }
    }
  },

  setUser: (user) => set({ user }),

  renew: async () => {
    const { refreshToken } = get();
    if (!refreshToken) return false;

    try {
      const tokens = await refreshTokens(refreshToken);
      await persist(tokens);
      set({ accessToken: tokens.access, refreshToken: tokens.refresh, status: 'authenticated' });
      return true;
    } catch {
      await forget();
      set({ user: null, accessToken: null, refreshToken: null, status: 'anonymous' });
      return false;
    }
  },
}));

export function getAccessToken(): string | null {
  return useSessionStore.getState().accessToken;
}

export function renewSession(): Promise<boolean> {
  return useSessionStore.getState().renew();
}
