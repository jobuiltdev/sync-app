/**
 * The Sync mark, as numbers.
 *
 * Shared by the static mark and the launch animation so the two can never
 * disagree about where a route sits. The animation's final frame is the static
 * mark precisely because both read these values.
 */

/** Every path is authored against this square. */
export const MARK_VIEWBOX = 64;

export const ROUTE_UPPER_PATH = 'M47 12H31C20 12 13 20 13 30C13 39 20 44 29 44';
export const ROUTE_LOWER_PATH = 'M28 27C40 27 49 34 49 43C49 52 42 55 32 55H17';

export const ROUTE_STROKE_WIDTH = 7;

export const NODE_UPPER = { cx: 52, cy: 12, r: 4 } as const;
export const NODE_LOWER = { cx: 12, cy: 55, r: 4 } as const;
export const NODE_STROKE_WIDTH = 4;

/**
 * The lower route, written backwards, for the formation only.
 *
 * The canonical path runs from inside the S outward to (17, 55). The formation
 * needs the opposite: the reveal has to start where the incoming network route
 * makes contact, which is that outer end, and travel inward. A dash reveal only
 * grows from a path's own start, so the path has to start there.
 *
 * Geometrically identical to `ROUTE_LOWER_PATH`, to the limit of the sampling
 * used to check it: same anchors, same handles, same arc length, reversed order.
 * A test holds it to that, because this is the one place two strings have to
 * describe the same curve and nothing else would catch them drifting.
 *
 * The upper route already runs outer-to-inner, so it needs no counterpart.
 */
export const ROUTE_LOWER_REVEAL_PATH = 'M17 55H32C42 55 49 52 49 43C49 34 40 27 28 27';

/**
 * Arc lengths, measured at authoring time.
 *
 * A dash reveal needs the length of the path it is trimming. Measuring one at
 * runtime means `getTotalLength` on a mounted node, which is a JS round trip per
 * path and a thing that can fail; these are the same numbers, sampled offline at
 * 200000 steps per segment and rounded to three decimals. Both are accurate to
 * better than a thousandth of a unit, which at a 7 unit stroke is nothing.
 */
export const MARK_UPPER_LENGTH = 68.457;
export const MARK_LOWER_LENGTH = 68.018;
