import { View } from 'react-native';
import Animated, {
  useAnimatedProps,
  useSharedValue,
} from 'react-native-reanimated';
import type { SharedValue } from 'react-native-reanimated';
import Svg, { Circle, Path } from 'react-native-svg';

import {
  MARK_LOWER_LENGTH,
  MARK_UPPER_LENGTH,
  MARK_VIEWBOX,
  NODE_LOWER,
  NODE_STROKE_WIDTH,
  NODE_UPPER,
  ROUTE_LOWER_REVEAL_PATH,
  ROUTE_STROKE_WIDTH,
  ROUTE_UPPER_PATH,
} from '@/components/brand/mark-geometry';
import {
  SEGMENT,
  dashWindow,
  eased,
  easeInOut,
  easeOut,
} from '@/features/startup/launch-timeline';
import type { FlowPlan } from '@/features/startup/launch-timeline';
import { usePalette } from '@/theme/theme';

const AnimatedPath = Animated.createAnimatedComponent(Path);
const AnimatedCircle = Animated.createAnimatedComponent(Circle);

/**
 * The Sync mark being drawn by the routes that arrive at it.
 *
 * This does not fade in, and it does not move. The mark sits at its exact final
 * position from the first frame and is revealed by trimming its stroke, growing
 * outward from the two points where the incoming network routes make contact.
 *
 * ### Why the crossfade had to go
 *
 * The previous version slid both complete paths in from the side and raised
 * their opacity while the network routes lowered theirs. Every number in it was
 * right and it still read as the network disappearing and a logo appearing,
 * because that is literally what it was: two whole objects swapping places. No
 * amount of retiming fixes that, because at no point was any single stroke ever
 * shared between the two.
 *
 * Now there is one stroke. Each stream is a window travelling a single distance
 * that runs through its network route, through a connector and into one of these
 * paths, and the mark's share is simply the last leg of that journey. The head
 * does not stop or slow at either boundary, and no opacity is crossed anywhere
 * along it, so the eye follows one continuous line from off screen into the S.
 *
 * The difference from the mark's point of view is that the reveal is no longer
 * its own eased animation between two numbers. It is a distance handed to it by
 * the flow, which is why `flow` is a prop rather than something worked out here:
 * the network and the mark have to be measuring the same journey or the stream
 * arrives at a stroke that has already started drawing itself.
 *
 * ### Gaining weight
 *
 * A network route is 2.5 units against a 320 unit viewBox; the mark's stroke is
 * 7 against 64. The incoming line is roughly a quarter of the final weight, so
 * the mark route starts at the incoming width and thickens to the canonical one
 * as it draws. Landing on the full weight immediately would put a step change in
 * the middle of a stroke that is meant to be continuous.
 *
 * The last frame is the static mark exactly: dash offsets at zero, stroke at
 * `ROUTE_STROKE_WIDTH`, rings at their canonical radius and width.
 */

export interface AnimatedSyncMarkProps {
  size?: number;
  color?: string;
  /**
   * The launch clock, 0 to 1.
   *
   * Optional only so the mark can be rendered in isolation for structural tests,
   * where it sits at its starting values. In the app it is always the
   * composition's single shared value.
   */
  progress?: SharedValue<number>;
  /**
   * The width of the incoming network stroke, already converted into this
   * mark's 64 unit coordinate system by the composition.
   *
   * Defaults to the canonical width, so a mark rendered without a launch behind
   * it is simply the mark.
   */
  incomingWidth?: number;
  /**
   * Each stream's whole journey in points, from the composition.
   *
   * Without it this mark has no way to know how far away the flow starts, and
   * would have to guess when its own leg begins. Defaults to a journey that is
   * nothing but the mark, which is what an isolated render should be.
   */
  flow?: Record<'upper' | 'lower', FlowPlan>;
}

