/**
 * Handing a destination to the phone's own maps app.
 *
 * **Sync does not do turn-by-turn navigation.** It is a solved problem owned by
 * software with offline tiles, live traffic and a voice, and reimplementing a
 * worse version inside a marketplace app would be a year of work to be second
 * best. Sync's job is to know which job, where, and what state it is in; the
 * moment a provider is driving, the phone's maps app is better at everything.
 *
 * The URL is built here rather than at the call site so the platform difference
 * lives in one testable place.
 */

import { Platform } from 'react-native';

import type { Coordinate } from '@/features/location/geo';

/**
 * A URL that opens the platform's maps application at a destination.
 *
 * iOS gets Apple Maps, which every iPhone has. Android gets the `geo:` scheme,
 * which any installed maps application can claim rather than hard-coding Google
 * Maps. The label rides along so the pin is named in the other app instead of
 * showing bare coordinates.
 */
export function directionsUrl(
  destination: Coordinate,
  label?: string,
  platform: string = Platform.OS,
): string {
  const { latitude, longitude } = destination;
  const name = encodeURIComponent((label ?? '').trim() || 'Sync job');

  if (platform === 'ios') {
    // `dirflg=d` asks for driving. Apple Maps falls back sensibly if it cannot.
    return `https://maps.apple.com/?daddr=${latitude},${longitude}&q=${name}&dirflg=d`;
  }

  if (platform === 'android') {
    return `geo:${latitude},${longitude}?q=${latitude},${longitude}(${name})`;
  }

  // Web and anything else: a universal Google Maps link, which resolves in a
  // browser without assuming an app is installed.
  return `https://www.google.com/maps/dir/?api=1&destination=${latitude},${longitude}`;
}

/**
 * The fallback when no maps application answers.
 *
 * A `geo:` intent with nothing registered to handle it throws, and an unhandled
 * throw here would take down the job screen over a button. This is always
 * openable in a browser.
 */
export function directionsFallbackUrl(destination: Coordinate): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${destination.latitude},${destination.longitude}`;
}
