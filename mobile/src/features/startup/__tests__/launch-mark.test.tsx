/**
 * The launch handoff.
 *
 * Two things are protected here. Motion is opt-in on evidence: the mark only
 * moves once the system preference has been read and come back negative, and an
 * unresolved preference is never treated as permission. And the mode is decided
 * exactly once, at the moment startup reports ready, so nothing arriving later
 * can swap the presentation or navigate a second time.
 *
 * Nothing asserts elapsed time. The formation runs on the UI thread through
 * Reanimated, so the completion boundary is invoked explicitly instead.
 */

import { act } from '@testing-library/react-native';

import type { ReducedMotion } from '@/features/accessibility/reduced-motion';
import { REDUCED_MOTION_HOLD_MS } from '@/features/startup/handoff';
import { LaunchScreen } from '@/features/startup/LaunchScreen';
import { renderWithProviders } from '@/test-utils/render';

const redirects: string[] = [];

// Navigation is imperative now. `<Redirect>` rendered nothing, so returning one
// tore the launch surface down before the destination had mounted, which the
// recorded review caught as a blank frame between the finished mark and the app.
jest.mock('expo-router', () => ({
  router: {
    replace: (href: string) => {
      redirects.push(href);
    },
  },
}));

/**
 * Stands in for the whole animated sequence so its single completion boundary
 * can be fired on demand. What happens inside it is covered by its own tests;
 * these are about what `LaunchScreen` does with the callback.
 */
let finishFormation: (() => void) | undefined;
/** The size the sequence is asked to draw the mark at, captured so it can be
 *  compared against the still mark the reduced-motion path renders. */
let animatedMarkSize: number | undefined;

jest.mock('@/features/startup/AnimatedLaunchComposition', () => {
  const { View } = jest.requireActual('react-native');
  return {
    AnimatedLaunchComposition: ({
      markSize,
      onComplete,
    }: {
      markSize?: number;
      onComplete?: () => void;
    }) => {
      finishFormation = onComplete;
      animatedMarkSize = markSize;
      return <View testID="animated-sync-mark" />;
    },
  };
});

const UNRESOLVED: ReducedMotion = { isReducedMotion: true, isHydrated: false };
const REDUCED: ReducedMotion = { isReducedMotion: true, isHydrated: true };
const ALLOWED: ReducedMotion = { isReducedMotion: false, isHydrated: true };

function renderLaunch(motion: ReducedMotion, isReady = false, destination = '/welcome') {
  return renderWithProviders(
    <LaunchScreen destination={destination as never} isReady={isReady} motion={motion} />,
  );
}

beforeEach(() => {
  redirects.length = 0;
  finishFormation = undefined;
});

describe('before startup is ready', () => {
  it('shows the static mark whatever the motion preference', async () => {
    for (const motion of [UNRESOLVED, REDUCED, ALLOWED]) {
      const view = await renderLaunch(motion);

      // The formation begins at readiness, not at hydration: starting it early
      // would spend the animation behind the native splash.
      expect(view.queryByTestId('animated-sync-mark')).toBeNull();
      expect(view.getByTestId('sync-route-upper')).toBeTruthy();
    }
  });

  it('never redirects', async () => {
    await renderLaunch(ALLOWED);

    expect(redirects).toEqual([]);
  });

  it('shows the mark rather than an empty surface', async () => {
    const view = await renderLaunch(UNRESOLVED);

    expect(view.getByTestId('launch-surface')).toBeTruthy();
    expect(view.getByTestId('sync-route-lower')).toBeTruthy();
  });
});

describe('ready with an unresolved preference', () => {
  it('hands off immediately rather than waiting to find out', async () => {
    await renderLaunch(UNRESOLVED, true);

    expect(redirects).toEqual(['/welcome']);
  });

  it('mounts no animation', async () => {
    const view = await renderLaunch(UNRESOLVED, true);

    expect(view.queryByTestId('animated-sync-mark')).toBeNull();
  });
});

describe('ready with reduce motion enabled', () => {
  it('holds the lockup before handing off', async () => {
    // The hold this phase added. Reduce motion no longer means the identity is
    // drawn and gone within a keychain read.
    jest.useFakeTimers();
    try {
      await renderLaunch(REDUCED, true);
      expect(redirects).toEqual([]);

      await act(async () => {
        jest.advanceTimersByTime(REDUCED_MOTION_HOLD_MS);
      });
      expect(redirects).toEqual(['/welcome']);
    } finally {
      jest.useRealTimers();
    }
  });

  it('never mounts the formation', async () => {
    const view = await renderLaunch(REDUCED, true);

    expect(view.queryByTestId('animated-sync-mark')).toBeNull();
  });
});

describe('ready with motion allowed', () => {
  it('holds the visual handoff while the mark forms', async () => {
    const view = await renderLaunch(ALLOWED, true);

    expect(view.getByTestId('animated-sync-mark')).toBeTruthy();
    expect(redirects).toEqual([]);
  });

  it('redirects when the formation reports completion', async () => {
    await renderLaunch(ALLOWED, true);
    expect(redirects).toEqual([]);

    await act(async () => finishFormation?.());

    expect(redirects).toEqual(['/welcome']);
  });

  it('had the destination resolved before the hold began', async () => {
    // The hold is visual only. Nothing about the destination is still being
    // worked out while the mark forms.
    await renderLaunch(ALLOWED, true, '/home');

    await act(async () => finishFormation?.());

    expect(redirects).toEqual(['/home']);
  });

  it('cannot navigate twice', async () => {
    await renderLaunch(ALLOWED, true);

    await act(async () => finishFormation?.());
    await act(async () => finishFormation?.());
    await act(async () => finishFormation?.());

    expect(redirects).toEqual(['/welcome']);
  });
});

