/**
 * The static launch scene.
 *
 * Structural only. There is nothing moving yet, so these tests guard the two
 * things that would quietly break the animation work that follows: the element
 * budget, and the promise that every coordinate is a literal rather than
 * something computed at render time.
 */

import { LaunchNetwork } from '@/features/startup/LaunchNetwork';
import {
  CENTRE,
  NETWORK_ELEMENT_IDS,
  NETWORK_INDICATOR,
  NETWORK_NODES,
  NETWORK_ROUTES,
  NETWORK_VIEWBOX,
} from '@/features/startup/network-geometry';
import { renderWithProviders } from '@/test-utils/render';

/**
 * The whole scene is marked hidden from assistive technology on purpose, which
 * also hides it from the default queries. Every lookup here opts in, so these
 * tests read the tree a sighted user sees rather than the one a screen reader
 * is given.
 */
const HIDDEN = { includeHiddenElements: true } as const;

/**
 * Walks a path made of an `M` followed by cubic segments.
 *
 * Written here rather than pulled in, because the point of these tests is to
 * check the shipped constants against geometry rather than to trust a library
 * to agree with the renderer about what the string means.
 */
function samplePath(d: string, perSegment = 120): { x: number; y: number }[] {
  const numbers = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
  const start = { x: numbers[0], y: numbers[1] };
  const points = [start];

  let from = start;
  for (let i = 2; i + 5 < numbers.length; i += 6) {
    const [c1x, c1y, c2x, c2y, x, y] = numbers.slice(i, i + 6);
    for (let step = 1; step <= perSegment; step += 1) {
      const t = step / perSegment;
      const u = 1 - t;
      points.push({
        x: u ** 3 * from.x + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t ** 3 * x,
        y: u ** 3 * from.y + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t ** 3 * y,
      });
    }
    from = { x, y };
  }

  return points;
}


/** Maximum deviation of a path from the straight line between its own ends. */
function chordDeviation(d: string): number {
  const points = samplePath(d, 300);
  const [first] = points;
  const last = points[points.length - 1];
  const length = Math.hypot(last.x - first.x, last.y - first.y);

  return Math.max(
    ...points.map((p) => {
      const t =
        ((p.x - first.x) * (last.x - first.x) + (p.y - first.y) * (last.y - first.y)) /
        (length * length);
      return Math.hypot(
        p.x - (first.x + t * (last.x - first.x)),
        p.y - (first.y + t * (last.y - first.y)),
      );
    }),
  );
}

/**
 * How many times the path changes which way it is turning.
 *
 * Small wiggles on near-straight runs are ignored, so this counts reversals the
 * eye would actually see rather than floating-point noise.
 */
function curvatureReversals(d: string): number {
  const points = samplePath(d, 200);
  const values: number[] = [];

  for (let i = 4; i < points.length - 4; i += 1) {
    const a = points[i - 4];
    const b = points[i];
    const c = points[i + 4];
    const cross = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    const scale = Math.hypot(b.x - a.x, b.y - a.y) * Math.hypot(c.x - b.x, c.y - b.y);
    values.push(scale > 0 ? cross / scale : 0);
  }

  const peak = Math.max(...values.map(Math.abs));
  let reversals = 0;
  let previous = 0;

  for (const value of values.filter((v) => Math.abs(v) > peak * 0.15)) {
    const sign = Math.sign(value);
    if (previous !== 0 && sign !== previous) reversals += 1;
    previous = sign;
  }

  return reversals;
}

/**
 * How far a path strays onto the wrong side of its own tangent at an interior
 * join, in user units.
 *
 * Zero means the curve sweeps one way throughout. A small non-zero value means
 * there is technically an inflection at the join, and the number says whether it
 * is one the eye could pick out or one that disappears inside the stroke.
 */
function counterBulge(d: string): number {
  const numbers = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
  // The join is the end of the first cubic; the tangent leaving it is the second
  // cubic's opening handle.
  const join = { x: numbers[6], y: numbers[7] };
  const handle = { x: numbers[8], y: numbers[9] };
  const length = Math.hypot(handle.x - join.x, handle.y - join.y);
  const normal = { x: -(handle.y - join.y) / length, y: (handle.x - join.x) / length };

  // Only the neighbourhood of the join. Far from it the curve is legitimately a
  // long way off this tangent line, which says nothing about an inflection here.
  const perSegment = 400;
  const points = samplePath(d, perSegment);
  const window = perSegment * 0.25;

  let positive = 0;
  let negative = 0;
  for (let i = perSegment - window; i <= perSegment + window; i += 1) {
    const point = points[i];
    const along = (point.x - join.x) * normal.x + (point.y - join.y) * normal.y;
    positive = Math.max(positive, along);
    negative = Math.min(negative, along);
  }

  return Math.min(Math.abs(positive), Math.abs(negative));
}

