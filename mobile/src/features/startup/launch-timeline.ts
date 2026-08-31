import {
  MARK_LOWER_LENGTH,
  MARK_UPPER_LENGTH,
  MARK_VIEWBOX,
  NODE_LOWER,
  NODE_UPPER,
  ROUTE_LOWER_PATH,
  ROUTE_UPPER_PATH,
} from '@/components/brand/mark-geometry';
import {
  NETWORK_VIEWBOX,
  ROUTE_ENDPOINT,
  ROUTE_LENGTH,
} from '@/features/startup/network-geometry';

/**
 * One clock for the whole launch.
 *
 * The first version of this sequence was four independently delayed timings in
 * one component and three more in another, with a React state change in the
 * middle to mount the mark. Every one of them was individually correct and the
 * result was visibly assembled: the network arrived and stopped, the scenery
 * left as though it were its own animation, and then an unrelated mark formed in
 * the centre while the network sat outside waiting to be dismissed.
 *
 * The cause was structural rather than a matter of tuning. Delays are gaps by
 * construction, and nothing forced any two of them to overlap.
 *
 * So there is now exactly one animated value in the entire launch: a linear
 * `progress` from 0 to 1, driven by a single `withTiming`. Every property of
 * every element is an interpolation of bounded ranges of that value, and the
 * ranges overlap on purpose. Nothing waits for anything else to finish, because
 * there is nothing to wait for: at any instant the whole picture is a pure
 * function of one number.
 *
 * The linear clock matters. Easing belongs inside each segment, applied to that
 * segment's own normalised progress. Easing the master value instead would warp
 * every segment at once and make the overlaps drift.
 */

/**
 * How long the whole thing takes.
 *
 * The problem this replaces was continuity, not pace, so the total stays close
 * to what it was. Long enough for six overlapping segments to breathe, short
 * enough that it is never in the way of opening the app.
 */
export const SEQUENCE_MS = 2050;

/**
 * The segments, as ranges of `progress`.
 *
 * Every range overlaps its neighbour. That overlap is the whole design: the
 * indicator sets off before the network has finished arriving, the scenery
 * starts receding while the indicator is still travelling, the primary routes
 * begin converging before the scenery has gone, and the mark is already gaining
 * opacity while those routes are still moving onto it.
 */
export const SEGMENT = {
  /**
   * The contextual route's own slow window, travelling and contracting before
   * the primary streams are anywhere near finished.
   */
  contextFlow: [0.0, 0.56],
  /**
   * One range per stream, covering the **entire** journey: network route,
   * connector and mark reveal, as a single distance. Nothing inside is eased
   * separately, which is the point. Easing each leg meant the stream decelerated
   * to nearly nothing at every boundary, and three smooth legs joined by two
   * stalls is not one movement.
   *
   * Staggered by 0.03, about 60ms at this duration.
   */
  upperFlow: [0.03, 0.86],
  lowerFlow: [0.06, 0.89],
  /** The travelling dots resolving into the mark's endpoint rings. */
  ringResolve: [0.76, 0.9],
  /**
   * The name settling under the symbol.
   *
   * Starts while the rings are still resolving and finishes before the hold
   * does, so the wordmark is fully present for the last six per cent of the
   * sequence and stays that way through the completion boundary. It is one
   * fade and one small lift: the mark has just been built by two routes, and a
   * second piece of choreography underneath it would argue with that.
   */
  wordmarkReveal: [0.82, 0.94],
  /** A calm beat on the finished mark before anything navigates. */
  hold: [0.9, 1.0],
} as const;

/** Normalised progress through one segment, clamped at both ends. */
export function stage(progress: number, range: readonly [number, number]) {
  'worklet';
  const t = (progress - range[0]) / (range[1] - range[0]);
  return t < 0 ? 0 : t > 1 ? 1 : t;
}

/**
 * The two easing curves, as arithmetic.
 *
 * Written out rather than taken from Reanimated's `Easing` because these run
 * inside `useAnimatedStyle` on segment progress, not as the easing argument to a
 * timing. Same curves, and no question about what is worklet-safe.
 */
export function easeOut(t: number) {
  'worklet';
  const inverse = 1 - t;
  return 1 - inverse * inverse * inverse;
}

export function easeInOut(t: number) {
  'worklet';
  const inverse = -2 * t + 2;
  return t < 0.5 ? 4 * t * t * t : 1 - (inverse * inverse * inverse) / 2;
}

/** Eased progress through a segment, which is what nearly every layer wants. */
export function eased(
  progress: number,
  range: readonly [number, number],
  curve: (t: number) => number,
) {
  'worklet';
  return curve(stage(progress, range));
}

export interface Vector {
  x: number;
  y: number;
}

