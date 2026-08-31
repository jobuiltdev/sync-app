/**
 * Where a launch ends up.
 *
 * A pure function, deliberately. The destination is the one decision the whole
 * startup sequence exists to make, and keeping it free of hooks, storage and
 * navigation means it can be exhaustively tested without rendering anything or
 * mocking a router.
 *
 * The priority is the one the app has always used, and it is not arbitrary:
 * a signed-in person has self-evidently seen the introduction, so authentication
 * is checked first and the onboarding flag is not even consulted.
 */

import type { SessionStatus } from '@/state/session';

/** The three places a cold start can land. Typed as literals rather than as the
 *  router's Href so this module stays independent of expo-router. */
export type StartupDestination = '/home' | '/onboarding' | '/welcome';

export function resolveDestination(
  sessionStatus: SessionStatus,
  hasSeenOnboarding: boolean,
): StartupDestination {
  if (sessionStatus === 'authenticated') return '/home';

  return hasSeenOnboarding ? '/welcome' : '/onboarding';
}

/**
 * Whether every local read the destination depends on has finished.
 *
 * Three keychain reads and nothing else. **No network call is part of this.**
 * Session restoration is a token read, not a request: whether that token is
 * still valid is settled lazily by the first authenticated call, so launch never
 * waits on a server and never depends on connection quality.
 *
 * The theme is included because it decides the colour of the first frame, and a
 * launch surface that repaints halfway through is worse than one that appears a
 * few milliseconds later.
 */
export function isStartupReady(flags: {
  sessionStatus: SessionStatus;
  onboardingHydrated: boolean;
  themeHydrated: boolean;
}): boolean {
  return (
    flags.sessionStatus !== 'loading' && flags.onboardingHydrated && flags.themeHydrated
  );
}
