/**
 * Whether the introduction has been seen.
 *
 * A store rather than a hook with its own effect. The previous version held
 * local state and ran its own `useEffect` in every component that called it,
 * which meant two independent state machines and two keychain reads for one
 * boolean. Marking it complete in one did not update the other. Nothing broke,
 * because the two never rendered at once, but a launch coordinator would have
 * been a third reader and the divergence would have started to matter.
 *
 * Persisted beside the session and theme keys, in the keychain, because that is
 * the storage this app already has and one boolean does not justify a second.
 *
 * Failing open is deliberate. If the read fails the carousel is skipped rather
 * than shown: seeing the introduction again on every launch is a worse failure
 * than never seeing it.
 */

import { create } from 'zustand';

import { ONBOARDING_STORAGE_KEY } from '@/features/onboarding/slides';
import { secureStorage } from '@/lib/secure-storage';

export type OnboardingStatus = 'loading' | 'ready';

interface OnboardingState {
  status: OnboardingStatus;
  hasSeenOnboarding: boolean;

  /** Reads the flag once. Safe to call from more than one place: the second
   *  call is a no-op rather than a second keychain read. */
  hydrate: () => Promise<void>;
  complete: () => Promise<void>;
  reset: () => Promise<void>;
}

/** Guards against a double hydrate from concurrent mounts. Kept outside the
 *  store so it is not part of the observable state. */
let hydrating: Promise<void> | null = null;

export const useOnboardingStore = create<OnboardingState>((set) => ({
  status: 'loading',
  hasSeenOnboarding: false,

  hydrate: async () => {
    if (hydrating) return hydrating;

    hydrating = (async () => {
      const stored = await secureStorage.get(ONBOARDING_STORAGE_KEY);
      set({ hasSeenOnboarding: stored === 'true', status: 'ready' });
    })();

    return hydrating;
  },

  complete: async () => {
    // In memory first, so a person who force-quits on the last slide does not
    // get the introduction again, and so the change is visible immediately
    // rather than a keychain round trip later.
    set({ hasSeenOnboarding: true, status: 'ready' });
    await secureStorage.set(ONBOARDING_STORAGE_KEY, 'true');
  },

  reset: async () => {
    set({ hasSeenOnboarding: false, status: 'ready' });
    await secureStorage.remove(ONBOARDING_STORAGE_KEY);
  },
}));

/** Test seam. Lets a suite start from a clean hydration lifecycle rather than
 *  inheriting the guard from a previous test. */
export function resetOnboardingHydration(): void {
  hydrating = null;
  useOnboardingStore.setState({ status: 'loading', hasSeenOnboarding: false });
}