/** The angle each cubic segment turns through, entry tangent to exit tangent. */
function segmentTurns(d: string): number[] {
  const numbers = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
  const turns: number[] = [];
  let from = { x: numbers[0], y: numbers[1] };

  for (let i = 2; i + 5 < numbers.length; i += 6) {
    const [c1x, c1y, c2x, c2y, x, y] = numbers.slice(i, i + 6);
    const entry = [c1x - from.x, c1y - from.y];
    const exit = [x - c2x, y - c2y];
    const dot =
      (entry[0] * exit[0] + entry[1] * exit[1]) /
      (Math.hypot(entry[0], entry[1]) * Math.hypot(exit[0], exit[1]));
    turns.push((Math.acos(Math.max(-1, Math.min(1, dot))) * 180) / Math.PI);
    from = { x, y };
  }

  return turns;
}

describe('the element budget', () => {
  it('draws exactly four service nodes', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const node of NETWORK_NODES) {
      expect(view.getByTestId(node.id, HIDDEN)).toBeTruthy();
    }
    expect(NETWORK_NODES).toHaveLength(4);
  });

  it('draws exactly three routes', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const route of NETWORK_ROUTES) {
      expect(view.getByTestId(route.id, HIDDEN)).toBeTruthy();
    }
    expect(NETWORK_ROUTES).toHaveLength(3);
  });

  it('draws exactly one route indicator', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    expect(view.getByTestId(NETWORK_INDICATOR.id, HIDDEN)).toBeTruthy();
  });

  it('stays inside the nine element budget', async () => {
    // Past roughly a dozen shapes the scene stops reading as a network and
    // starts reading as noise, and later starts costing frames.
    expect(NETWORK_ELEMENT_IDS).toHaveLength(8);
  });
});

describe('addressability', () => {
  it('gives every element a stable identifier', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const id of NETWORK_ELEMENT_IDS) {
      expect(view.getByTestId(id, HIDDEN)).toBeTruthy();
    }
  });

  it('uses no duplicate identifiers', () => {
    expect(new Set(NETWORK_ELEMENT_IDS).size).toBe(NETWORK_ELEMENT_IDS.length);
  });

  it('carries the identifier into the svg node itself', async () => {
    // The animation work will address these directly, not only through tests.
    // react-native-svg surfaces the `id` prop as `name` on the host node.
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const id of NETWORK_ELEMENT_IDS) {
      expect(view.getByTestId(id, HIDDEN).props.name).toBe(id);
    }
  });
});

