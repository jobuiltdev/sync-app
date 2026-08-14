import Constants from 'expo-constants';

/**
 * Where the app talks to, and the rules about what it is allowed to talk to.
 *
 * `EXPO_PUBLIC_` variables are inlined into the bundle at build time, so this is
 * build configuration rather than runtime configuration: a release build carries
 * whatever the machine that built it had set. That is exactly the mistake worth
 * guarding against, because a developer's `.env` points at a LAN address and a
 * release built on that machine would ship pointing at a laptop.
 *
 * So production builds are held to two rules, checked here and enforced by the
 * tests: the URL must be HTTPS, and it must not be a private or loopback
 * address. A build that breaks either fails at the first request with an
 * explanation, rather than shipping to a store and failing silently on a
 * stranger's phone.
 *
 * Nothing secret lives here. `EXPO_PUBLIC_` values are readable by anyone with
 * the app, so the only backend value the app holds is the base URL. Payment
 * happens on the provider's hosted page and the app never sees a Paystack key of
 * any kind, secret or public.
 */

/** Loopback and the private ranges. A production build must reach none of these. */
const PRIVATE_HOST = new RegExp(
  [
    '^localhost$',
    '^127\\.',
    '^0\\.0\\.0\\.0$',
    '^10\\.',
    '^192\\.168\\.',
    // 172.16.0.0 through 172.31.255.255
    '^172\\.(1[6-9]|2\\d|3[01])\\.',
    // Link-local, which is what a device gives itself when DHCP fails.
    '^169\\.254\\.',
    '\\.local$',
  ].join('|'),
);

/**
 * Whether this bundle was built for release.
 *
 * `__DEV__` is false in any production build, which is the signal Expo and React
 * Native already use. Deriving it rather than adding another environment
 * variable means there is no second switch to forget to set.
 */
export function isProductionBuild(): boolean {
  return !__DEV__;
}

export function assertUsableApiUrl(url: string, production: boolean): void {
  if (!production) return;

  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`EXPO_PUBLIC_API_URL is not a valid URL: ${url}`);
  }

  if (parsed.protocol !== 'https:') {
    throw new Error(
      `EXPO_PUBLIC_API_URL must be https in a production build, got ${parsed.protocol}//. ` +
        'Plain HTTP would send access tokens over the network in the clear.',
    );
  }

  if (PRIVATE_HOST.test(parsed.hostname)) {
    throw new Error(
      `EXPO_PUBLIC_API_URL points at ${parsed.hostname}, which is a private or local ` +
        'address. This build was made with a development configuration and cannot ' +
        'reach the API from a customer device.',
    );
  }
}

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

  const url = configured.replace(/\/+$/, '');
  assertUsableApiUrl(url, isProductionBuild());

  return url;
}

export const API_TIMEOUT_MS = 15_000;

export const appVersion = Constants.expoConfig?.version ?? 'unknown';
