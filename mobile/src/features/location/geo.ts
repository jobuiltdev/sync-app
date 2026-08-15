/**
 * Coordinates, distance and directions.
 *
 * Pure functions with no native dependency, deliberately. Everything a map
 * screen decides other than *drawing* lives here, so it is testable without a
 * renderer and survives whatever the map library turns out to be.
 *
 * **Distance is computed on the device and never asked of the backend.** Adding
 * a distance endpoint for a figure two coordinates already determine would be a
 * network round trip, a cache, and a geospatial dependency for arithmetic.
 */

export interface Coordinate {
  latitude: number;
  longitude: number;
}

/**
 * Reads a coordinate pair off an API payload.
 *
 * The API sends decimals as strings, because a float is not a safe carrier for
 * a fixed-precision value. Latitude and longitude are stored and validated as a
 * pair, so a half-set pair means the row is wrong and is treated as no location
 * rather than as a point on the equator.
 */
export function toCoordinate(
  latitude: string | number | null | undefined,
  longitude: string | number | null | undefined,
): Coordinate | null {
  if (latitude === null || latitude === undefined) return null;
  if (longitude === null || longitude === undefined) return null;

  const lat = typeof latitude === 'number' ? latitude : Number.parseFloat(latitude);
  const lng = typeof longitude === 'number' ? longitude : Number.parseFloat(longitude);

  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  // 0,0 is in the Gulf of Guinea. It is a real coordinate and about 600km from
  // Lagos, which makes it exactly the kind of plausible-looking wrong answer an
  // unset pair produces. Nothing Sync serves is there.
  if (lat === 0 && lng === 0) return null;

  return { latitude: lat, longitude: lng };
}

const EARTH_RADIUS_M = 6_371_008.8;

const toRadians = (degrees: number): number => (degrees * Math.PI) / 180;

/**
 * Great-circle distance in metres.
 *
 * Haversine. Straight-line rather than driving distance, which is the honest
 * thing a client can compute: turning it into a road distance needs a routing
 * service, and inventing one by multiplying by a fudge factor would be
 * presenting a guess as a measurement.
 */
export function distanceMetres(from: Coordinate, to: Coordinate): number {
  const dLat = toRadians(to.latitude - from.latitude);
  const dLng = toRadians(to.longitude - from.longitude);

  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(from.latitude)) * Math.cos(toRadians(to.latitude)) * Math.sin(dLng / 2) ** 2;

  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
}

/**
 * Distance as a person reads it.
 *
 * Precision is deliberately low. A provider deciding whether to set off wants
 * "about 4 km", and "4.23 km" implies an accuracy that a straight line between
 * two GPS fixes does not have.
 */
export function formatDistance(metres: number): string {
  if (!Number.isFinite(metres) || metres < 0) return '';

  if (metres < 1000) {
    // To the nearest 50m below a kilometre: a phone's fix is rarely better.
    const rounded = Math.max(50, Math.round(metres / 50) * 50);
    return `${rounded} m`;
  }

  const km = metres / 1000;
  if (km < 10) return `${km.toFixed(1)} km`;

  return `${Math.round(km)} km`;
}

/** The same figure spoken in full, for a screen reader. */
export function describeDistance(metres: number): string {
  if (!Number.isFinite(metres) || metres < 0) return '';

  if (metres < 1000) {
    const rounded = Math.max(50, Math.round(metres / 50) * 50);
    return `Approximately ${rounded} metres away`;
  }

  const km = metres / 1000;
  const value = km < 10 ? km.toFixed(1) : String(Math.round(km));

  return `Approximately ${value} kilometres away`;
}

/**
 * A region that comfortably contains every point given.
 *
 * Returned as a plain object rather than as a map library's type, so the camera
 * can be reasoned about and tested without one. The padding multiplier keeps
 * both markers off the edges, and the floor stops a single point zooming to the
 * maximum level, which looks broken.
 */
export interface Region {
  latitude: number;
  longitude: number;
  latitudeDelta: number;
  longitudeDelta: number;
}

/** Roughly 1.5km at Lagos' latitude. Close enough to read a street, far enough
 *  not to look like an error. */
const MIN_DELTA = 0.014;

export function regionFor(points: Coordinate[]): Region | null {
  if (points.length === 0) return null;

  const lats = points.map((point) => point.latitude);
  const lngs = points.map((point) => point.longitude);

  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);

  return {
    latitude: (minLat + maxLat) / 2,
    longitude: (minLng + maxLng) / 2,
    latitudeDelta: Math.max((maxLat - minLat) * 1.6, MIN_DELTA),
    longitudeDelta: Math.max((maxLng - minLng) * 1.6, MIN_DELTA),
  };
}
