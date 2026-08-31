/**
 * The animated launch sequence.
 *
 * What is protected here is the architecture rather than any duration. Both
 * layers must be mounted for the whole sequence, one shared value must own all
 * of it, nothing may mount partway through, and completion must reach
 * `LaunchScreen` exactly once and only after the mark has settled and held.
 *
 * Nothing asserts elapsed time. The sequence runs on the UI thread through
 * Reanimated, so its completion boundary is invoked explicitly instead.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { act } from '@testing-library/react-native';

import { AnimatedLaunchComposition } from '@/features/startup/AnimatedLaunchComposition';
import {
  NETWORK_ELEMENT_IDS,
  NETWORK_INDICATOR,
  NETWORK_NODES,
  NETWORK_ROUTES,
} from '@/features/startup/network-geometry';
import {
  ROUTE_TRANSFER,
  SEGMENT,
  SEQUENCE_MS,
  connectors,
  dashWindow,
  easeInOut,
  easeOut,
  flowPlan,
  stage,
  window as flowWindow,
} from '@/features/startup/launch-timeline';
import { ROUTE_STROKE_WIDTH as MARK_STROKE } from '@/components/brand/mark-geometry';
import { renderWithProviders } from '@/test-utils/render';

const HIDDEN = { includeHiddenElements: true } as const;

/** Captured stand-in, so the one completion boundary can be fired on demand. */
let finish: (() => void) | undefined;
let timings = 0;

jest.mock('react-native-reanimated', () => {
  const actual = jest.requireActual('react-native-reanimated');
  return {
    // Spreading alone loses the non-enumerable `__esModule` flag, which makes
    // interop hand back the whole module for the default import and leaves
    // `Animated.View` undefined.
    __esModule: true,
    ...actual,
    default: actual.default,
    withTiming: (toValue: number, config: unknown, callback?: () => void) => {
      timings += 1;
      finish = callback;
      return actual.withTiming(toValue, config);
    },
  };
});

beforeEach(() => {
  finish = undefined;
  timings = 0;
});

function renderComposition(onComplete = jest.fn()) {
  return renderWithProviders(
    <AnimatedLaunchComposition size={320} markSize={86} onComplete={onComplete} />,
  ).then((view) => ({ view, onComplete }));
}

describe('one timeline', () => {
  it('drives the whole sequence from a single timing', async () => {
    // The correction. Seven independently delayed animations across two
    // components is what produced the pauses, because a delay is a gap by
    // construction and nothing forced any two of them to overlap.
    await renderComposition();

    expect(timings).toBe(1);
  });

  it('mounts both layers from the first frame', async () => {
    // Previously the mark was mounted partway through by a React state change,
    // which put a component boundary exactly where the eye needed continuity.
    const { view } = await renderComposition();

    expect(view.getByTestId('animated-launch-network', HIDDEN)).toBeTruthy();
    expect(view.getByTestId('animated-sync-mark', HIDDEN)).toBeTruthy();
  });

  it('keeps every network and mark element addressable throughout', async () => {
    const { view } = await renderComposition();

    // The indicator is not part of the animated composition: once both primary
    // dots travel the flow it was a second object doing the same job.
    for (const id of NETWORK_ELEMENT_IDS.filter((each) => each !== NETWORK_INDICATOR.id)) {
      expect(view.getByTestId(id, HIDDEN)).toBeTruthy();
    }
    for (const id of [
      'route-arrival-connector',
      'route-approach-connector',
      'sync-route-upper',
      'sync-route-lower',
      'sync-node-upper',
      'sync-node-lower',
    ]) {
      expect(view.getByTestId(id, HIDDEN)).toBeTruthy();
    }
  });

  it('mounts nothing partway through', () => {
    // Architectural, so it is checked against the source: a `useState` here is
    // the seam this revision removed, and no rendered output would show it.
    const source = readFileSync(
      join(__dirname, '..', 'AnimatedLaunchComposition.tsx'),
      'utf8',
    );

    expect(source).not.toMatch(/useState/);
  });
});

