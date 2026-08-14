import { assertUsableApiUrl, resolveApiBaseUrl } from '@/api/config';

/**
 * The rules a release build is held to.
 *
 * `EXPO_PUBLIC_` values are inlined at build time, so a release built on a
 * developer's machine would ship pointing at their laptop. These are what turn
 * that into a loud failure instead of a silent one.
 */
describe('assertUsableApiUrl in a production build', () => {
  const production = true;

  it('accepts a public https URL', () => {
    expect(() => assertUsableApiUrl('https://api.sync.ng', production)).not.toThrow();
  });

  it('refuses plain http', () => {
    // Access tokens would cross the network in the clear.
    expect(() => assertUsableApiUrl('http://api.sync.ng', production)).toThrow(/https/);
  });

  it('refuses a LAN address, which is the mistake this exists to catch', () => {
    // https, so the private-address rule is what refuses these rather than the
    // protocol rule which is checked first.
    for (const host of [
      'https://192.168.1.24:8000',
      'https://10.0.0.5',
      'https://172.16.4.9',
      'https://172.31.255.1',
    ]) {
      expect(() => assertUsableApiUrl(host, production)).toThrow(/private or local/);
    }
  });

  it('refuses the exact URL a developer .env carries', () => {
    // The real mistake: a release built on a machine configured for a phone on
    // the same wifi. It breaks both rules and is refused for whichever comes
    // first, which is all that matters.
    expect(() => assertUsableApiUrl('http://192.168.1.24:8000', production)).toThrow();
  });

  it('refuses loopback', () => {
    for (const host of ['https://localhost:8000', 'https://127.0.0.1:8000']) {
      expect(() => assertUsableApiUrl(host, production)).toThrow(/private or local/);
    }
  });

  it('refuses a link-local address, which is what a device picks when DHCP fails', () => {
    expect(() => assertUsableApiUrl('https://169.254.1.1', production)).toThrow(/private/);
  });

  it('refuses an mDNS hostname', () => {
    expect(() => assertUsableApiUrl('https://joeys-macbook.local', production)).toThrow(/private/);
  });

  it('allows a public address that merely looks similar', () => {
    // 172.15 and 172.32 are outside the private range.
    expect(() => assertUsableApiUrl('https://172.15.0.1', production)).not.toThrow();
    expect(() => assertUsableApiUrl('https://172.32.0.1', production)).not.toThrow();
  });

  it('refuses something that is not a URL at all', () => {
    expect(() => assertUsableApiUrl('not a url', production)).toThrow(/valid URL/);
  });
});

describe('assertUsableApiUrl in a development build', () => {
  it('allows the LAN address a phone actually needs', () => {
    // A physical device cannot reach the development machine's loopback, so a
    // LAN address is the correct configuration locally.
    expect(() => assertUsableApiUrl('http://192.168.1.24:8000', false)).not.toThrow();
  });

  it('allows plain http locally', () => {
    expect(() => assertUsableApiUrl('http://localhost:8000', false)).not.toThrow();
  });
});

describe('resolveApiBaseUrl', () => {
  const original = process.env.EXPO_PUBLIC_API_URL;

  afterEach(() => {
    process.env.EXPO_PUBLIC_API_URL = original;
  });

  it('refuses to guess when nothing is configured', () => {
    delete process.env.EXPO_PUBLIC_API_URL;

    expect(() => resolveApiBaseUrl()).toThrow(/EXPO_PUBLIC_API_URL is not set/);
  });

  it('strips a trailing slash so paths do not double up', () => {
    process.env.EXPO_PUBLIC_API_URL = 'http://192.168.1.24:8000///';

    expect(resolveApiBaseUrl()).toBe('http://192.168.1.24:8000');
  });

  it('carries no credential of any kind', () => {
    // The app holds a base URL and nothing else. Payment happens on the
    // provider's hosted page, so no Paystack key is ever in the bundle.
    process.env.EXPO_PUBLIC_API_URL = 'https://api.sync.ng';

    expect(resolveApiBaseUrl()).toBe('https://api.sync.ng');
    expect(Object.keys(process.env).filter((key) => key.startsWith('EXPO_PUBLIC_'))).toEqual([
      'EXPO_PUBLIC_API_URL',
    ]);
  });
});
