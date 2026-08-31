/**
 * The animated network.
 *
 * Structural only. What it looks like in motion is a device question; what is
 * testable here is that it animates exactly the approved elements, that its
 * geometry is still the shared constants rather than a second copy, and that it
 * owns no timing of its own.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { AnimatedLaunchNetwork } from '@/features/startup/AnimatedLaunchNetwork';
import { LaunchNetwork } from '@/features/startup/LaunchNetwork';
import {
  INDICATOR_JOURNEY,
  NETWORK_ELEMENT_IDS,
  NETWORK_INDICATOR,
  NETWORK_NODES,
  LOWER_JOURNEY,
  NETWORK_ROUTES,
  QUIET_DRIFT,
  ROUTE_ENDPOINT,
  ROUTE_LENGTH,
} from '@/features/startup/network-geometry';
import { window as flowWindow } from '@/features/startup/launch-timeline';
import { renderWithProviders } from '@/test-utils/render';

const HIDDEN = { includeHiddenElements: true } as const;
const SCENE = { size: 320, markSize: 86 } as const;

describe('the animated network draws the approved scene', () => {
  it('renders every approved element and no others', async () => {
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    // Every approved element except the indicator, which is not part of the
    // animated composition: both primary dots now travel the flow themselves,
    // so a separate particle running the same curve was one object too many.
    for (const id of NETWORK_ELEMENT_IDS.filter((each) => each !== NETWORK_INDICATOR.id)) {
      expect(view.getByTestId(id, HIDDEN)).toBeTruthy();
    }
    expect(view.queryByTestId(NETWORK_INDICATOR.id, HIDDEN)).toBeNull();
  });

  it('adds one connector per primary route and nothing else', async () => {
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    expect(view.getByTestId('route-arrival-connector', HIDDEN)).toBeTruthy();
    expect(view.getByTestId('route-approach-connector', HIDDEN)).toBeTruthy();
  });

  it('keeps primary and contextual geometry separately addressable', async () => {
    // The timeline moves them independently, so they must stay independent
    // elements rather than being flattened into one layer.
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    for (const route of NETWORK_ROUTES) {
      expect(view.getByTestId(route.id, HIDDEN)).toBeTruthy();
    }
    for (const node of NETWORK_NODES) {
      expect(view.getByTestId(node.id, HIDDEN)).toBeTruthy();
    }
  });

  it('uses the same path data as the static composition', async () => {
    // One source of geometry. If these ever diverge the approved static scene
    // and the animated one are two different pictures.
    const still = await renderWithProviders(<LaunchNetwork size={320} />);
    const moving = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    for (const route of NETWORK_ROUTES) {
      expect(moving.getByTestId(route.id, HIDDEN).props.d).toBe(
        still.getByTestId(route.id, HIDDEN).props.d,
      );
    }
  });

  it('anchors every node where the static scene puts it', async () => {
    // The centres are the authored coordinates in both. The primary radii are
    // animated on the moving scene, since those dots resolve into rings, so only
    // the quiet ones can be compared whole.
    const still = await renderWithProviders(<LaunchNetwork size={320} />);
    const moving = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    for (const node of NETWORK_NODES) {
      const a = still.getByTestId(node.id, HIDDEN).props;
      const b = moving.getByTestId(node.id, HIDDEN).props;

      expect([b.cx, b.cy]).toEqual([a.cx, a.cy]);
      if (node.emphasis === 'quiet') expect(b.r).toBe(a.r);
    }
  });

  it('renders in dark mode', async () => {
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />, {
      mode: 'dark',
    });

    expect(view.getByTestId('animated-launch-network', HIDDEN)).toBeTruthy();
  });
});

describe('the network flows rather than translating', () => {
  it('translates no route layer at all', async () => {
    // A complete curve sliding inward moves every one of its points at the same
    // speed in the same direction, which is a rigid body. All five routes live
    // in one static layer now and only the window along each one moves.
    const source = readFileSync(join(__dirname, '..', 'AnimatedLaunchNetwork.tsx'), 'utf8');

    expect(source).not.toMatch(/arrivalLayer|approachLayer/);
    expect(source).not.toMatch(/ROUTE_ENTRY/);
  });

  it('gives every route an animated window rather than a static dash', async () => {
    // The dash has to change length as the head outruns and then loses the tail.
    // A fixed dasharray would be a fixed-length segment sliding along, which is
    // the rigid problem again in a smaller form.
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);

    for (const route of NETWORK_ROUTES) {
      const [dash, gap] = view.getByTestId(route.id, HIDDEN).props.strokeDasharray;

      // At rest the window is empty, and the gap is longer than the path so a
      // second dash can never appear on it. That is what keeps this a single
      // travelling segment rather than a dotted line.
      expect(dash).toBeLessThan(0.01);
      expect(gap).toBeGreaterThan(ROUTE_LENGTH[route.id]);
    }
  });

  it('measures every route length accurately', () => {
    // The window is expressed in each path's own units, so a wrong length puts
    // the head and tail in the wrong place for the whole journey.
    const measure = (d: string) => {
      const numbers = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);
      let from = { x: numbers[0], y: numbers[1] };
      let total = 0;

      for (let i = 2; i + 5 < numbers.length; i += 6) {
        const [c1x, c1y, c2x, c2y, x, y] = numbers.slice(i, i + 6);
        let previous = from;
        for (let k = 1; k <= 4000; k += 1) {
          const t = k / 4000;
          const u = 1 - t;
          const point = {
            x: u ** 3 * from.x + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t ** 3 * x,
            y: u ** 3 * from.y + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t ** 3 * y,
          };
          total += Math.hypot(point.x - previous.x, point.y - previous.y);
          previous = point;
        }
        from = { x, y };
      }
      return total;
    };

    for (const route of NETWORK_ROUTES) {
      expect(measure(route.d)).toBeCloseTo(ROUTE_LENGTH[route.id], 2);
    }
  });

  it('runs the contextual window off the end of its own path', () => {
    // The bug this replaced. The distance used to stop at the length of the
    // path, which puts the head at the end and leaves the tail one lag short of
    // it, so the last 55 percent of the grey route sat beside the finished mark
    // indefinitely. The journey has to run on by the lag for the window to close.
    const contextLength = ROUTE_LENGTH['route-context'];
    const lag = contextLength * 0.55;

    const final = flowWindow(contextLength + lag, lag, 0, contextLength);

    expect(final.tail).toBeCloseTo(contextLength);
    expect(final.visible).toBeCloseTo(0);
  });

  it('would have stranded the tail without the extra distance', () => {
    // The same call with the old journey length, kept so the regression is
    // stated rather than implied.
    const contextLength = ROUTE_LENGTH['route-context'];
    const lag = contextLength * 0.55;

    expect(flowWindow(contextLength, lag, 0, contextLength).visible).toBeCloseTo(lag);
  });

  it('leaves nothing of the contextual route on screen at the end', async () => {
    // A zero-length dash with round caps still paints a dot on some renderers,
    // so the stroke opacity is taken to zero once the window has closed.
    const view = await renderWithProviders(
      <AnimatedLaunchNetwork {...SCENE} progress={{ value: 1 } as never} />,
    );

    expect(view.getByTestId('route-context', HIDDEN).props.strokeOpacity).toBe(0);
  });

  it('keeps the contextual route visible while it is still flowing', async () => {
    const view = await renderWithProviders(
      <AnimatedLaunchNetwork {...SCENE} progress={{ value: 0.3 } as never} />,
    );

    expect(view.getByTestId('route-context', HIDDEN).props.strokeOpacity).toBeGreaterThan(0);
  });

  it('keeps the contextual route quiet while it flows', async () => {
    // It moves now rather than merely fading, but it is still scenery: muted
    // token, reduced opacity, thinner stroke than the primaries.
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);
    const context = NETWORK_ROUTES.find((route) => route.emphasis === 'quiet')!;
    const primary = NETWORK_ROUTES.find((route) => route.emphasis === 'primary')!;
    const props = view.getByTestId(context.id, HIDDEN).props;

    expect(props.strokeOpacity).toBeLessThan(1);
    expect(props.strokeWidth).toBeLessThan(primary.width);
  });

  it('rounds both ends of every route', async () => {
    // The head of a travelling window is a stroke end. Square caps would make it
    // read as a cut length of something rather than as a leading edge.
    // Compared against the static scene rather than against a literal, because
    // react-native-svg resolves the cap to its own enum on the way through.
    const still = await renderWithProviders(<LaunchNetwork size={320} />);
    const view = await renderWithProviders(<AnimatedLaunchNetwork {...SCENE} />);
    const round = still.getByTestId('route-arrival', HIDDEN).props.strokeLinecap;

    for (const id of [
      ...NETWORK_ROUTES.map((route) => route.id),
      'route-arrival-connector',
      'route-approach-connector',
    ]) {
      expect(view.getByTestId(id, HIDDEN).props.strokeLinecap).toBe(round);
    }
  });
});

describe('every dot travels', () => {
  it('gives both primary dots an authored journey', () => {
    // `node-b` was the stationary one. It sat at the bend of its own route while
    // the route flowed past it, which is the fastest thing to notice.
    expect(INDICATOR_JOURNEY.length).toBeGreaterThanOrEqual(12);
    expect(LOWER_JOURNEY.length).toBeGreaterThanOrEqual(12);
  });

  it('starts each primary journey on its own node', () => {
    const nodeA = NETWORK_NODES.find((n) => n.id === 'node-a')!;
    const nodeB = NETWORK_NODES.find((n) => n.id === 'node-b')!;

    expect(INDICATOR_JOURNEY[0]).toEqual({ x: nodeA.cx, y: nodeA.cy });
    expect(LOWER_JOURNEY[0]).toEqual({ x: nodeB.cx, y: nodeB.cy });
  });

  it('ends each primary journey on its route endpoint', () => {
    expect(INDICATOR_JOURNEY[INDICATOR_JOURNEY.length - 1]).toEqual(
      ROUTE_ENDPOINT['route-arrival'],
    );
    expect(LOWER_JOURNEY[LOWER_JOURNEY.length - 1]).toEqual(
      ROUTE_ENDPOINT['route-approach'],
    );
  });

  it('spaces the lower journey as evenly as the upper one', () => {
    for (const journey of [INDICATOR_JOURNEY, LOWER_JOURNEY]) {
      const steps = journey.slice(1).map((point, i) =>
        Math.hypot(point.x - journey[i].x, point.y - journey[i].y),
      );
      const mean = steps.reduce((a, b) => a + b, 0) / steps.length;

      for (const step of steps) {
        expect(Math.abs(step - mean) / mean).toBeLessThan(0.1);
      }
    }
  });

  it('moves both quiet dots before they recede', () => {
    // A dot that only dims looks switched off. These pull away along the route
    // they belong to and shrink as they go.
    for (const id of ['node-c', 'node-d']) {
      const drift = QUIET_DRIFT[id];
      const travelled = Math.hypot(
        drift[drift.length - 1].x - drift[0].x,
        drift[drift.length - 1].y - drift[0].y,
      );

      expect(drift.length).toBeGreaterThanOrEqual(3);
      expect(travelled).toBeGreaterThan(10);
    }
  });

  it('starts each quiet drift on its own node', () => {
    for (const id of ['node-c', 'node-d']) {
      const node = NETWORK_NODES.find((n) => n.id === id)!;
      expect(QUIET_DRIFT[id][0]).toEqual({ x: node.cx, y: node.cy });
    }
  });

  it('leaves no animated dot without somewhere to go', () => {
    // The whole rule: nothing on screen is pinned while the scene moves.
    const journeys: Record<string, readonly { x: number; y: number }[]> = {
      'node-a': INDICATOR_JOURNEY,
      'node-b': LOWER_JOURNEY,
      'node-c': QUIET_DRIFT['node-c'],
      'node-d': QUIET_DRIFT['node-d'],
    };

    for (const node of NETWORK_NODES) {
      const journey = journeys[node.id];
      expect(journey).toBeTruthy();

      const travelled = Math.hypot(
        journey[journey.length - 1].x - journey[0].x,
        journey[journey.length - 1].y - journey[0].y,
      );
      expect(travelled).toBeGreaterThan(node.r * 2);
    }
  });
});

describe('the geometry the timeline aims at', () => {
  it('states each primary route endpoint as its real path end', () => {
    // The convergence translates routes onto the mark by arithmetic on these
    // numbers rather than by parsing a path at runtime. This is what stops the
    // restated endpoints drifting away from the paths they came from.
    const ends: Record<string, { x: number; y: number }> = {
      'route-arrival': { x: 212, y: 108 },
      'route-approach': { x: 108, y: 212 },
    };

    for (const [id, end] of Object.entries(ends)) {
      const route = NETWORK_ROUTES.find((candidate) => candidate.id === id)!;
      const last = route.d.trim().split(/[\s,]+/).slice(-2).map(Number);

      expect(ROUTE_ENDPOINT[id]).toEqual(end);
      expect(last).toEqual([end.x, end.y]);
    }
  });

  it('keeps the indicator journey short and inward', () => {
    const first = INDICATOR_JOURNEY[0];
    const last = INDICATOR_JOURNEY[INDICATOR_JOURNEY.length - 1];
    const centre = { x: 160, y: 160 };

    // It should finish nearer the mark than it started, or it is not a journey
    // toward Sync.
    expect(Math.hypot(last.x - centre.x, last.y - centre.y)).toBeLessThan(
      Math.hypot(first.x - centre.x, first.y - centre.y),
    );
  });

  it('starts the indicator journey on the primary node', () => {
    const nodeA = NETWORK_NODES.find((n) => n.id === 'node-a')!;

    expect(INDICATOR_JOURNEY[0]).toEqual({ x: nodeA.cx, y: nodeA.cy });
  });

  it('ends the indicator journey on the route it is travelling', () => {
    const last = INDICATOR_JOURNEY[INDICATOR_JOURNEY.length - 1];

    expect(last).toEqual(ROUTE_ENDPOINT['route-arrival']);
  });

  it('authors the journey as literals rather than sampling a path', () => {
    // The reason these exist. Every waypoint is a plain number, so nothing
    // evaluates a bezier while the animation is running.
    for (const point of INDICATOR_JOURNEY) {
      expect(Number.isFinite(point.x)).toBe(true);
      expect(Number.isFinite(point.y)).toBe(true);
    }
    expect(INDICATOR_JOURNEY.length).toBeGreaterThanOrEqual(2);
  });
});