/**
 * Which piece of the network becomes which piece of the mark.
 *
 * This is the correction the recorded review asked for. Previously the network
 * withdrew and the mark formed, and no element of one had anything to do with
 * any element of the other, so there was nothing for the eye to follow across
 * the handover.
 *
 * Now two of the network's elements are the mark's elements. The upper-right
 * route and its node travel onto the mark's upper route and upper ring; the
 * lower-left route and its node onto the lower ones. They arrive at those exact
 * screen positions and crossfade there, so what reads is the same two routes
 * changing role rather than one set leaving and another arriving.
 *
 * The pairing is not arbitrary. `route-arrival` was authored to end aimed at the
 * centre along the diagonal the mark's upper route occupies, and `route-approach`
 * along the lower one. The composition was already built for this; nothing was
 * carrying it across.
 */
export const ROUTE_TRANSFER = {
  'route-arrival': 'upper',
  'route-approach': 'lower',
} as const;

/** Which node rides with which route, and therefore which ring it becomes. */
export const NODE_TRANSFER = {
  'node-a': 'upper',
  'node-b': 'lower',
} as const;

/**
 * A moving window along one path, in that path's own units.
 *
 * Everything visible during the approach is one of these. The head runs ahead,
 * the tail follows a fixed distance behind, and what is drawn is the interval
 * between them. Nothing translates: the curves stay exactly where they are
 * authored and only the window moves along them.
 *
 * That is the whole correction. Sliding a finished curve inward moves every
 * point of it at the same speed in the same direction, which is a stick being
 * pushed; a window moves along the curve, so the stroke follows the bend, grows
 * as the head outruns the tail and contracts as the tail catches up.
 *
 * `from` and `to` bound this path's slice of the whole journey, so a stream
 * crossing from its route into its connector is one continuous distance rather
 * than two animations meeting.
 */
export function window(
  distance: number,
  lag: number,
  from: number,
  to: number,
): { tail: number; visible: number } {
  'worklet';
  const head = distance < from ? from : distance > to ? to : distance;
  const behind = distance - lag;
  const tail = behind < from ? from : behind > to ? to : behind;

  return { tail: tail - from, visible: head - tail };
}

/**
 * The dash that draws that window as one solid segment.
 *
 * `[visible, length + 1]` is a single dash followed by a gap longer than the
 * path, so exactly one dash can ever be on it: no repeat, nothing that reads as
 * a dotted line. The offset places that dash at the tail.
 *
 * The offset is written as `visible + length + 1 - tail` rather than `-tail`.
 * Those are the same position, one period apart, and the positive form avoids
 * relying on how a negative dash phase is handled once it reaches the platform.
 *
 * `visible` is floored just above zero because a zero-length dash with round
 * caps draws a dot on some renderers, and a dot sitting at the start of a route
 * that has not begun flowing is exactly the sort of thing nobody notices until
 * it is on a device.
 */
export function dashWindow(visible: number, tail: number, length: number) {
  'worklet';
  const drawn = visible > 0.001 ? visible : 0.001;
  const gap = length + 1;

  return {
    strokeDasharray: [drawn, gap],
    strokeDashoffset: drawn + gap - tail,
  };
}

/** Sampled length of one cubic. Called from `useMemo`, never per frame. */
function cubicLength(p0: Vector, c1: Vector, c2: Vector, p3: Vector): number {
  let total = 0;
  let previous = p0;

  for (let i = 1; i <= 64; i += 1) {
    const t = i / 64;
    const u = 1 - t;
    const point = {
      x: u ** 3 * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t ** 3 * p3.x,
      y: u ** 3 * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t ** 3 * p3.y,
    };
    total += Math.hypot(point.x - previous.x, point.y - previous.y);
    previous = point;
  }
  return total;
}

/** A point on one cubic. Authoring-time and `useMemo` only. */
export function cubicPoint(p0: Vector, c1: Vector, c2: Vector, p3: Vector, t: number): Vector {
  const u = 1 - t;
  return {
    x: u ** 3 * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t ** 3 * p3.x,
    y: u ** 3 * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t ** 3 * p3.y,
  };
}

/** Where a mark coordinate falls inside the network's 320 unit square. */
export function markPointInNetwork(size: number, markSize: number) {
  const scale = (markSize / size) * (NETWORK_VIEWBOX / MARK_VIEWBOX);
  const origin = NETWORK_VIEWBOX / 2 - (MARK_VIEWBOX * scale) / 2;

  return (point: Vector): Vector => ({
    x: origin + point.x * scale,
    y: origin + point.y * scale,
  });
}

export interface Connector {
  d: string;
  length: number;
  from: Vector;
  to: Vector;
  control: [Vector, Vector];
}

/**
 * The two temporary curves bridging each fixed route to the mark.
 *
 * The routes no longer move, so their inward tips no longer reach the mark: the
 * network is scaled to the screen and the mark is a fixed point size, and the
 * gap between them depends on both. Rather than drag a whole curve across that
 * gap, each stream flows through a short connector that exists only while the
 * stream is inside it and is gone from the finished frame entirely.
 *
 * Both are authored tangent-continuous with the route feeding them. The upper
 * route arrives travelling left and its connector leaves travelling left; the
 * lower arrives travelling right and leaves travelling right. Neither turns a
 * corner at the handover.
 */
