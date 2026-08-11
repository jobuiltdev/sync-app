import Constants from 'expo-constants';

/**
 * Resolves the API base URL.
 *
 * There is deliberately no localhost fallback. A physical device cannot reach the
 * development machine's loopback interface, so a default of localhost would fail
 * only on real hardware, which is the slowest possible place to discover it.
 * Set EXPO_PUBLIC_API_URL to the machine's LAN address instead, for example
 * http://192.168.1.24:8000.
 */
export function resolveApiBaseUrl(): string {
  const configured = process.env.EXPO_PUBLIC_API_URL;

  if (!configured) {
    throw new Error(
      'EXPO_PUBLIC_API_URL is not set. Copy mobile/.env.example to mobile/.env and ' +
        "set it to your development machine's LAN address, for example " +
        'http://192.168.1.24:8000',
    );
  }

  return configured.replace(/\/+$/, '');
}

export const API_TIMEOUT_MS = 15_000;

export const appVersion = Constants.expoConfig?.version ?? 'unknown';
