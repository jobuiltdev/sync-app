import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  useAnimatedProps,
  useAnimatedStyle,
  useSharedValue,
} from 'react-native-reanimated';
import type { SharedValue } from 'react-native-reanimated';
import Svg, { Circle, Path } from 'react-native-svg';

import {
  INDICATOR_JOURNEY,
  LOWER_JOURNEY,
  NETWORK_NODES,
  NETWORK_ROUTES,
  NETWORK_VIEWBOX,
  QUIET_DRIFT,
  ROUTE_LENGTH,
} from '@/features/startup/network-geometry';
import {
  SEGMENT,
  connectors,
  cubicPoint,
  dashWindow,
  eased,
  easeInOut,
  easeOut,
  flowPlan,
  stage,
  window as flowWindow,
} from '@/features/startup/launch-timeline';
import { usePalette } from '@/theme/theme';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/**
 * The network, as something flowing rather than something arriving.
 *
 * ### Nothing here moves as a whole
 *
 * The previous version translated each complete route inward. Every point of a
 * curve then moves at the same speed in the same direction, which is a rigid
 * body: on a recording it read as two sticks sliding toward the middle, and no
 * amount of easing changes that, because the shape never does anything.
 *
 * The curves are now fixed exactly where `network-geometry` authors them, and
 * the only thing that moves is a window along each one. A head runs inward, a
 * tail follows a fixed distance behind, and what is drawn is the interval
 * between. The stroke therefore follows the bend of the route, grows while the
 * head outruns the tail and contracts when the tail catches up, none of which a
 * rigid translation can do.
 *
 * ### One distance for the whole journey
 *
 * Each stream has a single monotonic distance covering its route, its connector
 * and its share of the mark, measured in points so that a constant velocity
 * means the same thing across three legs in two coordinate systems. Nothing is
 * eased per leg. The previous version eased each stage separately, so the stream
 * slowed almost to a stop at every boundary, and three smooth legs joined by two
 * stalls is not one movement.
 *
 * ### Every dot has somewhere to be
 *
 * Both primary nodes travel their own routes and continue through their
 * connectors to the ring that replaces them. Both quiet nodes drift along the
 * contextual route before receding. Nothing on screen is pinned while the scene
 * moves around it, which is exactly what `node-b` was doing.
 *
 * The standalone indicator is gone from this composition. Once the primary dots
 * carry the flow it was a second object doing the same job.
 */

export interface AnimatedLaunchNetworkProps {
  /** Side of the square the network is drawn into, in points. */
  size: number;
  /** The mark's point size, which is what the connectors have to reach. */
  markSize: number;
  /**
   * The launch clock, 0 to 1.
   *
   * Optional only so the scene can be rendered in isolation for structural
   * tests. In the app it is always the composition's single shared value.
   */
  progress?: SharedValue<number>;
}

