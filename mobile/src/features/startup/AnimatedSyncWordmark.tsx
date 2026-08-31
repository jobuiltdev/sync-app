import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import type { SharedValue } from 'react-native-reanimated';

import { SyncWordmark } from '@/components/brand/SyncWordmark';
import {
  SEGMENT,
  WORDMARK_HEIGHT,
  WORDMARK_RISE,
  eased,
  easeOut,
} from '@/features/startup/launch-timeline';

/**
 * The Sync name arriving under the mark.
 *
 * One element, one fade, one small lift. The mark has just been drawn by two
 * routes travelling in from off screen, and that is the sentence the launch is
 * telling; the wordmark's job is to name the thing afterwards, quietly, and then
 * stop. Revealing it letter by letter, or drawing its strokes, or tracking it
 * open would be a second piece of choreography competing with the first at
 * exactly the moment the first has finished.
 *
 * ### It owns nothing
 *
 * No timing, no shared value of its own, no state. It is handed the same
 * `progress` the network and the mark are driven by and reads one bounded range
 * of it. It is also mounted from the first frame at zero opacity rather than
 * inserted partway through, for the same reason the mark is: a React component
 * appearing mid-sequence is a seam exactly where continuity matters.
 *
 * ### The production wordmark, not a copy
 *
 * The letterforms come from `SyncWordmark`. Nothing here knows what shape an S
 * is, and there is no second copy of those paths to fall out of step with the
 * exported assets.
 */

export interface AnimatedSyncWordmarkProps {
  /** Height in points. Width follows from the wordmark's own aspect ratio. */
  height?: number;
  /**
   * The launch clock, 0 to 1.
   *
   * Optional only so the component can be rendered in isolation for structural
   * tests, where it sits at its starting values.
   */
  progress?: SharedValue<number>;
  /**
   * Whether to skip the reveal and simply be present.
   *
   * Used by the reduced-motion path, which draws the finished composition with
   * no movement at all rather than a faster version of the same movement.
   */
  settled?: boolean;
}

export function AnimatedSyncWordmark({
  height = WORDMARK_HEIGHT,
  progress,
  settled = false,
}: AnimatedSyncWordmarkProps) {
  const standalone = useSharedValue(0);
  const clock = progress ?? standalone;

  const reveal = useAnimatedStyle(() => {
    if (settled) return { opacity: 1, transform: [{ translateY: 0 }] };

    const arrived = eased(clock.value, SEGMENT.wordmarkReveal, easeOut);

    return {
      opacity: arrived,
      // Four points, upward. Enough to read as settling into place rather than
      // switching on, and small enough that nothing appears to travel.
      transform: [{ translateY: WORDMARK_RISE * (1 - arrived) }],
    };
  });

  return (
    // Hidden from assistive technology on purpose. The mark above already
    // carries the accessible name, and two elements both announcing "Sync" is
    // worse than one.
    //
    // One view, carrying both the reveal and the accessibility treatment. A
    // wrapper around it would only exist to be queried.
    <Animated.View
      testID="animated-sync-wordmark"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="none"
      style={reveal}
    >
      <SyncWordmark height={height} accessibilityRole="none" accessibilityLabel="" />
    </Animated.View>
  );
}
