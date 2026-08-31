/**
 * Tangent continuity on the two primary routes.
 *
 * Each primary route is two cubic segments meeting at its own primary node. If
 * the handles either side of that join are not collinear, the join is a corner,
 * and a corner sitting exactly under a node reads on a device as a fault in the
 * drawing rather than as a bend in a road. The first version broke by 55 degrees
 * on one route and 30 on the other, which is what a recorded review picked up as
 * visible elbows.
 *
 * Nothing in the app parses a path. All of this is authoring-time analysis kept
 * where it belongs: in a test, run against the shipped constants.
 */

import {
  INDICATOR_JOURNEY,
  NETWORK_NODES,
  NETWORK_ROUTES,
  ROUTE_ENDPOINT,
} from '@/features/startup/network-geometry';

interface Point {
  x: number;
  y: number;
}
type Cubic = [Point, Point, Point, Point];

/** Splits `M x y C ...` into its cubic segments. */
function segmentsOf(d: string): Cubic[] {
  const n = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
  const segments: Cubic[] = [];
  let from: Point = { x: n[0], y: n[1] };

  for (let i = 2; i + 5 < n.length; i += 6) {
    const [c1x, c1y, c2x, c2y, x, y] = n.slice(i, i + 6);
    segments.push([from, { x: c1x, y: c1y }, { x: c2x, y: c2y }, { x, y }]);
    from = { x, y };
  }
  return segments;
}

function at(segment: Cubic, t: number): Point {
  const [p0, p1, p2, p3] = segment;
  const u = 1 - t;
  return {
    x: u ** 3 * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t ** 3 * p3.x,
    y: u ** 3 * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t ** 3 * p3.y,
  };
}

/** Unit tangent leaving a control point pair. */
function unit(from: Point, to: Point): Point {
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  return { x: (to.x - from.x) / length, y: (to.y - from.y) / length };
}

const PRIMARY = NETWORK_ROUTES.filter((route) => route.emphasis === 'primary');

describe('the shipped primary paths', () => {
  it('are exactly the corrected definitions', () => {
    // Pinned. These handles are the whole fix, and a well-meant nudge to any of
    // the six numbers puts the elbow back.
    const [arrival, approach] = PRIMARY;

    expect(arrival.d).toBe('M352 24C318 37 282 45 250 62C232 72 228 108 212 108');
    expect(approach.d).toBe('M-24 292C28 278 48 278 64 252C73 237 92 212 108 212');
  });

  it('is built from two cubics apiece', () => {
    for (const route of PRIMARY) {
      expect(segmentsOf(route.d)).toHaveLength(2);
    }
  });

  it('meets at its own primary node', () => {
    // The join is the node. If it drifted, the corner and the dot would be in
    // different places, which is worse than either alone.
    const joins: Record<string, string> = {
      'route-arrival': 'node-a',
      'route-approach': 'node-b',
    };

    for (const route of PRIMARY) {
      const node = NETWORK_NODES.find((n) => n.id === joins[route.id])!;
      const join = segmentsOf(route.d)[0][3];

      expect(join).toEqual({ x: node.cx, y: node.cy });
    }
  });

  it('keeps the inward endpoints the convergence aims at', () => {
    for (const route of PRIMARY) {
      const segments = segmentsOf(route.d);
      const end = segments[segments.length - 1][3];

      expect(end).toEqual(ROUTE_ENDPOINT[route.id]);
    }
  });

  it('keeps the start points outside the frame', () => {
    // Both routes are meant to come in from beyond the edge rather than to begin
    // somewhere on screen.
    const [arrival, approach] = PRIMARY;

    expect(segmentsOf(arrival.d)[0][0]).toEqual({ x: 352, y: 24 });
    expect(segmentsOf(approach.d)[0][0]).toEqual({ x: -24, y: 292 });
  });
});

describe('tangent continuity at every join', () => {
  it('turns the handles through less than two degrees', () => {
    for (const route of PRIMARY) {
      const segments = segmentsOf(route.d);

      for (let i = 1; i < segments.length; i += 1) {
        const incoming = unit(segments[i - 1][2], segments[i - 1][3]);
        const outgoing = unit(segments[i][0], segments[i][1]);
        const cross = incoming.x * outgoing.y - incoming.y * outgoing.x;

        // Collinear within tolerance. Measured at 0.0188 and 0.0112, which is
        // 1.1 and 0.6 degrees.
        expect(Math.abs(cross)).toBeLessThan(0.04);
      }
    }
  });

  it('continues forward rather than doubling back', () => {
    for (const route of PRIMARY) {
      const segments = segmentsOf(route.d);

      for (let i = 1; i < segments.length; i += 1) {
        const incoming = unit(segments[i - 1][2], segments[i - 1][3]);
        const outgoing = unit(segments[i][0], segments[i][1]);
        const dot = incoming.x * outgoing.x + incoming.y * outgoing.y;

        // A negative dot with a near-zero cross is a cusp: collinear, but
        // reversed. That is a spike, not a smooth join.
        expect(dot).toBeGreaterThan(0.99);
      }
    }
  });

  it('bends gently on both sides of the join', () => {
    // A join can be perfectly tangent-continuous and still look wrong if the
    // curve is nearly straight on one side and turning hard on the other.
    for (const route of PRIMARY) {
      const segments = segmentsOf(route.d);

      for (let i = 1; i < segments.length; i += 1) {
        const before = unit(at(segments[i - 1], 0.8), at(segments[i - 1], 1));
        const after = unit(at(segments[i], 0), at(segments[i], 0.2));
        const turn = Math.acos(
          Math.max(-1, Math.min(1, before.x * after.x + before.y * after.y)),
        );

        expect((turn * 180) / Math.PI).toBeLessThan(20);
      }
    }
  });
});

