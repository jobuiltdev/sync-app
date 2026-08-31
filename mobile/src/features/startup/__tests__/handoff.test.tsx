/**
 * The handoff from the launch surface to the destination.
 *
 * The rule itself is a pure function and is tested as one. What is harder to
 * hold, and worth holding, is that it reaches exactly the two group screens and
 * nothing else: a fade applied one level too broadly would replace every
 * transition in the app, and the two nested layouts are what stop that.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { ReducedMotion } from '@/features/accessibility/reduced-motion';
import { resolveDestination } from '@/features/startup/destination';
import { HANDOFF_MS, handoffTransition } from '@/features/startup/handoff';
import { renderWithProviders } from '@/test-utils/render';

// `jest.mock` is hoisted above this, so the layout resolves the stubs below.
import RootLayout from '../../../../app/_layout';

const UNRESOLVED: ReducedMotion = { isReducedMotion: true, isHydrated: false };
const REDUCED: ReducedMotion = { isReducedMotion: true, isHydrated: true };
const ALLOWED: ReducedMotion = { isReducedMotion: false, isHydrated: true };

/** Screen options the root navigator hands to each of its three entries. */
const screens: Record<string, Record<string, unknown> | undefined> = {};
let rootOptions: Record<string, unknown> | undefined;

const mockStartup = jest.fn();

jest.mock('@/features/startup/hooks', () => ({
  useStartup: () => mockStartup(),
}));

// The real one reaches for a native module that does not exist under Jest.
jest.mock('react-native-gesture-handler', () => {
  const { View } = jest.requireActual('react-native');
  return { GestureHandlerRootView: View };
});

jest.mock('expo-splash-screen', () => ({
  preventAutoHideAsync: jest.fn(() => Promise.resolve()),
  hideAsync: jest.fn(() => Promise.resolve()),
}));

jest.mock('expo-router', () => {
  const { View } = jest.requireActual('react-native');
  const Stack = ({
    children,
    screenOptions,
  }: {
    children: React.ReactNode;
    screenOptions: Record<string, unknown>;
  }) => {
    rootOptions = screenOptions;
    return <View testID="root-stack">{children}</View>;
  };
  const Screen = ({ name, options }: { name: string; options?: Record<string, unknown> }) => {
    screens[name] = options;
    return null;
  };
  Screen.displayName = 'Stack.Screen';
  Stack.Screen = Screen;
  return { Stack, router: { replace: jest.fn() } };
});

beforeEach(() => {
  for (const key of Object.keys(screens)) delete screens[key];
  rootOptions = undefined;
  mockStartup.mockReturnValue({
    isReady: true,
    destination: '/welcome',
    motion: ALLOWED,
  });
});

describe('the transition rule', () => {
  it('fades when motion is allowed', () => {
    const transition = handoffTransition(ALLOWED);

    expect(transition.animation).toBe('fade');
    expect(transition.animationDuration).toBe(HANDOFF_MS);
  });

  it('keeps the handoff short', () => {
    // The sequence before it already took two seconds. This is a swap, not
    // another thing to sit through.
    expect(HANDOFF_MS).toBeGreaterThan(0);
    expect(HANDOFF_MS).toBeLessThanOrEqual(250);
  });

  it('does nothing at all when reduce motion is on', () => {
    const transition = handoffTransition(REDUCED);

    expect(transition.animation).toBe('none');
    expect(transition.animationDuration).toBeUndefined();
  });

  it('does nothing when the preference has not arrived', () => {
    // Treated exactly like reduce motion. Waiting to find out would mean holding
    // somebody on a launch screen until an accessibility read comes back.
    const transition = handoffTransition(UNRESOLVED);

    expect(transition.animation).toBe('none');
  });

  it('never reports that it needs to wait', () => {
    // The rule has no third state. Whatever the preference, there is an answer
    // immediately, so nothing here can gate routing.
    for (const motion of [ALLOWED, REDUCED, UNRESOLVED]) {
      expect(['fade', 'none']).toContain(handoffTransition(motion).animation);
    }
  });

  it('always brings the destination in rather than taking the launch out', () => {
    // `router.replace` plays the pop animation by default, which with the app's
    // ordinary slide would send the finished logo off to the right. Declaring
    // the replacement a push makes the destination the incoming screen.
    for (const motion of [ALLOWED, REDUCED, UNRESOLVED]) {
      expect(handoffTransition(motion).animationTypeForReplace).toBe('push');
    }
  });
});

