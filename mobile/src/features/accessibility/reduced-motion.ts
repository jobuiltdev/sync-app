/**
 * The system Reduce Motion preference.
 *
 * Read from the operating system rather than offered as a Sync setting. Somebody
 * who has turned motion down has done it once, for every app on the phone, and
 * asking them to find a second switch buried in our settings is asking them to
 * do the same work twice.
 *
 * Reduce Motion is not a stylistic preference. It is an accessibility setting
 * that exists because motion causes nausea, dizziness and migraines in people
 * with vestibular conditions. A launch animation that ignores it is not merely
 * unpolished; it can make somebody physically unwell before they reach the app.
 *
 * ### Why the answer is three-valued
 *
 * `isReduceMotionEnabled()` is asynchronous, so for the first moments of a cold
 * start the preference is genuinely *unknown*. An earlier version of this hook
 * collapsed that into `false`, which is the wrong failure mode: somebody who had
 * asked for less motion would have received the opening frames of a cinematic
 * sequence before their setting resolved, and those frames are exactly the ones
 * that do the harm.
 *
 * So unknown is reported as unknown. `isHydrated` is what a caller waits on
 * before starting motion, and the correct behaviour while it is false is to show
 * a static frame rather than to guess.
 *
 * The subscription matters as much as the initial read: the preference can be
 * changed from Control Centre or Settings while Sync is backgrounded, and a
 * value captured once at launch would be wrong for the rest of the session.
 */

import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

export interface ReducedMotion {
  /** Whether the OS has asked for reduced motion. Only meaningful once
   *  `isHydrated`; before then it is the safe default rather than an answer. */
  isReducedMotion: boolean;
  /** Whether the preference has actually been read. Motion must not begin
   *  until this is true. */
  isHydrated: boolean;
}

export function useReducedMotion(): ReducedMotion {
  const [state, setState] = useState<ReducedMotion>({
    // Defaults to "reduce motion" while unknown, so that a caller which ignores
    // `isHydrated` still errs towards the accessible behaviour rather than the
    // harmful one. Callers should wait, but the default should not punish them
    // for forgetting.
    isReducedMotion: true,
    isHydrated: false,
  });

  useEffect(() => {
    let cancelled = false;

    void AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => {
        if (!cancelled) setState({ isReducedMotion: enabled, isHydrated: true });
      })
      .catch(() => {
        // A platform that cannot answer is treated as resolved-and-not-reduced:
        // holding a launch surface static for ever because an API is missing
        // would be a worse outcome than playing the animation.
        if (!cancelled) setState({ isReducedMotion: false, isHydrated: true });
      });

    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      (enabled: boolean) => setState({ isReducedMotion: enabled, isHydrated: true }),
    );

    return () => {
      cancelled = true;
      subscription.remove();
    };
  }, []);

  return state;
}