describe('the inward tangents the mark has to continue', () => {
  it('finishes the upper route travelling horizontally leftward', () => {
    const [arrival] = PRIMARY;
    const segments = segmentsOf(arrival.d);
    const last = segments[segments.length - 1];
    const tangent = unit(last[2], last[3]);

    expect(tangent.x).toBeCloseTo(-1);
    expect(tangent.y).toBeCloseTo(0);
  });

  it('finishes the lower route travelling horizontally rightward', () => {
    const [, approach] = PRIMARY;
    const segments = segmentsOf(approach.d);
    const last = segments[segments.length - 1];
    const tangent = unit(last[2], last[3]);

    expect(tangent.x).toBeCloseTo(1);
    expect(tangent.y).toBeCloseTo(0);
  });
});

describe('the indicator waypoints', () => {
  const upper = segmentsOf(PRIMARY[0].d);
  const inward = upper[upper.length - 1];
  const curve = Array.from({ length: 4001 }, (_, i) => at(inward, i / 4000));

  it('carries enough points to hide the polyline', () => {
    expect(INDICATOR_JOURNEY.length).toBeGreaterThanOrEqual(12);
    expect(INDICATOR_JOURNEY.length).toBeLessThanOrEqual(16);
  });

  it('stays on the corrected route', () => {
    // Every waypoint has to sit on the curve the indicator is supposed to be
    // travelling, or it visibly leaves the road.
    for (const point of INDICATOR_JOURNEY) {
      const nearest = Math.min(
        ...curve.map((p) => Math.hypot(p.x - point.x, p.y - point.y)),
      );

      expect(nearest).toBeLessThan(0.2);
    }
  });

  it('never cuts a perceptible corner between waypoints', () => {
    // What actually matters is the gap between the straight hop and the real
    // curve, not the number of points. Measured at 0.28 units at its worst.
    let worst = 0;
    for (let i = 0; i < INDICATOR_JOURNEY.length - 1; i += 1) {
      const from = INDICATOR_JOURNEY[i];
      const to = INDICATOR_JOURNEY[i + 1];
      for (let k = 1; k < 20; k += 1) {
        const s = k / 20;
        const mid = { x: from.x + (to.x - from.x) * s, y: from.y + (to.y - from.y) * s };
        worst = Math.max(
          worst,
          Math.min(...curve.map((p) => Math.hypot(p.x - mid.x, p.y - mid.y))),
        );
      }
    }

    expect(worst).toBeLessThan(0.5);
  });

  it('spaces the steps evenly', () => {
    // Uneven spacing is the indicator speeding up and slowing down for no
    // reason, which is exactly what pre-authored waypoints are meant to avoid.
    const steps = INDICATOR_JOURNEY.slice(1).map((point, i) =>
      Math.hypot(point.x - INDICATOR_JOURNEY[i].x, point.y - INDICATOR_JOURNEY[i].y),
    );
    const mean = steps.reduce((a, b) => a + b, 0) / steps.length;

    // Measured spread is 2.4 percent at its worst.
    for (const step of steps) {
      expect(Math.abs(step - mean) / mean).toBeLessThan(0.1);
    }
  });

  it('turns only slightly between consecutive steps', () => {
    for (let i = 0; i < INDICATOR_JOURNEY.length - 2; i += 1) {
      const a = unit(INDICATOR_JOURNEY[i], INDICATOR_JOURNEY[i + 1]);
      const b = unit(INDICATOR_JOURNEY[i + 1], INDICATOR_JOURNEY[i + 2]);
      const turn = Math.acos(Math.max(-1, Math.min(1, a.x * b.x + a.y * b.y)));

      expect((turn * 180) / Math.PI).toBeLessThan(25);
    }
  });

  it('begins on the node and ends on the route endpoint', () => {
    const nodeA = NETWORK_NODES.find((n) => n.id === 'node-a')!;

    expect(INDICATOR_JOURNEY[0]).toEqual({ x: nodeA.cx, y: nodeA.cy });
    expect(INDICATOR_JOURNEY[INDICATOR_JOURNEY.length - 1]).toEqual(
      ROUTE_ENDPOINT['route-arrival'],
    );
  });
});