describe('completion', () => {
  it('does not complete on mount', async () => {
    const { onComplete } = await renderComposition();

    expect(onComplete).not.toHaveBeenCalled();
  });

  it('completes when the timeline finishes', async () => {
    const { onComplete } = await renderComposition();

    await act(async () => finish?.());

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('completes once however often the boundary fires', async () => {
    const { onComplete } = await renderComposition();

    await act(async () => finish?.());
    await act(async () => finish?.());
    await act(async () => finish?.());

    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('does nothing when the boundary lands after unmount', async () => {
    // The launch surface can go at any moment. Nothing here may call back into
    // a component that has left.
    const { view, onComplete } = await renderComposition();

    await act(async () => {
      view.unmount();
    });
    await act(async () => finish?.());

    expect(onComplete).not.toHaveBeenCalled();
  });
});

describe('the segments', () => {
  it('runs for a duration that leaves room for the flow to read', () => {
    expect(SEQUENCE_MS).toBeGreaterThanOrEqual(1750);
    expect(SEQUENCE_MS).toBeLessThanOrEqual(2050);
  });

  it('spans the whole clock without a gap at either end', () => {
    expect(SEGMENT.contextFlow[0]).toBe(0);
    expect(SEGMENT.hold[1]).toBe(1);
  });

  it('gives each stream one range for its entire journey', () => {
    // The correction. Route, connector and mark used to have a segment each, so
    // the stream decelerated to almost nothing twice on the way in. There is now
    // one range per stream and the legs are slices of one distance inside it.
    for (const range of [SEGMENT.upperFlow, SEGMENT.lowerFlow]) {
      expect(range[1] - range[0]).toBeGreaterThan(0.7);
    }
  });

  it('staggers the two streams without separating them', () => {
    const stagger = SEGMENT.lowerFlow[0] - SEGMENT.upperFlow[0];

    expect(stagger).toBeGreaterThan(0);
    expect(stagger * SEQUENCE_MS).toBeGreaterThanOrEqual(40);
    expect(stagger * SEQUENCE_MS).toBeLessThanOrEqual(70);
  });

  it('clears the scenery before the streams finish', () => {
    // It is context. If it were still travelling while the mark formed it would
    // be competing with the thing the mark is for.
    expect(SEGMENT.contextFlow[1]).toBeLessThan(SEGMENT.upperFlow[1]);
    expect(SEGMENT.contextFlow[1]).toBeLessThan(SEGMENT.lowerFlow[1]);
  });

  it('starts the context flowing from the first frame', () => {
    expect(SEGMENT.contextFlow[0]).toBe(0);
    expect(SEGMENT.contextFlow[0]).toBeLessThan(SEGMENT.upperFlow[0]);
  });

  it('resolves the rings while the streams are still arriving', () => {
    expect(SEGMENT.ringResolve[0]).toBeLessThan(SEGMENT.upperFlow[1]);
    expect(SEGMENT.ringResolve[0]).toBeLessThan(SEGMENT.lowerFlow[1]);
  });

  it('finishes every moving part before the hold', () => {
    for (const segment of [
      SEGMENT.contextFlow,
      SEGMENT.upperFlow,
      SEGMENT.lowerFlow,
      SEGMENT.ringResolve,
    ]) {
      expect(segment[1]).toBeLessThanOrEqual(SEGMENT.hold[0]);
    }
  });

  it('starts the hold exactly where the last movement ends', () => {
    const last = Math.max(
      SEGMENT.upperFlow[1],
      SEGMENT.lowerFlow[1],
      SEGMENT.ringResolve[1],
    );

    expect(SEGMENT.hold[0]).toBe(last);
  });
});

describe('the travelling window', () => {
  it('produces one bounded interval', () => {
    for (const distance of [0, 20, 60, 100, 140, 170]) {
      const { tail, visible } = flowWindow(distance, 40, 0, 170);

      expect(visible).toBeGreaterThanOrEqual(0);
      expect(tail).toBeGreaterThanOrEqual(0);
      expect(tail + visible).toBeLessThanOrEqual(170 + 1e-9);
    }
  });

  it('never lets the window exceed the lag', () => {
    // If it did, the whole route would be drawn at once, which is the rigid line
    // this replaced.
    for (let d = 0; d <= 170; d += 5) {
      expect(flowWindow(d, 40, 0, 170).visible).toBeLessThanOrEqual(40 + 1e-9);
    }
  });

  it('grows then contracts rather than only growing', () => {
    // A head that outruns a tail pinned at zero is an endlessly growing line.
    // The contraction happens once the head has reached the end of the leg and
    // the stream keeps going, which is when it is flowing on into the connector.
    const early = flowWindow(15, 40, 0, 170).visible;
    const middle = flowWindow(85, 40, 0, 170).visible;
    const leaving = flowWindow(190, 40, 0, 170).visible;
    const gone = flowWindow(210, 40, 0, 170).visible;

    expect(middle).toBeGreaterThan(early);
    expect(leaving).toBeLessThan(middle);
    expect(gone).toBe(0);
  });

  it('is empty before the window reaches its leg and after it leaves', () => {
    expect(flowWindow(10, 40, 100, 200).visible).toBe(0);
    expect(flowWindow(400, 40, 100, 200).visible).toBe(0);
  });

  it('draws one dash and never a repeat', () => {
    // The gap is longer than the path, so a second dash cannot fit on it. That
    // is what stops this reading as a dotted line.
    const { strokeDasharray } = dashWindow(30, 10, 170);

    expect(strokeDasharray[1]).toBeGreaterThan(170);
  });

  it('keeps the dash offset positive at every point of the travel', () => {
    // Negative dash phase is well defined in SVG and not reliably the same once
    // it reaches the platform. The offset is written one period along instead.
    for (let tail = 0; tail <= 170; tail += 10) {
      expect(dashWindow(20, tail, 170).strokeDashoffset).toBeGreaterThan(0);
    }
  });

  it('never collapses the dash to zero length', () => {
    // A zero-length dash with round caps draws a dot on some renderers, which
    // would sit at the start of a route that has not begun flowing.
    expect(dashWindow(0, 0, 170).strokeDasharray[0]).toBeGreaterThan(0);
  });
});

describe('one uninterrupted journey', () => {
  const plan = flowPlan(320, 86);

  it('measures all three legs and their total', () => {
    for (const stream of [plan.upper, plan.lower]) {
      expect(stream.route).toBeGreaterThan(0);
      expect(stream.connector).toBeGreaterThan(0);
      expect(stream.mark).toBeGreaterThan(0);
      expect(stream.total).toBeCloseTo(stream.route + stream.connector + stream.mark);
    }
  });

  it('keeps the ribbon continuous across the route to connector boundary', () => {
    // The property the whole revision rests on. However the journey is sliced
    // into legs, the drawn length is always exactly the interval between tail
    // and head. A shortfall at any distance would be a gap opening at a
    // boundary, which is the stream visibly breaking in two.
    const stream = plan.upper;
    const flowing = stream.route + stream.connector;
    const clamp = (n: number) => (n < 0 ? 0 : n > flowing ? flowing : n);

    for (let d = 0; d <= stream.total; d += stream.total / 400) {
      const drawn =
        flowWindow(d, stream.lag, 0, stream.route).visible +
        flowWindow(d, stream.lag, stream.route, flowing).visible;

      expect(drawn).toBeCloseTo(clamp(d) - clamp(d - stream.lag), 6);
    }
  });

  it('begins depositing the mark exactly as the ribbon leaves the connector', () => {
    // The second boundary. The mark's leg starts at zero at the instant the head
    // crosses out of the connector, so the stroke it lays down continues the
    // stream rather than starting somewhere ahead of it.
    const stream = plan.upper;
    const flowing = stream.route + stream.connector;
    const deposited = (d: number) =>
      Math.min(Math.max(d - flowing, 0), stream.mark);

    expect(deposited(flowing - 0.001)).toBe(0);
    expect(deposited(flowing)).toBe(0);
    expect(deposited(flowing + 5)).toBeCloseTo(5);
    expect(deposited(stream.total)).toBeCloseTo(stream.mark);

    // And the ribbon's head is at the connector's end at that same moment.
    const { tail, visible } = flowWindow(flowing, stream.lag, stream.route, flowing);
    expect(stream.route + tail + visible).toBeCloseTo(flowing, 6);
  });

  it('advances the head monotonically', () => {
    const stream = plan.lower;
    let previous = -1;

    for (let d = 0; d <= stream.total; d += stream.total / 200) {
      const { tail, visible } = flowWindow(d, stream.lag, 0, stream.route);
      const head = tail + visible;
      expect(head).toBeGreaterThanOrEqual(previous - 1e-9);
      previous = head;
    }
  });

  it('scales the journey with the scene', () => {
    // The network scales with the screen and the mark does not, so the distance
    // between them genuinely depends on the size.
    expect(flowPlan(280, 86).upper.total).not.toBeCloseTo(flowPlan(380, 86).upper.total);
  });

  it('lags the tail behind the head by a fraction of the route', () => {
    for (const stream of [plan.upper, plan.lower]) {
      expect(stream.lag).toBeGreaterThan(0);
      expect(stream.lag).toBeLessThan(stream.route);
    }
  });
});

describe('easing', () => {
  it('holds each curve to its endpoints', () => {
    for (const curve of [easeOut, easeInOut]) {
      expect(curve(0)).toBeCloseTo(0);
      expect(curve(1)).toBeCloseTo(1);
    }
  });

  it('advances monotonically', () => {
    // A curve that dipped would show as a route stalling or reversing.
    for (const curve of [easeOut, easeInOut]) {
      let previous = -1;
      for (let t = 0; t <= 1.0001; t += 0.05) {
        const value = curve(t);
        expect(value).toBeGreaterThanOrEqual(previous);
        previous = value;
      }
    }
  });

  it('clamps segment progress at both ends', () => {
    expect(stage(0, SEGMENT.upperFlow)).toBe(0);
    expect(stage(1, SEGMENT.upperFlow)).toBe(1);
    expect(stage(SEGMENT.upperFlow[0], SEGMENT.upperFlow)).toBe(0);
    expect(stage(SEGMENT.upperFlow[1], SEGMENT.upperFlow)).toBe(1);
  });
});

describe('the connectors', () => {
  const bridge = connectors(320, 86);

  it('starts each one exactly where its route ends', () => {
    expect(bridge['route-arrival'].from).toEqual({ x: 212, y: 108 });
    expect(bridge['route-approach'].from).toEqual({ x: 108, y: 212 });
  });

  it('finishes each one on the mapped ring centre', () => {
    // (52, 12) and (12, 55) in mark units, mapped into the network's square.
    const scale = (86 / 320) * (320 / 64);
    const origin = 320 / 2 - (64 * scale) / 2;

    expect(bridge['route-arrival'].to.x).toBeCloseTo(origin + 52 * scale);
    expect(bridge['route-arrival'].to.y).toBeCloseTo(origin + 12 * scale);
    expect(bridge['route-approach'].to.x).toBeCloseTo(origin + 12 * scale);
    expect(bridge['route-approach'].to.y).toBeCloseTo(origin + 55 * scale);
  });

  it('leaves each route along the tangent it arrives on', () => {
    // The upper route finishes travelling left and its connector must leave
    // travelling left; the lower one the other way. Anything else is a corner at
    // the handover, which is what the elbows were.
    const upper = bridge['route-arrival'];
    const lower = bridge['route-approach'];

    expect(upper.control[0].y).toBe(upper.from.y);
    expect(upper.control[0].x).toBeLessThan(upper.from.x);
    expect(lower.control[0].y).toBe(lower.from.y);
    expect(lower.control[0].x).toBeGreaterThan(lower.from.x);
  });

  it('approaches each ring horizontally', () => {
    const upper = bridge['route-arrival'];
    const lower = bridge['route-approach'];

    expect(upper.control[1].y).toBeCloseTo(upper.to.y);
    expect(upper.control[1].x).toBeGreaterThan(upper.to.x);
    expect(lower.control[1].y).toBeCloseTo(lower.to.y);
    expect(lower.control[1].x).toBeLessThan(lower.to.x);
  });

  it('writes a path that matches its own endpoints', () => {
    for (const id of ['route-arrival', 'route-approach']) {
      const { d, from, to } = bridge[id];
      const numbers = d.match(/-?\d+(?:\.\d+)?/g)!.map(Number);

      expect(numbers[0]).toBeCloseTo(from.x);
      expect(numbers[1]).toBeCloseTo(from.y);
      expect(numbers[numbers.length - 2]).toBeCloseTo(to.x, 1);
      expect(numbers[numbers.length - 1]).toBeCloseTo(to.y, 1);
    }
  });

  it('stays short relative to the route it extends', () => {
    // It is a bridge, not a leg of the composition. If it were long it would be
    // a third route nobody designed.
    const plan = flowPlan(320, 86);

    expect(plan.upper.connector).toBeLessThan(plan.upper.route * 0.5);
    expect(plan.lower.connector).toBeLessThan(plan.lower.route * 0.5);
  });

  it('pairs each primary route with the mark route on its own diagonal', () => {
    expect(ROUTE_TRANSFER['route-arrival']).toBe('upper');
    expect(ROUTE_TRANSFER['route-approach']).toBe('lower');
  });
});

describe('no rigid translation', () => {
  it('never translates a primary route layer', () => {
    // The thing the recording caught: a complete curve sliding inward moves
    // every one of its points the same way, which is a stick being pushed. The
    // curves are fixed now and only the window along them moves.
    const source = readFileSync(join(__dirname, '..', 'AnimatedLaunchNetwork.tsx'), 'utf8');

    expect(source).not.toMatch(/arrivalLayer|approachLayer/);
    expect(source).not.toMatch(/ROUTE_ENTRY/);
  });

  it('no longer exposes the rigid alignment helper', () => {
    const timeline = readFileSync(join(__dirname, '..', 'launch-timeline.ts'), 'utf8');

    expect(timeline).not.toMatch(/convergence/);
    expect(timeline).not.toMatch(/MARK_ENTRY/);
  });
});

describe('stroke width continuity', () => {
  it('hands the mark the width the route arrives at', () => {
    // Both in the mark's 64 unit system. A 2.5 unit route on a 320 unit viewBox
    // drawn at 320 points is 2.5 points wide, and the same 2.5 points against an
    // 86 point mark is 1.86 of its units, which is where the mark stroke starts.
    const incoming = 2.5 * (320 / 320) * (64 / 86);

    expect(incoming).toBeCloseTo(1.86, 2);
    expect(incoming).toBeLessThan(MARK_STROKE);
  });

  it('is thinner than the mark it grows into at every scene size', () => {
    for (const size of [260, 320, 380]) {
      expect(2.5 * (size / 320) * (64 / 86)).toBeLessThan(MARK_STROKE);
    }
  });
});

describe('the element budget', () => {
  it('animates the approved elements and nothing else', async () => {
    expect(NETWORK_ROUTES).toHaveLength(3);
    expect(NETWORK_NODES).toHaveLength(4);
    expect(NETWORK_ELEMENT_IDS).toHaveLength(8);
    expect(NETWORK_INDICATOR.id).toBe('route-indicator');
  });
});