describe('static geometry', () => {
  it('renders identical path data at any size', async () => {
    // The proof that nothing is computed from the size. If a path were derived
    // at render time these would differ.
    const small = await renderWithProviders(<LaunchNetwork size={180} />);
    const large = await renderWithProviders(<LaunchNetwork size={420} />);

    for (const route of NETWORK_ROUTES) {
      expect(large.getByTestId(route.id, HIDDEN).props.d).toBe(
        small.getByTestId(route.id, HIDDEN).props.d,
      );
    }
  });

  it('renders identical node positions at any size', async () => {
    const small = await renderWithProviders(<LaunchNetwork size={180} />);
    const large = await renderWithProviders(<LaunchNetwork size={420} />);

    for (const node of NETWORK_NODES) {
      const a = small.getByTestId(node.id, HIDDEN).props;
      const b = large.getByTestId(node.id, HIDDEN).props;
      expect([b.cx, b.cy, b.r]).toEqual([a.cx, a.cy, a.r]);
    }
  });

  it('scales through the viewBox rather than the coordinates', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={240} />);
    const svg = view.getByTestId('launch-network', HIDDEN);

    // Rendered size changes; the coordinate space it is drawn in does not.
    expect(svg.props.bbWidth).toBe(240);
    expect(svg.props.vbWidth).toBe(NETWORK_VIEWBOX);
    expect(svg.props.vbHeight).toBe(NETWORK_VIEWBOX);
  });

  it('keeps every node clear of the reserved centre', () => {
    // The mark is drawn on top of this. A node inside the reserved circle would
    // sit underneath it and read as a smudge.
    for (const node of NETWORK_NODES) {
      const distance = Math.hypot(node.cx - CENTRE.x, node.cy - CENTRE.y);
      expect(distance).toBeGreaterThanOrEqual(CENTRE.clearRadius);
    }
  });

  it('keeps every route clear of the reserved centre', () => {
    // Sampled rather than reasoned about: a control point outside the circle
    // says nothing about where the curve between them actually goes.
    for (const route of NETWORK_ROUTES) {
      for (const point of samplePath(route.d)) {
        const distance = Math.hypot(point.x - CENTRE.x, point.y - CENTRE.y);
        expect(distance).toBeGreaterThanOrEqual(CENTRE.clearRadius);
      }
    }
  });

  it('puts a node in each of the four quadrants', () => {
    const quadrant = (n: (typeof NETWORK_NODES)[number]) =>
      `${n.cx < CENTRE.x ? 'W' : 'E'}${n.cy < CENTRE.y ? 'N' : 'S'}`;

    expect(new Set(NETWORK_NODES.map(quadrant)).size).toBe(4);
  });

  it('does not arrange the nodes on a circle', () => {
    // Equal radii would read as an orbit or a compass rose.
    const radii = NETWORK_NODES.map((n) =>
      Math.round(Math.hypot(n.cx - CENTRE.x, n.cy - CENTRE.y)),
    );

    expect(new Set(radii).size).toBeGreaterThan(1);
  });

  it('gives the contextual route a curvature reversal', () => {
    // The measurable difference between a route and an orbit. A circle or an
    // ellipse turns the same way along its whole length; this one does not, so
    // no part of it can be continued into a ring.
    const context = NETWORK_ROUTES.find((r) => r.emphasis === 'quiet')!;

    expect(curvatureReversals(context.d)).toBeGreaterThanOrEqual(1);
  });

  it('varies the contextual route distance from the centre', () => {
    // A constant radius is what an orbit is. Measured across the whole path.
    const context = NETWORK_ROUTES.find((r) => r.emphasis === 'quiet')!;
    const radii = samplePath(context.d, 300).map((p) =>
      Math.hypot(p.x - CENTRE.x, p.y - CENTRE.y),
    );

    expect(Math.max(...radii) - Math.min(...radii)).toBeGreaterThan(60);
  });

  it('bends the contextual route in more than one direction', () => {
    const context = NETWORK_ROUTES.find((r) => r.emphasis === 'quiet')!;

    expect(segmentTurns(context.d).filter((deg) => deg > 25).length).toBeGreaterThanOrEqual(2);
  });

  it('curves both primary routes rather than leaving them straight', () => {
    // They read as diagonal slashes below roughly 15 units of deviation from
    // their own chord.
    for (const route of NETWORK_ROUTES.filter((r) => r.emphasis === 'primary')) {
      expect(chordDeviation(route.d)).toBeGreaterThan(15);
    }
  });

  it('keeps both primary routes free of visible waviness', () => {
    // A curve that reverses repeatedly reads as a wobble at this stroke width,
    // not as a road.
    //
    // Measured as the bulge rather than as a count of sign changes. The two
    // cubics either side of each node are tangent-continuous but not curvature-
    // continuous, so the sign can flip at the join by an amount far below
    // anything the eye resolves, and counting flips called that waviness. What
    // actually matters is how far the curve strays onto the other side of its
    // own tangent at that join, in units, against a 2.5 unit stroke.
    for (const route of NETWORK_ROUTES.filter((r) => r.emphasis === 'primary')) {
      // Currently 0 on `route-arrival`, which never crosses, and 0.75 on
      // `route-approach`, which is well inside its own stroke.
      expect(counterBulge(route.d)).toBeLessThan(route.width / 2);
    }
  });

  it('does not make the two primary routes mirror images', () => {
    const [a, b] = NETWORK_ROUTES.filter((r) => r.emphasis === 'primary');

    expect(Math.abs(chordDeviation(a.d) - chordDeviation(b.d))).toBeGreaterThan(0.5);
  });

  it('enters the frame on a diagonal wherever a route leaves it', () => {
    // A route crossing the frame edge near-vertically reads as a dangling wire.
    // Measured as the angle of the opening tangent, which is what the eye reads.
    //
    // Sampled finely on purpose. A coarse secant is a chord, not a tangent, and
    // on a curve that bends away from its opening direction it reads low: at 40
    // steps this measured `route-approach` at 14.9 degrees against a true
    // opening tangent of 15.07, which is the test's own approximation failing
    // rather than the geometry.
    for (const route of NETWORK_ROUTES) {
      const [start, next] = samplePath(route.d, 2000);
      const leavesFrame =
        start.x < 0 || start.y < 0 || start.x > NETWORK_VIEWBOX || start.y > NETWORK_VIEWBOX;
      if (!leavesFrame) continue;

      const degrees = Math.abs(
        (Math.atan2(Math.abs(next.y - start.y), Math.abs(next.x - start.x)) * 180) / Math.PI,
      );
      expect(degrees).toBeGreaterThan(15);
      expect(degrees).toBeLessThan(75);
    }
  });

  it('finishes both primary routes travelling horizontally', () => {
    // These used to end aimed at the centre, on the reasoning that the eye
    // should be carried inward. That was superseded: each route now becomes the
    // corresponding Sync route, and the Sync routes run horizontally at the ends
    // the network hands over to. Aiming diagonally at the centre and then
    // continuing horizontally would put a direction change at exactly the moment
    // of the transfer.
    //
    // The continuity of the joins themselves is held in `route-continuity`.
    for (const route of NETWORK_ROUTES.filter((r) => r.emphasis === 'primary')) {
      const points = samplePath(route.d, 2000);
      const end = points[points.length - 1];
      const before = points[points.length - 2];
      const heading = Math.abs(
        (Math.atan2(Math.abs(end.y - before.y), Math.abs(end.x - before.x)) * 180) /
          Math.PI,
      );

      expect(heading).toBeLessThan(2);
    }
  });

  it('still finishes both primary routes near the reserved centre', () => {
    // Horizontal, but not wandering off. Each one has to end close enough to the
    // mark that the convergence is a short continuation rather than a leap.
    for (const route of NETWORK_ROUTES.filter((r) => r.emphasis === 'primary')) {
      const points = samplePath(route.d, 400);
      const end = points[points.length - 1];
      const distance = Math.hypot(end.x - CENTRE.x, end.y - CENTRE.y);

      expect(distance).toBeGreaterThan(CENTRE.clearRadius);
      expect(distance).toBeLessThan(CENTRE.clearRadius + 15);
    }
  });

  it('leaves the indicator sitting on a route rather than floating', () => {
    const nearest = Math.min(
      ...NETWORK_ROUTES.flatMap((route) =>
        samplePath(route.d, 600).map((p) =>
          Math.hypot(p.x - NETWORK_INDICATOR.cx, p.y - NETWORK_INDICATOR.cy),
        ),
      ),
    );

    expect(nearest).toBeLessThan(2);
  });

  it('keeps every node well inside the frame', () => {
    // Nodes clipped by an edge look like a rendering fault rather than a design.
    for (const node of NETWORK_NODES) {
      expect(Math.min(node.cx, node.cy)).toBeGreaterThan(node.r + 20);
      expect(Math.max(node.cx, node.cy)).toBeLessThan(NETWORK_VIEWBOX - node.r - 20);
    }
  });
});