describe('freezing the decision', () => {
  it('does not start animating when the preference arrives after readiness', async () => {
    // The static mark has already settled by then. Mounting the formation now
    // would snap the logo back to its starting corner.
    const view = await renderLaunch(UNRESOLVED, true);
    expect(redirects).toEqual(['/welcome']);

    await act(async () => {
      view.rerender(<LaunchScreen destination="/welcome" isReady motion={ALLOWED} />);
    });

    expect(view.queryByTestId('animated-sync-mark')).toBeNull();
    expect(redirects).toEqual(['/welcome']);
  });

  it('does not fall back to a static handoff when the preference flips mid-formation', async () => {
    const view = await renderLaunch(ALLOWED, true);
    expect(view.getByTestId('animated-sync-mark')).toBeTruthy();

    await act(async () => {
      view.rerender(<LaunchScreen destination="/welcome" isReady motion={REDUCED} />);
    });

    // Replacing the surface underneath somebody mid-launch is the thing the
    // freeze exists to prevent.
    expect(view.getByTestId('animated-sync-mark')).toBeTruthy();
    expect(redirects).toEqual([]);
  });

  it('keeps the frozen destination even if a new one is passed', async () => {
    const view = await renderLaunch(ALLOWED, true, '/home');

    await act(async () => {
      view.rerender(<LaunchScreen destination="/onboarding" isReady motion={ALLOWED} />);
    });
    await act(async () => finishFormation?.());

    expect(redirects).toEqual(['/home']);
  });
});

describe('teardown', () => {
  it('does no navigation work when completion lands after unmount', async () => {
    const view = await renderLaunch(ALLOWED, true);
    const late = finishFormation;

    await act(async () => {
      view.unmount();
    });
    await act(async () => late?.());

    expect(redirects).toEqual([]);
  });
});

describe('every destination still works', () => {
  it.each(['/home', '/onboarding', '/welcome'])('hands off to %s', async (target) => {
    redirects.length = 0;
    jest.useFakeTimers();
    try {
      await renderLaunch(REDUCED, true, target);
      await act(async () => {
        jest.advanceTimersByTime(REDUCED_MOTION_HOLD_MS);
      });

      expect(redirects).toEqual([target]);
    } finally {
      jest.useRealTimers();
    }
  });

  it.each(['/home', '/onboarding', '/welcome'])(
    'hands off to %s without waiting when the preference is unresolved',
    async (target) => {
      redirects.length = 0;
      await renderLaunch(UNRESOLVED, true, target);

      expect(redirects).toEqual([target]);
    },
  );

  it.each(['/home', '/onboarding', '/welcome'])(
    'hands off to %s after a formation',
    async (target) => {
      redirects.length = 0;
      await renderLaunch(ALLOWED, true, target);
      await act(async () => finishFormation?.());

      expect(redirects).toEqual([target]);
    },
  );
});

describe('the mark at rest', () => {
  it('draws the still mark and the animated one at the same size', async () => {
    // The animation ends on the still mark's exact geometry. A different size
    // either side of the handoff would show as a jump on the last frame.
    const moving = await renderLaunch(ALLOWED, true);
    // Still, and still on screen: the waiting surface is where the mark is
    // drawn without animating.
    const still = await renderLaunch(REDUCED);

    const svg = still.getByLabelText('Sync', { includeHiddenElements: true }).props;

    expect(animatedMarkSize).toBe(86);
    expect(svg.width).toBe(animatedMarkSize);
    expect(moving.getByTestId('animated-sync-mark', { includeHiddenElements: true })).toBeTruthy();
  });
});

describe('the surface during handoff', () => {
  it('keeps the finished mark on screen while navigation resolves', async () => {
    // The blank frame. Navigation is not instant, and whatever is rendered while
    // it resolves is what the eye sees; rendering nothing meant a completed mark
    // vanished and left an empty surface until the destination mounted.
    const view = await renderLaunch(ALLOWED, true);

    await act(async () => finishFormation?.());

    expect(redirects).toEqual(['/welcome']);
    expect(view.getByTestId('launch-surface')).toBeTruthy();
    expect(view.getByTestId('animated-sync-mark')).toBeTruthy();
  });

  it('keeps the still mark on screen for an immediate handoff', async () => {
    const view = await renderLaunch(UNRESOLVED, true);

    expect(redirects).toEqual(['/welcome']);
    expect(view.getByTestId('launch-surface')).toBeTruthy();
    expect(view.getByTestId('sync-route-lower')).toBeTruthy();
  });

  it('keeps the lockup on screen through the reduce-motion handoff', async () => {
    jest.useFakeTimers();
    try {
      const view = await renderLaunch(REDUCED, true);
      await act(async () => {
        jest.advanceTimersByTime(REDUCED_MOTION_HOLD_MS);
      });

      expect(redirects).toEqual(['/welcome']);
      expect(view.getByTestId('launch-surface')).toBeTruthy();
      expect(view.getByTestId('sync-route-lower')).toBeTruthy();
    } finally {
      jest.useRealTimers();
    }
  });

  it('does not swap the animated mark for a static one at the handoff', async () => {
    // The composition holds its own final frame. Unmounting it to show the
    // still mark would replace one mark with another at the worst moment.
    const view = await renderLaunch(ALLOWED, true);

    await act(async () => finishFormation?.());

    expect(view.queryByTestId('launch-network')).toBeNull();
  });
});
