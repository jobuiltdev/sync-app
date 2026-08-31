import { useCallback, useEffect, useRef, useState } from 'react';
import { router } from 'expo-router';
import { StyleSheet, View, useWindowDimensions } from 'react-native';

import { SyncMark } from '@/components/brand/SyncMark';
import { SyncWordmark } from '@/components/brand/SyncWordmark';
import type { ReducedMotion } from '@/features/accessibility/reduced-motion';
import { AnimatedLaunchComposition } from '@/features/startup/AnimatedLaunchComposition';
import { LaunchNetwork } from '@/features/startup/LaunchNetwork';
import type { StartupDestination } from '@/features/startup/destination';
import { REDUCED_MOTION_HOLD_MS } from '@/features/startup/handoff';
import { WORDMARK_HEIGHT, wordmarkOffset } from '@/features/startup/launch-timeline';
import { usePalette } from '@/theme/theme';

interface LaunchScreenProps {
  destination: StartupDestination;
  isReady: boolean;
  /**
   * Passed in rather than read here, so this component stays a presentation
   * decision and the accessibility subscription keeps one owner.
   */
  motion: ReducedMotion;
}

/**
 * One launch, one decision.
 *
 * ### The phases
 *
 * ```
 * waiting ──ready & motion allowed──▶ forming ──animation done──▶ handoff
 *    └──────ready & anything else───────────────────────────────▶ handoff
 * ```
 *
 * `waiting` is the only phase that reads `isReady` or `motion`. The instant
 * startup reports ready, the mode is chosen and **frozen**, along with the
 * destination. Nothing afterwards can change either.
 *
 * That freeze is the point of this component. Without it a preference arriving
 * a few milliseconds late would swap a settled static mark for an off-position
 * animated one, which reads as the logo jumping backwards; an animation could
 * mount after navigation was already allowed; and a person changing an
 * accessibility setting mid-launch would have the surface replaced underneath
 * them. All three are the same bug, and freezing on the first ready is the
 * cheapest way to make all three impossible.
 *
 * ### What motion may and may not affect
 *
 * It decides whether the mark moves and, when it does, how long the *visual*
 * handoff waits. It never touches `isReady`, never touches which destination is
 * chosen, and never delays a launch where the preference has not arrived: an
 * unresolved preference hands off immediately rather than waiting to find out,
 * because waiting on an accessibility read to be let into an app is the wrong
 * trade in both directions.
 */
type LaunchPhase =
  /** Startup has not resolved. Static mark, nothing decided. */
  | { kind: 'waiting' }
  /** Motion was allowed at the moment of readiness. Mark is forming; the
   *  destination is already known and simply not used yet. */
  | { kind: 'forming'; destination: StartupDestination }
  /**
   * Reduce motion was on at the moment of readiness. The finished lockup is on
   * screen and completely still, and stays that way for `REDUCED_MOTION_HOLD_MS`
   * before anything navigates.
   *
   * This is the only phase with a timer, and it is a hold rather than an
   * animation: nothing about the surface changes while it runs.
   */
  | { kind: 'holding'; destination: StartupDestination }
  /**
   * Go. The surface stays on screen through this phase.
   *
   * `presentation` records how the launch was drawn, so the handoff keeps
   * showing the same thing rather than swapping to a different one at the exact
   * moment navigation starts.
   */
  | {
      kind: 'handoff';
      destination: StartupDestination;
      presentation: Presentation;
    };

/**
 * What the surface is drawing.
 *
 * `still` is the waiting state and the unresolved-preference handoff: the whole
 * scene, network included, because nothing has been decided yet. `lockup` is the
 * reduce-motion presentation, which is the mark and the name and nothing else.
 */
type Presentation = 'animated' | 'lockup' | 'still';

