import * as SecureStore from 'expo-secure-store';

import { type AuthSession, type AuthUser, logout, refreshTokens } from '@/api/endpoints/auth';
import { SECURE_KEYS } from '@/lib/secure-storage';
import { useSessionStore } from '@/state/session';

// Babel hoists this above the imports, so the module is mocked before the store
// under test resolves it.
jest.mock('@/api/endpoints/auth', () => ({
  refreshTokens: jest.fn(),
  logout: jest.fn(),
}));

const mockRefresh = refreshTokens as jest.MockedFunction<typeof refreshTokens>;
const mockLogout = logout as jest.MockedFunction<typeof logout>;

const USER = {
  id: 'e6b1c2f0-0000-4000-8000-000000000000',
  email: 'ada@example.com',
  phone: null,
  first_name: 'Ada',
  last_name: 'Okeke',
  full_name: 'Ada Okeke',
  is_email_verified: false,
  is_phone_verified: false,
  email_verified_at: null,
  phone_verified_at: null,
  created_at: '2026-08-11T00:00:00Z',
} satisfies AuthUser;

const SESSION: AuthSession = {
  user: USER,
  tokens: { access: 'access-1', refresh: 'refresh-1' },
};

async function resetStore() {
  await SecureStore.deleteItemAsync(SECURE_KEYS.accessToken);
  await SecureStore.deleteItemAsync(SECURE_KEYS.refreshToken);
  useSessionStore.setState({
    status: 'loading',
    user: null,
    accessToken: null,
    refreshToken: null,
  });
}

describe('session store', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await resetStore();
  });

  describe('hydrate', () => {
    it('resolves to anonymous when the keychain is empty', async () => {
      await useSessionStore.getState().hydrate();

      expect(useSessionStore.getState().status).toBe('anonymous');
    });

    it('restores a stored session', async () => {
      await useSessionStore.getState().signIn(SESSION);
      useSessionStore.setState({ status: 'loading', accessToken: null, refreshToken: null });

      await useSessionStore.getState().hydrate();

      const state = useSessionStore.getState();
      expect(state.status).toBe('authenticated');
      expect(state.accessToken).toBe('access-1');
      expect(state.refreshToken).toBe('refresh-1');
    });

    it('always leaves the loading state, so the router never hangs', async () => {
      await useSessionStore.getState().hydrate();

      expect(useSessionStore.getState().status).not.toBe('loading');
    });
  });

  describe('signIn', () => {
    it('stores tokens in the keychain and marks the session authenticated', async () => {
      await useSessionStore.getState().signIn(SESSION);

      expect(useSessionStore.getState().status).toBe('authenticated');
      expect(useSessionStore.getState().user).toEqual(USER);
      await expect(SecureStore.getItemAsync(SECURE_KEYS.refreshToken)).resolves.toBe('refresh-1');
    });
  });

  describe('renew', () => {
    it('adopts the rotated pair', async () => {
      await useSessionStore.getState().signIn(SESSION);
      mockRefresh.mockResolvedValue({ access: 'access-2', refresh: 'refresh-2' });

      await expect(useSessionStore.getState().renew()).resolves.toBe(true);

      expect(useSessionStore.getState().accessToken).toBe('access-2');
      expect(useSessionStore.getState().refreshToken).toBe('refresh-2');
    });

    it('persists the rotated refresh token, since the old one is now spent', async () => {
      await useSessionStore.getState().signIn(SESSION);
      mockRefresh.mockResolvedValue({ access: 'access-2', refresh: 'refresh-2' });

      await useSessionStore.getState().renew();

      await expect(SecureStore.getItemAsync(SECURE_KEYS.refreshToken)).resolves.toBe('refresh-2');
    });

    it('clears the session when the refresh token is rejected', async () => {
      await useSessionStore.getState().signIn(SESSION);
      mockRefresh.mockRejectedValue(new Error('invalid'));

      await expect(useSessionStore.getState().renew()).resolves.toBe(false);

      expect(useSessionStore.getState().status).toBe('anonymous');
      await expect(SecureStore.getItemAsync(SECURE_KEYS.refreshToken)).resolves.toBeNull();
    });

    it('does nothing without a stored refresh token', async () => {
      await expect(useSessionStore.getState().renew()).resolves.toBe(false);
      expect(mockRefresh).not.toHaveBeenCalled();
    });
  });

  describe('signOut', () => {
    it('clears local state and the keychain', async () => {
      await useSessionStore.getState().signIn(SESSION);
      mockLogout.mockResolvedValue();

      await useSessionStore.getState().signOut();

      const state = useSessionStore.getState();
      expect(state.status).toBe('anonymous');
      expect(state.user).toBeNull();
      await expect(SecureStore.getItemAsync(SECURE_KEYS.accessToken)).resolves.toBeNull();
    });

    it('tells the server to blacklist the refresh token', async () => {
      await useSessionStore.getState().signIn(SESSION);
      mockLogout.mockResolvedValue();

      await useSessionStore.getState().signOut();

      expect(mockLogout).toHaveBeenCalledWith('refresh-1');
    });

    it('signs out locally even when the server call fails', async () => {
      // Tapping sign out must work offline. Leaving someone signed in because a
      // request failed is the worst possible outcome on a shared phone.
      await useSessionStore.getState().signIn(SESSION);
      mockLogout.mockRejectedValue(new Error('offline'));

      await useSessionStore.getState().signOut();

      expect(useSessionStore.getState().status).toBe('anonymous');
      await expect(SecureStore.getItemAsync(SECURE_KEYS.refreshToken)).resolves.toBeNull();
    });
  });
});
