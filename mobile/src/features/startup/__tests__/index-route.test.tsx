/**
 * The launch seam, end to end.
 *
 * Renders the real `app/index.tsx` against stubbed stores and asserts where it
 * sends people. The pure priority logic is covered in `destination.test.ts`;
 * this checks the screen is actually wired to it, and that nothing is revealed
 * before the reads are in.
 */

import { readFileSync } from 'fs';
import { join } from 'path';

import Index from '@/../app/index';
import { renderWithProviders } from '@/test-utils/render';

const mockStartup = jest.fn();

/** These cases are about routing, so motion stays unresolved: the launch
 *  surface then shows the static mark and nothing animates. */
const UNRESOLVED = { isReducedMotion: true, isHydrated: false };

jest.mock('@/features/startup/hooks', () => ({
  useStartup: () => mockStartup(),
}));

const redirects: string[] = [];

jest.mock('expo-router', () => ({
  router: {
    replace: (href: string) => {
      redirects.push(href);
    },
  },
}));

beforeEach(() => {
  redirects.length = 0;
  jest.clearAllMocks();
});

describe('the launch seam', () => {
  it('reveals nothing until the local reads are in', async () => {
    mockStartup.mockReturnValue({ isReady: false, destination: '/welcome', motion: UNRESOLVED });

    await renderWithProviders(<Index />);

    // Navigating early would flash a screen the person is about to be moved off.
    expect(redirects).toEqual([]);
  });

  it('paints the themed ground while it waits, not a spinner', async () => {
    mockStartup.mockReturnValue({ isReady: false, destination: '/welcome', motion: UNRESOLVED });

    const view = await renderWithProviders(<Index />);
    const root = view.toJSON();

    // The native splash is still covering this, so anything drawn here would
    // either never be seen or would flash for a frame during the handoff.
    expect(JSON.stringify(root)).not.toMatch(/ActivityIndicator/);
  });

  it('shows the static Sync mark while it waits', async () => {
    mockStartup.mockReturnValue({ isReady: false, destination: '/welcome', motion: UNRESOLVED });

    const view = await renderWithProviders(<Index />);

    expect(view.getByTestId('launch-surface')).toBeTruthy();
    expect(view.getByLabelText('Sync')).toBeTruthy();
    expect(view.getByTestId('sync-route-upper')).toBeTruthy();
    expect(view.getByTestId('sync-route-lower')).toBeTruthy();
  });

  it('sends an authenticated person home', async () => {
    mockStartup.mockReturnValue({ isReady: true, destination: '/home', motion: UNRESOLVED });

    await renderWithProviders(<Index />);

    expect(redirects).toEqual(['/home']);
  });

  it('sends a first-time visitor to the introduction', async () => {
    mockStartup.mockReturnValue({ isReady: true, destination: '/onboarding', motion: UNRESOLVED });

    await renderWithProviders(<Index />);

    expect(redirects).toEqual(['/onboarding']);
  });

  it('sends a returning signed-out person to welcome', async () => {
    mockStartup.mockReturnValue({ isReady: true, destination: '/welcome', motion: UNRESOLVED });

    await renderWithProviders(<Index />);

    expect(redirects).toEqual(['/welcome']);
  });

  it('makes no decision of its own', async () => {
    // Every destination comes from the coordinator. If this screen ever starts
    // branching on session or onboarding state directly, there are two copies
    // of the priority and one of them will drift.
    const source = readFileSync(join(__dirname, '../../../../app/index.tsx'), 'utf8');

    expect(source).not.toMatch(/useSessionStore|useOnboarding\b/);
  });
});
