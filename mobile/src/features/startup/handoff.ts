import type { ReducedMotion } from '@/features/accessibility/reduced-motion';

/**
 * How the launch surface gives way to the destination.
 *
 * The last frame of the launch is a finished mark and wordmark on the theme's
 * ground. The first frame of the destination is its own content on the same
 * ground. Getting from one to the other is a navigation problem rather than an
 * animation problem, so it is solved with the native stack transition instead of
 * anything drawn on the launch surface.
 *
 * ### Why not fade the launch screen out
 *
 * Because there is nothing behind it. Fading `LaunchScreen` toward transparent
 * reveals whatever the navigator is painting underneath, which is a bare ground
 * with no content on it, and the destination then appears into that gap. The
 * result is mark, then empty screen, then app. Handing the job to the stack
 * means the destination is the thing that arrives and the launch surface simply
 * stops being on top of it.
 *
 * ### Why `animationTypeForReplace` matters more than the animation
 *
 * `router.replace` defaults to playing the **pop** animation, on the reasoning
 * that a replacement removes the current screen. With the app's ordinary
 * `slide_from_right` that pops the launch surface off to the right, which is the
 * finished logo sliding sideways off the screen. Declaring the replacement a
 * push makes the destination the incoming screen and leaves the launch surface
 * still until it is covered.
 */

export interface HandoffTransition {
  /** Native stack animation for the incoming group. */
  animation: 'fade' | 'none';
  /** Honoured where the platform's native stack supports it. */
  animationDuration?: number;
  /** The destination arrives; the launch surface does not leave. */
  animationTypeForReplace: 'push';
}

/**
 * Short. This is a handoff, not a transition anybody should notice, and the
 * sequence before it has already taken two seconds.
 */
export const HANDOFF_MS = 180;

/**
 * How long the static lockup is held before a reduce-motion launch navigates.
 *
 * Without it, somebody with Reduce Motion on gets the identity for whatever a
 * keychain read takes, which on a warm launch is close to nothing: the brand is
 * technically drawn and effectively never seen. Four hundred milliseconds is
 * long enough to register a mark and a name and short enough that it never
 * becomes a wait.
 *
 * This is a hold, not a slow animation. Nothing moves during it, which is the
 * whole point: the preference asks for no motion, not for less of it.
 *
 * It applies only to an **explicit** preference. An unresolved one still routes
 * immediately, because holding somebody on a launch screen while an
 * accessibility read comes back is the failure this codebase has guarded against
 * from the beginning.
 */
export const REDUCED_MOTION_HOLD_MS = 400;

/**
 * The same rule `LaunchScreen` uses to decide whether to animate at all.
 *
 * An unresolved preference is treated exactly like reduce motion: no transition.
 * Waiting to find out would mean holding somebody on a launch screen until an
 * accessibility read comes back, and that is the wrong trade in both directions.
 * Nothing here can delay routing; it only decides how the swap is drawn.
 */
export function handoffTransition(motion: ReducedMotion): HandoffTransition {
  const mayAnimate = motion.isHydrated && !motion.isReducedMotion;

  return mayAnimate
    ? { animation: 'fade', animationDuration: HANDOFF_MS, animationTypeForReplace: 'push' }
    : { animation: 'none', animationTypeForReplace: 'push' };
}
