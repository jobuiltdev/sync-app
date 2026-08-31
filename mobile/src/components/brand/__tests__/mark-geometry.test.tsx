/**
 * The static mark and the animated one must not drift apart.
 *
 * The animation's whole contract is that its last frame *is* the static mark.
 * That holds because both read the same constants, and these tests fail the
 * moment somebody edits a path in one place only.
 *
 * The lower route is the one exception and it is deliberate: the formation
 * draws it backwards, because a dash reveal grows from a path's own start and
 * the reveal has to start where the incoming network route makes contact. The
 * two strings therefore differ, and what is asserted instead is that they
 * describe the same curve.
 */

import { SyncMark } from '@/components/brand/SyncMark';
import {
  MARK_LOWER_LENGTH,
  MARK_UPPER_LENGTH,
  NODE_LOWER,
  NODE_STROKE_WIDTH,
  NODE_UPPER,
  ROUTE_LOWER_PATH,
  ROUTE_LOWER_REVEAL_PATH,
  ROUTE_STROKE_WIDTH,
  ROUTE_UPPER_PATH,
} from '@/components/brand/mark-geometry';
import { AnimatedSyncMark } from '@/features/startup/AnimatedSyncMark';
import { renderWithProviders } from '@/test-utils/render';

interface Point {
  x: number;
  y: number;
}

/** Walks a path of `M`, `H` and cubic commands. Test-only, as always. */
function samplePath(d: string, per = 400): Point[] {
  const tokens = d.match(/[MCH]|-?\d+(?:\.\d+)?/g)!;
  const points: Point[] = [];
  let cursor: Point = { x: 0, y: 0 };
  let i = 0;

  while (i < tokens.length) {
    const command = tokens[i];
    if (command === 'M') {
      cursor = { x: Number(tokens[i + 1]), y: Number(tokens[i + 2]) };
      points.push(cursor);
      i += 3;
    } else if (command === 'H') {
      i += 1;
      while (i < tokens.length && !Number.isNaN(Number(tokens[i]))) {
        const to = { x: Number(tokens[i]), y: cursor.y };
        for (let k = 1; k <= per; k += 1) {
          points.push({ x: cursor.x + (to.x - cursor.x) * (k / per), y: cursor.y });
        }
        cursor = to;
        i += 1;
      }
    } else if (command === 'C') {
      i += 1;
      while (i + 5 < tokens.length && !Number.isNaN(Number(tokens[i]))) {
        const n = tokens.slice(i, i + 6).map(Number);
        const [p0, c1, c2, p3] = [
          cursor,
          { x: n[0], y: n[1] },
          { x: n[2], y: n[3] },
          { x: n[4], y: n[5] },
        ];
        for (let k = 1; k <= per; k += 1) {
          const t = k / per;
          const u = 1 - t;
          points.push({
            x: u ** 3 * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t ** 3 * p3.x,
            y: u ** 3 * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t ** 3 * p3.y,
          });
        }
        cursor = p3;
        i += 6;
      }
    } else {
      i += 1;
    }
  }
  return points;
}

describe('shared geometry', () => {
  it('draws the upper route from the same constant in both marks', async () => {
    const still = await renderWithProviders(<SyncMark />);
    const moving = await renderWithProviders(<AnimatedSyncMark />);

    expect(moving.getByTestId('sync-route-upper').props.d).toBe(
      still.getByTestId('sync-route-upper').props.d,
    );
  });

  it('places the rings at the same centres in both marks', async () => {
    // Radius and stroke width are animated on the moving mark, so they are not
    // static props there. The centres are, and they must not move.
    const still = await renderWithProviders(<SyncMark />);
    const moving = await renderWithProviders(<AnimatedSyncMark />);

    for (const id of ['sync-node-upper', 'sync-node-lower']) {
      const a = still.getByTestId(id).props;
      const b = moving.getByTestId(id).props;
      expect([b.cx, b.cy]).toEqual([a.cx, a.cy]);
    }
  });

  it('takes both marks from the same constants', () => {
    expect(ROUTE_UPPER_PATH).toMatch(/^M47 12H31/);
    expect(ROUTE_LOWER_PATH).toMatch(/^M28 27C40 27/);
    expect(ROUTE_STROKE_WIDTH).toBe(7);
    expect(NODE_UPPER.r).toBe(4);
    expect(NODE_LOWER.r).toBe(4);
    expect(NODE_STROKE_WIDTH).toBe(4);
  });
});