describe('presentation', () => {
  it('is hidden from assistive technology', async () => {
    // Abstract scenery. The mark next to it already carries the accessible name.
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    expect(view.getByTestId('launch-network', HIDDEN).props.accessibilityElementsHidden).toBe(true);
  });

  it('takes no touches', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    expect(view.getByTestId('launch-network', HIDDEN).props.pointerEvents).toBe('none');
  });

  it('renders in dark mode', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />, { mode: 'dark' });

    expect(view.getByTestId('launch-network', HIDDEN)).toBeTruthy();
    expect(view.getByTestId(NETWORK_INDICATOR.id, HIDDEN)).toBeTruthy();
  });

  it('draws every route thin enough to read as a route', async () => {
    // The composition was rebuilt away from thick outlined paths. These bounds
    // are what stops a later tweak sliding back toward a diagram.
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const route of NETWORK_ROUTES) {
      const width = view.getByTestId(route.id, HIDDEN).props.strokeWidth;
      expect(width).toBeLessThanOrEqual(route.emphasis === 'primary' ? 2.6 : 1.6);
      // And still visible on a device rather than a hairline that vanishes.
      expect(width).toBeGreaterThanOrEqual(route.emphasis === 'primary' ? 2 : 1.2);
    }
  });

  it('draws nodes as filled dots rather than outlined rings', async () => {
    // A ringed endpoint is how the Sync mark terminates its own routes. Four
    // more of them around the network dilutes the one place it means something.
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    for (const node of NETWORK_NODES) {
      const props = view.getByTestId(node.id, HIDDEN).props;
      expect(props.fill).toBeTruthy();
      expect(props.stroke).toBeUndefined();
    }
  });

  it('keeps every dot small', async () => {
    // Scenery. Dots large enough to count as objects in their own right pull
    // attention away from the centre, which is the only thing that matters here.
    for (const node of NETWORK_NODES) {
      expect(node.r).toBeLessThanOrEqual(4.5);
    }
  });

  it('keeps the indicator smaller than the nodes it travels between', async () => {
    // It is told apart by moving, not by being bigger. A large dot on a thin
    // route reads as a bead threaded on a wire.
    const smallest = Math.min(...NETWORK_NODES.map((n) => n.r));

    expect(NETWORK_INDICATOR.r).toBeLessThan(smallest);
  });

  it('gives the emphasised route a heavier stroke than the quiet ones', async () => {
    const view = await renderWithProviders(<LaunchNetwork size={320} />);

    const primary = NETWORK_ROUTES.find((r) => r.emphasis === 'primary')!;
    const quiet = NETWORK_ROUTES.filter((r) => r.emphasis === 'quiet');

    for (const route of quiet) {
      expect(view.getByTestId(primary.id, HIDDEN).props.strokeWidth).toBeGreaterThan(
        view.getByTestId(route.id, HIDDEN).props.strokeWidth,
      );
    }
  });
});
