/**
 * Reading and advancing the introduction.
 *
 * A thin view over `onboarding/store`, which owns the single hydration
 * lifecycle. This file exists so call sites keep a small, obvious API and never
 * have to know the store is Zustand.
 */

import { useOnboardingStore } from '@/features/onboarding/store';

export type OnboardingState = 'loading' | 'needed' | 'seen';

export function useOnboarding(): {
  state: OnboardingState;
  complete: () => Promise<void>;
} {
  const status = useOnboardingStore((s) => s.status);
  const hasSeen = useOnboardingStore((s) => s.hasSeenOnboarding);
  const complete = useOnboardingStore((s) => s.complete);

  return {
    state: status === 'loading' ? 'loading' : hasSeen ? 'seen' : 'needed',
    complete,
  };
}

/** Clears the flag. Exposed for tests and for anybody who wants to see the
 *  introduction again from a debug build, not wired to a user-facing control. */
export async function resetOnboarding(): Promise<void> {
  await useOnboardingStore.getState().reset();
}
