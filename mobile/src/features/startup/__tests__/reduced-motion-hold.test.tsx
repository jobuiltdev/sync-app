/**
 * The reduce-motion brand hold.
 *
 * Somebody with Reduce Motion on used to get the Sync identity for however long
 * three keychain reads took, which on a warm launch is close to nothing. This
 * gives them a fixed, completely motionless moment instead.
 *
 * Two things are worth protecting and they pull against each other. The hold has
 * to be real, so nothing may navigate before it elapses; and it must never apply
 * to somebody whose preference has not come back, because holding a launch
 * screen on an unresolved accessibility read is the failure this codebase has
 * guarded against from the start.
 */

import { act } from '@testing-library/react-native';

import type { ReducedMotion } from '@/features/accessibility/reduced-motion';
import { REDUCED_MOTION_HOLD_MS, handoffTransition } from '@/features/startup/handoff';
import { LaunchScreen } from '@/features/startup/LaunchScreen';
import { renderWithProviders } from '@/test-utils/render';

const redirects: string[] = [];

jest.mock('expo-router', () => ({
  router: {
    replace: (href: string) => {
      redirects.push(href);
    },
  },
}));

/** Stands in for the animated sequence, which has its own tests. */
jest.mock('@/features/startup/AnimatedLaunchComposition', () => {
  const { View } = jest.requireActual('react-native');
  return {
    AnimatedLaunchComposition: () => <View testID="animated-sync-mark" />,
  };
});

const UNRESOLVED: ReducedMotion = { isReducedMotion: true, isHydrated: false };
const REDUCED: ReducedMotion = { isReducedMotion: true, isHydrated: true };
const ALLOWED: ReducedMotion = { isReducedMotion: false, isHydrated: true };

function renderLaunch(motion: ReducedMotion, isReady = true, destination = '/welcome') {
  return renderWithProviders(
    <LaunchScreen destination={destination as never} isReady={isReady} motion={motion} />,
  );
}

/** Moves the fake clock and lets React flush whatever that caused. */
async function elapse(ms: number) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

/**
 * Counting the hold's own timer rather than every timer in the tree.
 *
 * `jest.getTimerCount()` sees the query client, the providers and React's own
 * scheduling too, so it cannot answer "did the hold leave something pending".
 * These spies watch for the one delay the hold uses and track whether each id
 * it produced was later cleared.
 */
let scheduled: jest.SpyInstance;
let cancelled: jest.SpyInstance;

function holdTimers() {
  const created = scheduled.mock.calls
    .map((call, index) =>
      call[1] === REDUCED_MOTION_HOLD_MS ? scheduled.mock.results[index].value : undefined,
    )
    .filter((id) => id !== undefined);
  const clearedIds = new Set(cancelled.mock.calls.map((call) => call[0]));

  return {
    created: created.length,
    pending: created.filter((id) => !clearedIds.has(id)).length,
  };
}

beforeEach(() => {
  redirects.length = 0;
  jest.useFakeTimers();
  scheduled = jest.spyOn(globalThis, 'setTimeout');
  cancelled = jest.spyOn(globalThis, 'clearTimeout');
});

afterEach(() => {
  scheduled.mockRestore();
  cancelled.mockRestore();
  jest.useRealTimers();
});

describe('the hold', () => {
  it('shows the finished lockup', async () => {
    const view = await renderLaunch(REDUCED);

    expect(view.getByTestId('launch-lockup')).toBeTruthy();
    // The mark and the name, both drawn at rest.
    expect(view.getByTestId('sync-route-upper')).toBeTruthy();
    expect(view.getByTestId('sync-route-lower')).toBeTruthy();
    expect(view.getByTestId('letter-s')).toBeTruthy();
    expect(view.getByTestId('letter-c')).toBeTruthy();
  });

  it('leaves the network out of it', async () => {
    // Standing still, the network is a diagram around a logo rather than a
    // composition going anywhere.
    const view = await renderLaunch(REDUCED);

    expect(view.queryByTestId('launch-network')).toBeNull();
    expect(view.queryByTestId('route-context')).toBeNull();
  });

  it('mounts no animation', async () => {
    const view = await renderLaunch(REDUCED);

    expect(view.queryByTestId('animated-sync-mark')).toBeNull();
    expect(view.queryByTestId('animated-launch-composition')).toBeNull();
  });

  it('navigates nowhere before the hold elapses', async () => {
    await renderLaunch(REDUCED);
    expect(redirects).toEqual([]);

    await elapse(REDUCED_MOTION_HOLD_MS - 1);

    expect(redirects).toEqual([]);
  });

  it('navigates once the hold elapses', async () => {
    await renderLaunch(REDUCED);

    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(redirects).toEqual(['/welcome']);
  });

  it('navigates exactly once however long the clock runs', async () => {
    await renderLaunch(REDUCED);

    await elapse(REDUCED_MOTION_HOLD_MS * 6);

    expect(redirects).toEqual(['/welcome']);
  });

  it('holds for four hundred milliseconds', () => {
    // Long enough to read a mark and a name, short enough never to be a wait.
    expect(REDUCED_MOTION_HOLD_MS).toBe(400);
  });

  it('keeps the lockup on screen after navigating', async () => {
    // Navigation is not instant. Whatever is rendered while it resolves is what
    // the eye sees, and rendering nothing was the blank frame this app already
    // fixed once.
    const view = await renderLaunch(REDUCED);
    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(view.getByTestId('launch-surface')).toBeTruthy();
    expect(view.getByTestId('launch-lockup')).toBeTruthy();
  });
});