export function AnimatedLaunchNetwork({
  size,
  markSize,
  progress,
}: AnimatedLaunchNetworkProps) {
  const palette = usePalette();

  const standalone = useSharedValue(0);
  const clock = progress ?? standalone;

  const unit = size / NETWORK_VIEWBOX;

  const [arrival, approach, context] = NETWORK_ROUTES;
  const [nodeA, nodeB] = NETWORK_NODES.filter((node) => node.emphasis === 'primary');
  const quietNodes = NETWORK_NODES.filter((node) => node.emphasis === 'quiet');

  const bridge = useMemo(() => connectors(size, markSize), [size, markSize]);
  const plan = useMemo(() => flowPlan(size, markSize), [size, markSize]);

  /**
   * Where each travelling dot goes, as one list per stream.
   *
   * The route half is the authored waypoints; the connector half is sampled from
   * the memoized connector, which is arithmetic on four known points rather than
   * anything parsed. Built once per size, never per frame.
   */
  const dotPath = useMemo(() => {
    const along = (id: string, waypoints: readonly { x: number; y: number }[]) => {
      const { from, to, control } = bridge[id];
      const connector = Array.from({ length: 9 }, (_, i) =>
        cubicPoint(from, control[0], control[1], to, (i + 1) / 9),
      );
      return [...waypoints, ...connector];
    };

    return {
      upper: along('route-arrival', INDICATOR_JOURNEY),
      lower: along('route-approach', LOWER_JOURNEY),
    };
  }, [bridge]);

  const upperDots = dotPath.upper;
  const lowerDots = dotPath.lower;
  const upperPlan = plan.upper;
  const lowerPlan = plan.lower;
  const arrivalLength = ROUTE_LENGTH[arrival.id];
  const approachLength = ROUTE_LENGTH[approach.id];
  const contextLength = ROUTE_LENGTH[context.id];
  const upperConnector = bridge[arrival.id];
  const lowerConnector = bridge[approach.id];

  // Written out per element rather than through a helper: `useAnimatedStyle` and
  // `useAnimatedProps` are hooks, and a hook called from a plain function is a
  // rule violation even where the call order happens to be stable.

  const arrivalStroke = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.upperFlow, easeInOut) * upperPlan.total;
    const { tail, visible } = flowWindow(flown, upperPlan.lag, 0, upperPlan.route);

    // Back into this route's own viewBox units, which is what the dash wants.
    return dashWindow(visible / unit, tail / unit, arrivalLength);
  });

  const approachStroke = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.lowerFlow, easeInOut) * lowerPlan.total;
    const { tail, visible } = flowWindow(flown, lowerPlan.lag, 0, lowerPlan.route);

    return dashWindow(visible / unit, tail / unit, approachLength);
  });

  const upperBridgeStroke = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.upperFlow, easeInOut) * upperPlan.total;
    const { tail, visible } = flowWindow(
      flown,
      upperPlan.lag,
      upperPlan.route,
      upperPlan.route + upperPlan.connector,
    );

    return dashWindow(visible / unit, tail / unit, upperConnector.length);
  });

  const lowerBridgeStroke = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.lowerFlow, easeInOut) * lowerPlan.total;
    const { tail, visible } = flowWindow(
      flown,
      lowerPlan.lag,
      lowerPlan.route,
      lowerPlan.route + lowerPlan.connector,
    );

    return dashWindow(visible / unit, tail / unit, lowerConnector.length);
  });

  const contextStroke = useAnimatedProps(() => {
    // Slower and longer than the primaries, and gone before they finish. It is
    // scenery: it should be the thing noticed second.
    const lag = contextLength * 0.55;

    // The journey runs to `contextLength + lag`, not `contextLength`. Stopping
    // the head at the end of the path leaves the tail one lag short of it, so
    // the last 55 percent of the route stayed on screen next to the finished
    // mark forever. Letting the distance run on by the lag is what lets the tail
    // reach the end and the window close.
    const travelled = eased(clock.value, SEGMENT.contextFlow, easeInOut) *
      (contextLength + lag);
    const { tail, visible } = flowWindow(travelled, lag, 0, contextLength);

    // A zero-length dash with round caps still paints a dot on some renderers,
    // which would leave a grey speck at the end of the route. This is that
    // cleanup and nothing else: by the time it applies the window has already
    // closed, so there is no fade to see.
    const closed = stage(clock.value, SEGMENT.contextFlow) >= 1 || visible <= 0.001;

    return {
      ...dashWindow(visible, tail, contextLength),
      strokeOpacity: closed ? 0 : context.opacity,
    };
  });

  /** Walks a waypoint list. No path is evaluated here; these are literals. */
  const travel = (points: readonly { x: number; y: number }[], t: number) => {
    'worklet';
    const last = points.length - 1;
    const scaled = t * last;
    const index = Math.min(Math.floor(scaled), last - 1);
    const within = scaled - index;
    const from = points[index];
    const to = points[index + 1];

    return {
      x: from.x + (to.x - from.x) * within,
      y: from.y + (to.y - from.y) * within,
    };
  };

  const nodeALayer = useAnimatedStyle(() => {
    // The dot rides its stream's head, so it is always at the front of the flow
    // rather than keeping its own separate time.
    const flown = eased(clock.value, SEGMENT.upperFlow, easeInOut) * upperPlan.total;
    const reached = Math.min(flown / (upperPlan.route + upperPlan.connector), 1);
    const at = travel(upperDots, reached);

    return {
      transform: [
        { translateX: (at.x - nodeA.cx) * unit },
        { translateY: (at.y - nodeA.cy) * unit },
      ],
      opacity: stage(clock.value, [0.03, 0.1]),
    };
  });

  const nodeBLayer = useAnimatedStyle(() => {
    const flown = eased(clock.value, SEGMENT.lowerFlow, easeInOut) * lowerPlan.total;
    const reached = Math.min(flown / (lowerPlan.route + lowerPlan.connector), 1);
    const at = travel(lowerDots, reached);

    return {
      transform: [
        { translateX: (at.x - nodeB.cx) * unit },
        { translateY: (at.y - nodeB.cy) * unit },
      ],
      opacity: stage(clock.value, [0.06, 0.13]),
    };
  });

  // Arriving means becoming a ring, in place. The filled centre contracts as the
  // mark's own ring grows around it at the same coordinates, so one object
  // changes rather than one fading out while another fades in somewhere else.
  const nodeAFill = useAnimatedProps(() => ({
    r: nodeA.r * (1 - eased(clock.value, SEGMENT.ringResolve, easeOut)),
  }));

  const nodeBFill = useAnimatedProps(() => ({
    r: nodeB.r * (1 - eased(clock.value, SEGMENT.ringResolve, easeOut)),
  }));

  const quietCLayer = useAnimatedStyle(() => {
    const drift = eased(clock.value, SEGMENT.contextFlow, easeInOut);
    const at = travel(QUIET_DRIFT['node-c'], drift);
    const gone = eased(clock.value, [0.4, 0.62], easeInOut);

    return {
      transform: [
        { translateX: (at.x - quietNodes[0].cx) * unit },
        { translateY: (at.y - quietNodes[0].cy) * unit },
        { scale: 1 - gone * 0.35 },
      ],
      opacity: stage(clock.value, [0.06, 0.2]) * (1 - gone),
    };
  });

  const quietDLayer = useAnimatedStyle(() => {
    const drift = eased(clock.value, SEGMENT.contextFlow, easeInOut);
    const at = travel(QUIET_DRIFT['node-d'], drift);
    const gone = eased(clock.value, [0.44, 0.66], easeInOut);

    return {
      transform: [
        { translateX: (at.x - quietNodes[1].cx) * unit },
        { translateY: (at.y - quietNodes[1].cy) * unit },
        { scale: 1 - gone * 0.35 },
      ],
      opacity: stage(clock.value, [0.1, 0.24]) * (1 - gone),
    };
  });

  const layer = [StyleSheet.absoluteFill, { width: size, height: size }];
  const svg = {
    width: size,
    height: size,
    viewBox: `0 0 ${NETWORK_VIEWBOX} ${NETWORK_VIEWBOX}`,
    fill: 'none',
  } as const;

  return (
    <View
      testID="animated-launch-network"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={{ width: size, height: size }}
    >
      {/* Every route sits in one static layer. None of these translate; the
          windows below move along them. */}
      <View style={layer} pointerEvents="none">
        <Svg {...svg}>
          <AnimatedPath
            testID={context.id}
            animatedProps={contextStroke}
            d={context.d}
            stroke={palette.inkMuted}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={context.width}
          />
          <AnimatedPath
            testID={arrival.id}
            animatedProps={arrivalStroke}
            d={arrival.d}
            stroke={palette.primary}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={arrival.width}
          />
          <AnimatedPath
            testID={approach.id}
            animatedProps={approachStroke}
            d={approach.d}
            stroke={palette.primary}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={approach.width}
          />
          {/* The connectors. Temporary by construction: the window passes
              through and nothing is left behind in the final frame. */}
          <AnimatedPath
            testID="route-arrival-connector"
            animatedProps={upperBridgeStroke}
            d={upperConnector.d}
            stroke={palette.primary}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={arrival.width}
          />
          <AnimatedPath
            testID="route-approach-connector"
            animatedProps={lowerBridgeStroke}
            d={lowerConnector.d}
            stroke={palette.primary}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={approach.width}
          />
        </Svg>
      </View>

      <Animated.View style={[layer, quietCLayer]}>
        <Svg {...svg}>
          <Circle
            testID={quietNodes[0].id}
            cx={quietNodes[0].cx}
            cy={quietNodes[0].cy}
            fill={palette.inkMuted}
            fillOpacity={0.55}
            r={quietNodes[0].r}
          />
        </Svg>
      </Animated.View>

      <Animated.View style={[layer, quietDLayer]}>
        <Svg {...svg}>
          <Circle
            testID={quietNodes[1].id}
            cx={quietNodes[1].cx}
            cy={quietNodes[1].cy}
            fill={palette.inkMuted}
            fillOpacity={0.55}
            r={quietNodes[1].r}
          />
        </Svg>
      </Animated.View>

      <Animated.View style={[layer, nodeALayer]}>
        <Svg {...svg}>
          <AnimatedCircle
            testID={nodeA.id}
            animatedProps={nodeAFill}
            cx={nodeA.cx}
            cy={nodeA.cy}
            fill={palette.primary}
          />
        </Svg>
      </Animated.View>

      <Animated.View style={[layer, nodeBLayer]}>
        <Svg {...svg}>
          <AnimatedCircle
            testID={nodeB.id}
            animatedProps={nodeBFill}
            cx={nodeB.cx}
            cy={nodeB.cy}
            fill={palette.primary}
          />
        </Svg>
      </Animated.View>
    </View>
  );
}
