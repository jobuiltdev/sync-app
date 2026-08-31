import { useEffect, useMemo, useRef } from 'react';
import { StyleSheet, View } from 'react-native';
import { Easing, runOnJS, useSharedValue, withTiming } from 'react-native-reanimated';

import { MARK_VIEWBOX } from '@/components/brand/mark-geometry';
import { AnimatedLaunchNetwork } from '@/features/startup/AnimatedLaunchNetwork';
import { AnimatedSyncMark } from '@/features/startup/AnimatedSyncMark';
import { AnimatedSyncWordmark } from '@/features/startup/AnimatedSyncWordmark';
import { NETWORK_ROUTES, NETWORK_VIEWBOX } from '@/features/startup/network-geometry';
import {
  SEQUENCE_MS,
  WORDMARK_HEIGHT,
  flowPlan,
  wordmarkOffset,
} from '@/features/startup/launch-timeline';

/**
 * The whole launch sequence, as one animation.
 *
 * ```
 * 0.00  network arrives
 * 0.16  the indicator sets off, before the network has finished arriving
 * 0.36  the scenery begins receding
 * 0.00  the contextual route's window sets off, carrying both quiet dots
 * 0.03  the upper stream starts its journey, the lower one 60ms behind
 * ....  each stream flows route, connector and mark as one distance
 * 0.76  the travelling dots resolve into the endpoint rings
 * 0.90  the mark is complete and holds
 * 1.00  completion is reported
 * ```
 *
 * ### One value, no stages
 *
 * There used to be a state change here that mounted the mark partway through,
 * plus four delayed timings inside the network and three more inside the mark.
 * That is what the recorded review saw: a network that arrived and paused, a
 * scenery fade that looked like its own animation, and a mark forming in the
 * middle while the network sat outside waiting to be dismissed.
 *
 * Now this component starts a single linear `withTiming` and hands the resulting
 * shared value to both layers, which are **both mounted from the first frame**.
 * There is no React boundary between network and mark, nothing is delayed, and
 * every segment overlaps its neighbour by construction. The ranges live in
 * `launch-timeline`.
 *
 * ### One completion boundary
 *
 * `LaunchScreen` is handed one callback, fired from the master timing's own
 * completion, which is after the hold. It never learns there were two layers.
 */

export interface AnimatedLaunchCompositionProps {
  /** Side of the square the network is drawn into. */
  size: number;
  /** Size of the Sync mark at the centre. */
  markSize: number;
  /** Fired once, after the mark has settled and held. */
  onComplete?: () => void;
}

export function AnimatedLaunchComposition({
  size,
  markSize,
  onComplete,
}: AnimatedLaunchCompositionProps) {
  const progress = useSharedValue(0);

  /**
   * The incoming route's stroke width, expressed in the mark's coordinates.
   *
   * The two live in different systems: a route is 2.5 units against a 320 unit
   * viewBox scaled to `size`, and the mark is drawn against 64 units scaled to
   * `markSize`. Converting through points is what makes "the same thickness on
   * screen" mean anything, and it is what lets the mark start at the width the
   * route hands it rather than at a step change. Two divisions, once per render.
   */
  const primaryWidth = NETWORK_ROUTES.find((route) => route.emphasis === 'primary')!.width;
  const incomingWidth =
    primaryWidth * (size / NETWORK_VIEWBOX) * (MARK_VIEWBOX / markSize);

  /**
   * The two journeys, measured once and shared.
   *
   * Both layers have to be working from the same distances or the stream and
   * the stroke it becomes disagree about where the mark begins.
   */
  const flow = useMemo(() => flowPlan(size, markSize), [size, markSize]);

  // Held in a ref so a parent passing a fresh closure every render cannot
  // restart the sequence, and so the worklet always calls the current one.
  const complete = useRef(onComplete);
  complete.current = onComplete;

  const live = useRef(true);
  const fired = useRef(false);

  useEffect(() => {
    live.current = true;

    const finish = () => {
      // Two guards for two different failures. `live` stops a callback landing
      // after the surface has gone, which would otherwise ask a departed
      // component to navigate. `fired` makes the handoff a one-way door.
      if (!live.current || fired.current) return;
      fired.current = true;
      complete.current?.();
    };

    progress.value = withTiming(
      1,
      // Linear on purpose. Easing lives inside each segment, applied to that
      // segment's own progress; easing the master clock would warp all six at
      // once and pull the overlaps apart.
      { duration: SEQUENCE_MS, easing: Easing.linear },
      () => {
        'worklet';
        // Fired whether or not the timing ran to completion. A cancelled
        // sequence still has to release the launch surface: holding because
        // Reanimated interrupted would strand somebody on a half-finished mark,
        // which is far worse than an early cut. This is also why no fallback
        // timer is needed to guarantee the handoff happens.
        runOnJS(finish)();
      },
    );

    return () => {
      live.current = false;
    };
    // Runs once. A launch surface that re-animates on a re-render is a launch
    // surface that stutters.
  }, [progress]);

  return (
    <View
      testID="animated-launch-composition"
      style={[styles.scene, { width: size, height: size }]}
    >
      <AnimatedLaunchNetwork size={size} markSize={markSize} progress={progress} />

      {/* Centred over the network's reserved middle, and mounted from the start.
          Absolute so the mark's own size can change without moving the scene. */}
      <View style={styles.mark} pointerEvents="none">
        <AnimatedSyncMark
          size={markSize}
          progress={progress}
          incomingWidth={incomingWidth}
          flow={flow}
        />
      </View>

      {/* Under the mark, offset from the same centre. The mark itself does not
          move: the sequence has just spent two seconds putting it where it is,
          and sliding it up to make room would undo that in the last fraction of
          a second. */}
      <View
        style={[styles.mark, { transform: [{ translateY: wordmarkOffset(markSize) }] }]}
        pointerEvents="none"
      >
        <AnimatedSyncWordmark height={WORDMARK_HEIGHT} progress={progress} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  scene: { alignItems: 'center', justifyContent: 'center' },
  mark: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
});
