import { directionsFallbackUrl, directionsUrl } from '@/features/location/directions';

const VI = { latitude: 6.428055, longitude: 3.421944 };

describe('handing a destination to the native maps app', () => {
  it('opens Apple Maps on iOS', () => {
    const url = directionsUrl(VI, 'SY-1 Eko Hotel', 'ios');

    expect(url).toContain('maps.apple.com');
    expect(url).toContain('daddr=6.428055,3.421944');
  });

  it('asks for driving directions on iOS', () => {
    expect(directionsUrl(VI, 'job', 'ios')).toContain('dirflg=d');
  });

  it('uses the geo scheme on Android', () => {
    // `geo:` lets any installed maps application answer, rather than hard-coding
    // Google Maps onto a phone that may prefer something else.
    const url = directionsUrl(VI, 'SY-1', 'android');

    expect(url.startsWith('geo:')).toBe(true);
    expect(url).toContain('6.428055,3.421944');
  });

  it('names the pin so the other app does not show bare coordinates', () => {
    expect(directionsUrl(VI, 'Eko Hotel gate', 'android')).toContain('Eko%20Hotel%20gate');
  });

  it('falls back to a name when the label is empty', () => {
    expect(directionsUrl(VI, '   ', 'ios')).toContain('Sync%20job');
    expect(directionsUrl(VI, undefined, 'ios')).toContain('Sync%20job');
  });

  it('escapes a label that would otherwise break the URL', () => {
    const url = directionsUrl(VI, 'Flat 3 & 4, "the annex"', 'android');

    expect(url).not.toContain('"');
    expect(url).not.toContain(' ');
  });

  it('gives a browser link on any other platform', () => {
    const url = directionsUrl(VI, 'job', 'web');

    expect(url).toContain('google.com/maps');
    expect(url).toContain('destination=6.428055,3.421944');
  });

  it('has a fallback that opens without any app installed', () => {
    // A geo: intent with nothing registered throws, and an unhandled throw would
    // take down the job screen over a button.
    const url = directionsFallbackUrl(VI);

    expect(url.startsWith('https://')).toBe(true);
    expect(url).toContain('destination=6.428055,3.421944');
  });

  it('never puts the destination anywhere but the destination parameter', () => {
    // The job's coordinates go to the maps app and nowhere else. No analytics
    // parameter, no referrer, no Sync endpoint.
    const url = directionsUrl(VI, 'job', 'ios');

    expect(url).not.toMatch(/sync|api|track|analytics/i);
  });
});
