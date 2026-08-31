/**
 * The startup coordinator.
 *
 * One place that knows whether the app is ready to show its first real frame,
 * and where that frame should be. The future launch animation reads exactly two
 * things from here, `isReady` and `destination`, and does no storage work of its
 * own.
 *
 * Everything it depends on is already being read for other reasons. Nothing here
 * adds a keychain read, a request or a timer; it observes three hydrations that
 * were happening anyway and combines them.
 */

import { useEffect } from 'react';

import { type ReducedMotion, useReducedMotion } from '@/features/accessibility/reduced-motion';
import { useOnboardingStore } from '@/features/onboarding/store';
import {
  type StartupDestination,
  isStartupReady,
  resolveDestination,
} from '@/features/startup/destination';
import { useSessionStore } from '@/state/session';
import { useTheme } from '@/theme/theme';

export interface Startup {
  /** Every local read the destination depends on has finished. */
  isReady: boolean;
  /** Meaningless until `isReady`. Held rather than navigated to, so a future
   *  launch animation decides when the handoff happens. */
  destination: StartupDestination;
  /**
   * The system Reduce Motion preference, and whether it is known yet.
   *
   * **Deliberately not part of `isReady`.** Where somebody lands has nothing to
   * do with how they feel about motion, and folding this into the destination
   * gate would delay routing for an accessibility read that routing does not
   * need. It rides along because the launch surface wants both, and one hook is
   * a better seam than two for a single screen.
   *
   * A future animation waits on `motion.isHydrated` before it starts moving, and
   * shows a static frame until then.
   */
  motion: ReducedMotion;
}

/**
 * Kicks off hydration once and reports readiness.
 *
 * Called from the root layout. Both stores guard against a second hydrate, so
 * calling this from more than one place is safe, but there is no reason to.
 */
export function useStartup(): Startup {
  const sessionStatus = useSessionStore((s) => s.status);
  const hydrateSession = useSessionStore((s) => s.hydrate);

  const onboardingStatus = useOnboardingStore((s) => s.status);
  const hasSeenOnboarding = useOnboardingStore((s) => s.hasSeenOnboarding);
  const hydrateOnboarding = useOnboardingStore((s) => s.hydrate);

  const { isHydrated: themeHydrated } = useTheme();
  const motion = useReducedMotion();

  useEffect(() => {
    // Fired together rather than in sequence: they are independent keychain
    // reads and serialising them would double the wait for no benefit.
    void hydrateSession();
    void hydrateOnboarding();
  }, [hydrateSession, hydrateOnboarding]);

  return {
    isReady: isStartupReady({
      sessionStatus,
      onboardingHydrated: onboardingStatus === 'ready',
      themeHydrated,
    }),
    destination: resolveDestination(sessionStatus, hasSeenOnboarding),
    motion,
  };
}