describe('who does not get held', () => {
  it('routes an unresolved preference immediately', async () => {
    await renderLaunch(UNRESOLVED);

    expect(redirects).toEqual(['/welcome']);
  });

  it('starts no hold at all for an unresolved preference', async () => {
    await renderLaunch(UNRESOLVED);

    expect(holdTimers().created).toBe(0);
  });

  it('still runs the full sequence when motion is allowed', async () => {
    const view = await renderLaunch(ALLOWED);

    expect(view.getByTestId('animated-sync-mark')).toBeTruthy();
    expect(redirects).toEqual([]);
  });

  it('never lets the hold navigate an animated launch', async () => {
    // The animated path reports completion itself. If the hold reached it, a
    // launch would navigate out from under a sequence still playing.
    await renderLaunch(ALLOWED);

    await elapse(REDUCED_MOTION_HOLD_MS * 4);

    expect(redirects).toEqual([]);
  });

  it('waits while startup has not resolved', async () => {
    const view = await renderLaunch(REDUCED, false);

    await elapse(REDUCED_MOTION_HOLD_MS * 2);

    expect(redirects).toEqual([]);
    expect(view.getByTestId('launch-surface')).toBeTruthy();
  });
});

describe('the decision is frozen', () => {
  it('does not restart the hold on a re-render', async () => {
    const view = await renderLaunch(REDUCED);

    await elapse(300);
    await act(async () => {
      view.rerender(
        <LaunchScreen destination={'/welcome' as never} isReady motion={REDUCED} />,
      );
    });
    await elapse(100);

    // 400ms of clock has passed in total. A restart would still be waiting.
    expect(redirects).toEqual(['/welcome']);
  });

  it('ignores a preference that flips mid-hold', async () => {
    // Replacing the surface underneath somebody part way through is the thing
    // the freeze exists to prevent, and it applies to this phase too.
    const view = await renderLaunch(REDUCED);

    await act(async () => {
      view.rerender(
        <LaunchScreen destination={'/welcome' as never} isReady motion={ALLOWED} />,
      );
    });

    expect(view.getByTestId('launch-lockup')).toBeTruthy();
    expect(view.queryByTestId('animated-sync-mark')).toBeNull();

    await elapse(REDUCED_MOTION_HOLD_MS);
    expect(redirects).toEqual(['/welcome']);
  });

  it('keeps the frozen destination even if a new one arrives', async () => {
    const view = await renderLaunch(REDUCED, true, '/home');

    await act(async () => {
      view.rerender(
        <LaunchScreen destination={'/onboarding' as never} isReady motion={REDUCED} />,
      );
    });
    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(redirects).toEqual(['/home']);
  });

  it.each(['/home', '/onboarding', '/welcome'])('holds then routes to %s', async (target) => {
    await renderLaunch(REDUCED, true, target);

    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(redirects).toEqual([target]);
  });
});

describe('teardown', () => {
  it('clears the pending hold on unmount', async () => {
    const view = await renderLaunch(REDUCED);
    expect(holdTimers().pending).toBe(1);

    await act(async () => {
      view.unmount();
    });

    expect(holdTimers().pending).toBe(0);
  });

  it('navigates nowhere when the hold would have fired after unmount', async () => {
    const view = await renderLaunch(REDUCED);

    await act(async () => {
      view.unmount();
    });
    await elapse(REDUCED_MOTION_HOLD_MS * 2);

    expect(redirects).toEqual([]);
  });

  it('schedules exactly one timeout for the hold', async () => {
    // One timeout, not a chain of them and not a repeating one.
    await renderLaunch(REDUCED);

    expect(holdTimers().created).toBe(1);
    expect(holdTimers().pending).toBe(1);
  });

  it('schedules no further work once the hold has fired', async () => {
    await renderLaunch(REDUCED);

    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(holdTimers().created).toBe(1);
  });

  it('does not reschedule the hold when the phase advances', async () => {
    // Entering `handoff` tears the effect down, which clears the timer it set.
    // A second one appearing here would be a chained delay.
    const view = await renderLaunch(REDUCED);
    await elapse(REDUCED_MOTION_HOLD_MS);
    await elapse(REDUCED_MOTION_HOLD_MS);

    expect(holdTimers().created).toBe(1);
    expect(view.getByTestId('launch-lockup')).toBeTruthy();
  });
});

describe('the root transition stays unanimated', () => {
  it('gives reduce motion no transition', () => {
    // The hold is motionless and so is the swap that follows it.
    expect(handoffTransition(REDUCED).animation).toBe('none');
    expect(handoffTransition(REDUCED).animationDuration).toBeUndefined();
  });

  it('gives an unresolved preference no transition either', () => {
    expect(handoffTransition(UNRESOLVED).animation).toBe('none');
  });
});
