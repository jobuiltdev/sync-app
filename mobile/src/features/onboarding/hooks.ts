/**
 * Whether the introduction has been seen.
 *
 * Persisted beside the theme preference, in the keychain, for the same reason:
 * it is the storage this app already has and one boolean does not justify a
 * second one.
 *
 * Failing open is deliberate. If the read fails the carousel is skipped rather
 * than shown, because showing somebody the introduction again every launch is a
 * worse failure than never showing it at all.
 */

import { useCallback, useEffect, useState } from 'react';

import { ONBOARDING_STORAGE_KEY } from '@/features/onboarding/slides';
import { secureStorage } from '@/lib/secure-storage';

export type OnboardingState = 'loading' | 'needed' | 'seen';

export function useOnboarding() {
  const [state, setState] = useState<OnboardingState>('loading');

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const stored = await secureStorage.get(ONBOARDING_STORAGE_KEY);
      if (cancelled) return;
      setState(stored === 'true' ? 'seen' : 'needed');
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const complete = useCallback(async () => {
    // Marked before navigating, so a person who force-quits on the last slide
    // does not get the introduction again.
    setState('seen');
    await secureStorage.set(ONBOARDING_STORAGE_KEY, 'true');
  }, []);

  return { state, complete };
}

/** Clears the flag. Exposed for tests and for anybody who wants to see it
 *  again from a debug build, not wired to a user-facing control. */
export async function resetOnboarding(): Promise<void> {
  await secureStorage.remove(ONBOARDING_STORAGE_KEY);
}