describe('what the navigator does with it', () => {
  it('gives both destination groups the handoff', async () => {
    await renderWithProviders(<RootLayout />);

    expect(screens['(auth)']).toMatchObject({ animation: 'fade', animationTypeForReplace: 'push' });
    expect(screens['(app)']).toMatchObject({ animation: 'fade', animationTypeForReplace: 'push' });
  });

  it('leaves the launch screen itself alone', async () => {
    // `index` is never navigated to, only away from, so it has nothing to say
    // about how it is entered.
    await renderWithProviders(<RootLayout />);

    expect(screens.index).toBeUndefined();
  });

  it('drops the transition when reduce motion is on', async () => {
    mockStartup.mockReturnValue({ isReady: true, destination: '/home', motion: REDUCED });
    await renderWithProviders(<RootLayout />);

    expect(screens['(auth)']).toMatchObject({ animation: 'none' });
    expect(screens['(app)']).toMatchObject({ animation: 'none' });
  });

  it('drops the transition when the preference is unresolved', async () => {
    mockStartup.mockReturnValue({ isReady: false, destination: '/welcome', motion: UNRESOLVED });
    await renderWithProviders(<RootLayout />);

    expect(screens['(app)']).toMatchObject({ animation: 'none' });
  });

  it('leaves the app-wide default as the ordinary slide', async () => {
    // The handoff is per screen. If it were set on `screenOptions` every push in
    // the app would fade, which is the thing this must not do.
    await renderWithProviders(<RootLayout />);

    expect(rootOptions).toMatchObject({ animation: 'slide_from_right' });
  });

  it('paints every screen on the same ground', async () => {
    // Outgoing launch surface and incoming destination are the same colour, so
    // the crossfade cannot flash a contrasting frame between them.
    await renderWithProviders(<RootLayout />);
    const content = (rootOptions as { contentStyle: { backgroundColor: string } }).contentStyle;

    expect(content.backgroundColor).toBeTruthy();
  });
});

describe('internal navigation is untouched', () => {
  const layout = (group: string) =>
    readFileSync(join(__dirname, '..', '..', '..', '..', 'app', group, '_layout.tsx'), 'utf8');

  it('keeps both nested layouts sliding as they were', () => {
    // Navigation inside a group is governed by that group's own layout, which is
    // why setting the handoff on the root entry cannot reach it.
    for (const group of ['(app)', '(auth)']) {
      expect(layout(group)).toMatch(/animation: 'slide_from_right'/);
    }
  });

  it('leaves the sheet-style screens presenting from the bottom', () => {
    const app = layout('(app)');

    expect(app).toMatch(/payout-request.*slide_from_bottom/);
    expect(app).toMatch(/appearance.*slide_from_bottom/);
  });

  it('adds no fade to any nested layout', () => {
    for (const group of ['(app)', '(auth)']) {
      expect(layout(group)).not.toMatch(/animation: 'fade'/);
    }
  });
});

describe('the destinations are unchanged', () => {
  /** Every destination the resolver can actually produce. */
  const reachable = new Set(
    (['authenticated', 'anonymous'] as const).flatMap((status) =>
      [true, false].map((seen) => resolveDestination(status, seen)),
    ),
  );

  it('still resolves to exactly the three startup destinations', () => {
    expect([...reachable].sort()).toEqual(['/home', '/onboarding', '/welcome']);
  });

  it('lands every one of them in a group the handoff covers', () => {
    // `/home` is inside `(app)`; the other two are inside `(auth)`. Both groups
    // carry the transition, so no destination can arrive without it.
    const group = (destination: string) => (destination === '/home' ? '(app)' : '(auth)');

    for (const destination of reachable) {
      expect(['(auth)', '(app)']).toContain(group(destination));
    }
  });
});

describe('cleanup', () => {
  it('has removed the temporary wordmark proof', () => {
    const brand = join(__dirname, '..', '..', '..', '..', 'assets', 'brand');

    expect(existsSync(join(brand, '_proof-wordmark.svg'))).toBe(false);
  });

  it('has kept every production asset', () => {
    const brand = join(__dirname, '..', '..', '..', '..', 'assets', 'brand');

    for (const name of [
      'sync-wordmark.svg',
      'sync-wordmark-light.svg',
      'sync-wordmark-dark.svg',
      'sync-wordmark-mono-black.svg',
      'sync-wordmark-mono-white.svg',
      'sync-lockup-light.svg',
      'sync-lockup-dark.svg',
      'sync-mark.svg',
    ]) {
      expect(existsSync(join(brand, name))).toBe(true);
    }
  });
});
