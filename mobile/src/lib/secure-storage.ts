import * as SecureStore from 'expo-secure-store';

/**
 * Thin wrapper over the device keychain.
 *
 * Tokens live here and never in AsyncStorage, which is plain unencrypted storage
 * readable on a rooted or jailbroken device. Reads are tolerant of failure because
 * a keychain miss should log the user out, not crash the app on launch.
 */
export const secureStorage = {
  async get(key: string): Promise<string | null> {
    try {
      return await SecureStore.getItemAsync(key);
    } catch {
      return null;
    }
  },

  async set(key: string, value: string): Promise<void> {
    await SecureStore.setItemAsync(key, value);
  },

  async remove(key: string): Promise<void> {
    try {
      await SecureStore.deleteItemAsync(key);
    } catch {
      // Deleting a key that is not there is not a failure worth surfacing.
    }
  },
};

export const SECURE_KEYS = {
  accessToken: 'sync.access_token',
  refreshToken: 'sync.refresh_token',
} as const;