export function connectors(size: number, markSize: number): Record<string, Connector> {
  const toNetwork = markPointInNetwork(size, markSize);
  const upperTarget = toNetwork({ x: NODE_UPPER.cx, y: NODE_UPPER.cy });
  const lowerTarget = toNetwork({ x: NODE_LOWER.cx, y: NODE_LOWER.cy });

  const upperFrom = ROUTE_ENDPOINT['route-arrival'];
  const lowerFrom = ROUTE_ENDPOINT['route-approach'];

  // The first handle continues the route's own horizontal tangent; the second
  // approaches the ring horizontally from the same side.
  const upperControl: [Vector, Vector] = [
    { x: upperFrom.x - 16, y: upperFrom.y },
    { x: upperTarget.x + 16, y: upperTarget.y },
  ];
  const lowerControl: [Vector, Vector] = [
    { x: lowerFrom.x + 16, y: lowerFrom.y },
    { x: lowerTarget.x - 16, y: lowerTarget.y },
  ];

  const round = (n: number) => Math.round(n * 100) / 100;

  return {
    'route-arrival': {
      d:
        `M${upperFrom.x} ${upperFrom.y}C${upperControl[0].x} ${upperControl[0].y} ` +
        `${round(upperControl[1].x)} ${round(upperControl[1].y)} ` +
        `${round(upperTarget.x)} ${round(upperTarget.y)}`,
      length: cubicLength(upperFrom, upperControl[0], upperControl[1], upperTarget),
      from: upperFrom,
      to: upperTarget,
      control: upperControl,
    },
    'route-approach': {
      d:
        `M${lowerFrom.x} ${lowerFrom.y}C${lowerControl[0].x} ${lowerControl[0].y} ` +
        `${round(lowerControl[1].x)} ${round(lowerControl[1].y)} ` +
        `${round(lowerTarget.x)} ${round(lowerTarget.y)}`,
      length: cubicLength(lowerFrom, lowerControl[0], lowerControl[1], lowerTarget),
      from: lowerFrom,
      to: lowerTarget,
      control: lowerControl,
    },
  };
}

export interface FlowPlan {
  /** Network route, connector and mark leg lengths, all in points. */
  route: number;
  connector: number;
  mark: number;
  total: number;
  /** How far the tail runs behind the head, in points. */
  lag: number;
}

/**
 * One journey per stream, measured in points end to end.
 *
 * Points rather than either viewBox, because the three legs live in two
 * different coordinate systems and the only thing that makes a constant velocity
 * across them mean anything is physical distance on the screen.
 */
export function flowPlan(size: number, markSize: number): Record<'upper' | 'lower', FlowPlan> {
  const networkUnit = size / NETWORK_VIEWBOX;
  const markUnit = markSize / MARK_VIEWBOX;
  const bridge = connectors(size, markSize);

  const plan = (routeId: string, markLength: number): FlowPlan => {
    const route = ROUTE_LENGTH[routeId] * networkUnit;
    const connector = bridge[routeId].length * networkUnit;
    const mark = markLength * markUnit;

    return {
      route,
      connector,
      mark,
      total: route + connector + mark,
      // Long enough to read as a ribbon rather than a dot, short enough that the
      // route is never drawn end to end at once, which would be the old rigid
      // line back again.
      lag: route * 0.42,
    };
  };

  return {
    upper: plan('route-arrival', MARK_UPPER_LENGTH),
    lower: plan('route-approach', MARK_LOWER_LENGTH),
  };
}

/** The mark path each half of the transfer resolves into. *//** The mark path each half of the transfer resolves into. */
export const MARK_ROUTE_PATH = {
  upper: ROUTE_UPPER_PATH,
  lower: ROUTE_LOWER_PATH,
} as const;

/**
 * How the finished lockup is stacked.
 *
 * The mark does not move for the wordmark. It is centred in the scene and it
 * stays there, because the whole sequence has just spent two seconds putting it
 * exactly where it is; sliding it up to make room would undo that in the last
 * fraction of a second. The wordmark is placed under it instead, offset from the
 * same centre.
 *
 * Held here rather than in either component so the animated surface and the
 * still one cannot drift apart by a point.
 */
export const WORDMARK_HEIGHT = 21;
export const WORDMARK_GAP = 18;

/** How far below the scene's centre the wordmark's own centre sits. */
export function wordmarkOffset(markSize: number): number {
  return markSize / 2 + WORDMARK_GAP + WORDMARK_HEIGHT / 2;
}

/** How far it lifts as it arrives. Small enough to read as settling. */
export const WORDMARK_RISE = 4;