export function LaunchScreen({ destination, isReady, motion }: LaunchScreenProps) {
  const [phase, setPhase] = useState<LaunchPhase>({ kind: 'waiting' });

  /** Navigation has been asked for. Never asked for twice. */
  const navigated = useRef(false);
  /** Cleared on unmount, so a completion callback that lands afterwards does
   *  nothing at all rather than trying to advance a departed component. */
  const live = useRef(true);

  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);

  const onFormed = useCallback(() => {
    if (!live.current) return;
    setPhase((current) =>
      // Only `forming` can advance this way, so a second call, or one that
      // arrives after an unmount-and-remount, changes nothing.
      current.kind === 'forming'
        ? { kind: 'handoff', destination: current.destination, presentation: 'animated' }
        : current,
    );
  }, []);

  // Decided during render rather than in an effect, so there is no painted
  // frame in which readiness is known but the presentation has not caught up.
  // React re-renders immediately on a state update made here, without painting
  // the discarded pass. The `waiting` guard makes it a one-time transition.
  if (phase.kind === 'waiting' && isReady) {
    const mayAnimate = motion.isHydrated && !motion.isReducedMotion;
    // The destination travels into the phase. Capturing it here is what makes
    // "resolved before the hold begins" a property of the type rather than a
    // promise in a comment.
    // Three outcomes, decided once and frozen. An explicit preference for less
    // motion earns the hold; an unresolved one is never made to wait for an
    // accessibility read it may not get.
    if (mayAnimate) {
      setPhase({ kind: 'forming', destination });
    } else if (motion.isHydrated) {
      setPhase({ kind: 'holding', destination });
    } else {
      setPhase({ kind: 'handoff', destination, presentation: 'still' });
    }
  }

  // The hold. Started from an effect rather than during render, so it begins
  // once the static lockup is actually on screen rather than when the decision
  // to show it was made.
  //
  // Keyed on the phase *kind*, so a re-render, or a preference arriving late,
  // cannot restart it: `holding` is entered once and the timer with it.
  useEffect(() => {
    if (phase.kind !== 'holding') return undefined;

    const timer = setTimeout(() => {
      if (!live.current) return;
      setPhase((current) =>
        current.kind === 'holding'
          ? { kind: 'handoff', destination: current.destination, presentation: 'lockup' }
          : current,
      );
    }, REDUCED_MOTION_HOLD_MS);

    // Cleared on unmount and on any phase change, so nothing is left pending
    // and nothing fires into a component that has gone.
    return () => clearTimeout(timer);
  }, [phase.kind]);

  // Navigation is imperative rather than a rendered `Redirect`, and this is the
  // whole reason. `<Redirect>` renders nothing, so returning one meant the
  // launch surface was torn down the instant the mark finished and the
  // destination had not mounted yet. The recording caught that as a blank frame
  // between a completed mark and the app. Now the finished surface stays
  // rendered and simply gets replaced when the next route is ready.
  useEffect(() => {
    if (phase.kind !== 'handoff' || navigated.current) return;
    // A ref rather than state: this must happen exactly once, and it must not
    // cause a render of its own.
    navigated.current = true;
    router.replace(phase.destination);
  }, [phase]);

  // The presentation carries through the handoff unchanged. The animated
  // composition in particular stays mounted holding its final frame, because
  // unmounting it to show a static mark would swap one mark for another at the
  // worst possible moment.
  const presentation: Presentation =
    phase.kind === 'forming'
      ? 'animated'
      : phase.kind === 'holding'
        ? 'lockup'
        : phase.kind === 'handoff'
          ? phase.presentation
          : 'still';

  return <LaunchSurface presentation={presentation} onFormed={onFormed} />;
}

/** How much of the shorter screen edge the scene occupies, and the ceiling it
 *  will not grow past. Tuned so the composition reads the same on a small
 *  iPhone as on a large Android instead of turning into wallpaper. */
const SCENE_RATIO = 0.86;
const SCENE_MAX = 380;

/**
 * The mark, in points.
 *
 * Raised from 76, then eased back to 86 once the network around it was thinned
 * out. At 76 the mark read as a label on a diagram; at 92, against 2.5 unit
 * routes and small filled dots, it was heavier than it needed to be to dominate.
 * It remains the strongest element on the surface with room to spare inside the
 * 70 unit reserved centre.
 */
const MARK_SIZE = 86;

function LaunchSurface({
  presentation,
  onFormed,
}: {
  presentation: Presentation;
  onFormed: () => void;
}) {
  const palette = usePalette();
  const { width, height } = useWindowDimensions();

  // Square, from the shorter edge, so a node can never be pushed off a narrow
  // screen or a short one. The scene scales; the composition does not change.
  const scene = Math.min(Math.min(width, height) * SCENE_RATIO, SCENE_MAX);

  return (
    <View
      testID="launch-surface"
      style={[styles.surface, { backgroundColor: palette.ground }]}
    >
      {presentation === 'animated' ? (
        // The full sequence: network in, indicator across, network out, mark
        // forms. It reports completion once, after the mark has finished.
        <AnimatedLaunchComposition size={scene} markSize={MARK_SIZE} onComplete={onFormed} />
      ) : (
        <View
          testID={presentation === 'lockup' ? 'launch-lockup' : 'launch-scene'}
          style={[styles.scene, { width: scene, height: scene }]}
        >
          {/* The network is scenery for a composition that is going to move.
              Standing still it is just a diagram around a logo, so the
              reduce-motion hold shows the lockup on its own. */}
          {presentation === 'still' ? <LaunchNetwork size={scene} /> : null}

          {/* Centred over the network's reserved middle. Absolute rather than
              in flow so the mark's own size can change without moving it. */}
          <View style={styles.mark} pointerEvents="none">
            <SyncMark size={MARK_SIZE} />
          </View>

          {/* The same lockup the animation finishes on, drawn at rest. Reduce
              motion gets the finished composition rather than a quicker version
              of the movement. */}
          <View
            style={[styles.mark, { transform: [{ translateY: wordmarkOffset(MARK_SIZE) }] }]}
            pointerEvents="none"
          >
            <SyncWordmark
              height={WORDMARK_HEIGHT}
              accessibilityRole="none"
              accessibilityLabel=""
            />
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scene: { alignItems: 'center', justifyContent: 'center' },
  mark: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },
});