export function AnimatedSyncMark({
  size = 76,
  color,
  progress,
  incomingWidth = ROUTE_STROKE_WIDTH,
  flow,
}: AnimatedSyncMarkProps) {
  const palette = usePalette();
  const stroke = color ?? palette.primary;

  const standalone = useSharedValue(0);
  const clock = progress ?? standalone;

  /** Points per mark unit, which is how the flow distance is converted. */
  const markUnit = size / MARK_VIEWBOX;
  const upperPlan: FlowPlan = flow?.upper ?? {
    route: 0,
    connector: 0,
    mark: MARK_UPPER_LENGTH * markUnit,
    total: MARK_UPPER_LENGTH * markUnit,
    lag: 0,
  };
  const lowerPlan: FlowPlan = flow?.lower ?? {
    route: 0,
    connector: 0,
    mark: MARK_LOWER_LENGTH * markUnit,
    total: MARK_LOWER_LENGTH * markUnit,
    lag: 0,
  };

  // Both routes are the last leg of their stream's journey. The tail is pinned
  // at the start rather than following the head, which is the one difference
  // from the legs behind them: what the stream lays down here stays down.
  const upperRoute = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.upperFlow, easeInOut) * upperPlan.total;
    const into = flown - upperPlan.route - upperPlan.connector;
    const drawn = into < 0 ? 0 : into > upperPlan.mark ? upperPlan.mark : into;
    const weight = drawn / upperPlan.mark;

    return {
      ...dashWindow(drawn / markUnit, 0, MARK_UPPER_LENGTH),
      strokeWidth: incomingWidth + (ROUTE_STROKE_WIDTH - incomingWidth) * weight,
    };
  });

  const lowerRoute = useAnimatedProps(() => {
    const flown = eased(clock.value, SEGMENT.lowerFlow, easeInOut) * lowerPlan.total;
    const into = flown - lowerPlan.route - lowerPlan.connector;
    const drawn = into < 0 ? 0 : into > lowerPlan.mark ? lowerPlan.mark : into;
    const weight = drawn / lowerPlan.mark;

    return {
      ...dashWindow(drawn / markUnit, 0, MARK_LOWER_LENGTH),
      strokeWidth: incomingWidth + (ROUTE_STROKE_WIDTH - incomingWidth) * weight,
    };
  });

  // The rings grow rather than fade. A complete ring appearing at full size is
  // the same swap this revision removed, one object smaller.
  const upperRing = useAnimatedProps(() => {
    const grown = eased(clock.value, SEGMENT.ringResolve, easeOut);

    return {
      r: NODE_UPPER.r * grown,
      strokeWidth: NODE_STROKE_WIDTH * grown,
    };
  });

  const lowerRing = useAnimatedProps(() => {
    const grown = eased(clock.value, SEGMENT.ringResolve, easeOut);

    return {
      r: NODE_LOWER.r * grown,
      strokeWidth: NODE_STROKE_WIDTH * grown,
    };
  });

  const svg = {
    width: size,
    height: size,
    viewBox: `0 0 ${MARK_VIEWBOX} ${MARK_VIEWBOX}`,
    fill: 'none',
  } as const;

  return (
    <View
      testID="animated-sync-mark"
      accessible
      accessibilityRole="image"
      accessibilityLabel="Sync"
      style={{ width: size, height: size }}
    >
      {/* One Svg, not three. Nothing here translates any more, so the layers
          that existed to carry transforms have no reason to. */}
      <Svg {...svg} pointerEvents="none">
        <AnimatedPath
          testID="sync-route-upper"
          animatedProps={upperRoute}
          d={ROUTE_UPPER_PATH}
          stroke={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* The reversed twin of the canonical lower path. Same curve, authored
            from the outer end so the reveal starts where the network route
            arrives rather than in the middle of the S. */}
        <AnimatedPath
          testID="sync-route-lower"
          animatedProps={lowerRoute}
          d={ROUTE_LOWER_REVEAL_PATH}
          stroke={stroke}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <AnimatedCircle
          testID="sync-node-upper"
          animatedProps={upperRing}
          cx={NODE_UPPER.cx}
          cy={NODE_UPPER.cy}
          stroke={stroke}
        />
        <AnimatedCircle
          testID="sync-node-lower"
          animatedProps={lowerRing}
          cx={NODE_LOWER.cx}
          cy={NODE_LOWER.cy}
          stroke={stroke}
        />
      </Svg>
    </View>
  );
}