describe('the reversed lower route', () => {
  it('starts where the incoming network route makes contact', () => {
    // (17, 55) is the outer end of the lower route and the point `route-approach`
    // aligns onto. The reveal has to begin there or the S grows from its middle.
    expect(ROUTE_LOWER_REVEAL_PATH).toMatch(/^M17 55/);
  });

  it('ends where the canonical path begins', () => {
    const canonical = samplePath(ROUTE_LOWER_PATH);
    const reversed = samplePath(ROUTE_LOWER_REVEAL_PATH);

    expect(reversed[reversed.length - 1].x).toBeCloseTo(canonical[0].x);
    expect(reversed[reversed.length - 1].y).toBeCloseTo(canonical[0].y);
    expect(reversed[0].x).toBeCloseTo(canonical[canonical.length - 1].x);
    expect(reversed[0].y).toBeCloseTo(canonical[canonical.length - 1].y);
  });

  it('traces exactly the same curve', () => {
    // The one place two strings have to describe one shape. Nothing else would
    // catch them drifting, and if they drifted the mark would finish wrong.
    const canonical = samplePath(ROUTE_LOWER_PATH);
    const reversed = samplePath(ROUTE_LOWER_REVEAL_PATH);

    const worst = Math.max(
      ...canonical
        .filter((_, i) => i % 7 === 0)
        .map((p) =>
          Math.min(...reversed.map((q) => Math.hypot(p.x - q.x, p.y - q.y))),
        ),
    );

    expect(worst).toBeLessThan(0.01);
  });

  it('is the reverse rather than a different route with the same ends', () => {
    // Walk both and check they visit the same places in opposite order.
    const canonical = samplePath(ROUTE_LOWER_PATH, 100);
    const reversed = samplePath(ROUTE_LOWER_REVEAL_PATH, 100);

    for (const fraction of [0.25, 0.5, 0.75]) {
      const a = canonical[Math.floor((canonical.length - 1) * fraction)];
      const b = reversed[Math.floor((reversed.length - 1) * (1 - fraction))];

      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThan(1);
    }
  });
});

describe('the mark is revealed by trimming, not by fading', () => {
  it('drives both routes from an animated dash rather than a static one', async () => {
    // The reveal length is now the distance the stream has travelled into this
    // leg, so the dash has to change every frame. A fixed dasharray here would
    // mean the mark had gone back to timing its own reveal.
    const moving = await renderWithProviders(<AnimatedSyncMark />);
    const lengths: Record<string, number> = {
      'sync-route-upper': MARK_UPPER_LENGTH,
      'sync-route-lower': MARK_LOWER_LENGTH,
    };

    for (const [id, length] of Object.entries(lengths)) {
      const [dash, gap] = moving.getByTestId(id).props.strokeDasharray;

      // Nothing drawn until the stream arrives, and a gap longer than the path
      // so a second dash can never appear on it.
      expect(dash).toBeLessThan(0.01);
      expect(gap).toBeGreaterThan(length);
    }
  });

  it('measures both lengths accurately', () => {
    // A wrong length leaves a sliver permanently undrawn or finishes the reveal
    // early, and neither is visible in review until it is on a device.
    const measure = (d: string) => {
      const points = samplePath(d, 4000);
      let total = 0;
      for (let i = 1; i < points.length; i += 1) {
        total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
      }
      return total;
    };

    expect(measure(ROUTE_UPPER_PATH)).toBeCloseTo(MARK_UPPER_LENGTH, 2);
    expect(measure(ROUTE_LOWER_REVEAL_PATH)).toBeCloseTo(MARK_LOWER_LENGTH, 2);
  });

  it('never sets an opacity on the routes', async () => {
    // The crossfade this replaced. If either route carries an opacity again, the
    // mark can fade into existence instead of being drawn by the network.
    const moving = await renderWithProviders(<AnimatedSyncMark />);

    for (const id of ['sync-route-upper', 'sync-route-lower']) {
      const props = moving.getByTestId(id).props;
      expect(props.opacity).toBeUndefined();
      expect(props.strokeOpacity).toBeUndefined();
    }
  });
});
