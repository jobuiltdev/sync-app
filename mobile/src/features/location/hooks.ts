/**
 * The device's own location, used locally and nowhere else.
 *
 * ### The privacy boundary
 *
 * A provider's position is sensitive operational data. In this milestone it is
 * read **once**, on an explicit tap, held in component state, and used only to
 * draw a second marker and compute a distance. It is never persisted, never
 * sent to the backend, never shown to a customer, and never logged. There is no
 * endpoint that would accept it.
 *
 * That is a deliberate boundary rather than an unfinished one. Live tracking
 * needs a location model, a retention policy, a consent surface and a
 * conversation about what a customer is entitled to see, none of which are
 * decided. Reading a single fix to orient somebody needs none of that.
 *
 * ### Why one fix and not a subscription
 *
 * `watchPositionAsync` would re-render on every GPS update and keep the radio
 * warm, which costs battery on exactly the phones providers are carrying. A
 * provider looking at a job wants to know roughly how far away it is, and that
 * answer does not change meaningfully between renders.
 */

import * as Location from 'expo-location';
import { useCallback, useRef, useState } from 'react';

import type { Coordinate } from '@/features/location/geo';

export type LocationStatus =
  /** Not asked for. The default, and the only state on first render. */
  | 'idle'
  | 'requesting'
  | 'granted'
  /** Refused, which is a normal answer and never blocks the screen. */
  | 'denied'
  /** Permission held but no fix came back: indoors, airplane mode, no GPS. */
  | 'unavailable';

export interface DeviceLocation {
  status: LocationStatus;
  coordinate: Coordinate | null;
  /** Asks for permission and takes one reading. Only ever called from an
   *  explicit user action. Resolves with the fix so a caller can act on it in
   *  the same handler rather than watching state in an effect. */
  request: () => Promise<Coordinate | null>;
}

export function useDeviceLocation(): DeviceLocation {
  const [status, setStatus] = useState<LocationStatus>('idle');
  const [coordinate, setCoordinate] = useState<Coordinate | null>(null);
  // Guards against a double tap firing two permission dialogs.
  const inFlight = useRef(false);

  const request = useCallback(async (): Promise<Coordinate | null> => {
    if (inFlight.current) return null;
    inFlight.current = true;
    setStatus('requesting');

    try {
      const { granted } = await Location.requestForegroundPermissionsAsync();

      if (!granted) {
        // Not an error. Somebody declining to share their position is a choice,
        // and the job's own location is still on the map.
        setStatus('denied');
        return null;
      }

      const position = await Location.getCurrentPositionAsync({
        // Balanced rather than best: a hundred metres is far more accuracy than
        // "how far is this job" needs, and the highest setting can take twenty
        // seconds and a lot of battery to better it.
        accuracy: Location.Accuracy.Balanced,
      });

      const fix: Coordinate = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      };
      setCoordinate(fix);
      setStatus('granted');
      return fix;
    } catch {
      // Deliberately swallowed and never logged: the failure message from the
      // location provider can carry coordinates.
      setStatus('unavailable');
      return null;
    } finally {
      inFlight.current = false;
    }
  }, []);

  return { status, coordinate, request };
}

/** What to tell somebody about the state of their location, in their terms. */
export function locationStatusMessage(status: LocationStatus): string | null {
  switch (status) {
    case 'denied':
      return 'Location is off, so we cannot show how far away you are. The job location is still on the map.';
    case 'unavailable':
      return 'We could not get a fix on your location. This is usually better outdoors.';
    default:
      return null;
  }
}
