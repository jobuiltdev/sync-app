/**
 * How the coordinator carries the Reduce Motion preference.
 *
 * Two guarantees, and they pull in opposite directions. The launch surface needs
 * the preference, so it is exposed. Routing does not, so it must never wait for
 * it: where somebody lands has nothing to do with how they feel about motion,
 * and gating the destination on an accessibility read would delay every launch
 * for no reason.
 */

import { act, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Text as RNText } from 'react-native';

import { resetOnboardingHydration } from '@/features/onboarding/store';
import { useStartup } from '@/features/startup/hooks';
import { renderWithProviders } from '@/test-utils/render';

function Probe() {
  const { isReady, destination, motion } = useStartup();

  return (
    <>
      <RNText testID="ready">{String(isReady)}</RNText>
      <RNText testID="destination">{destination}</RNText>
      <RNText testID="motion-hydrated">{String(motion.isHydrated)}</RNText>
      <RNText testID="motion-reduced">{String(motion.isReducedMotion)}</RNText>
    </>
  );
}

beforeEach(() => {
  jest.restoreAllMocks();
  resetOnboardingHydration();
});

describe('motion readiness alongside startup', () => {
  it('is exposed so a launch surface can wait on it', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);

    const view = await renderWithProviders(<Probe />);

    await waitFor(() =>
      expect(view.getByTestId('motion-hydrated')).toHaveTextContent('true'),
    );
    expect(view.getByTestId('motion-reduced')).toHaveTextContent('true');
  });

  it('does not hold up routing while the preference is unknown', async () => {
    // A query that never settles. The destination must still resolve, because
    // it does not depend on this and nobody should wait on an accessibility
    // read to be let into the app.
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockReturnValue(new Promise(() => undefined) as never);

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('ready')).toHaveTextContent('true'));
    expect(view.getByTestId('motion-hydrated')).toHaveTextContent('false');
  });

  it('resolves a destination independently of the preference', async () => {
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockReturnValue(new Promise(() => undefined) as never);

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('ready')).toHaveTextContent('true'));
    // No session and no onboarding flag in a fresh test keychain.
    expect(view.getByTestId('destination')).toHaveTextContent('/onboarding');
  });

  it('keeps following preference changes through the coordinator', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false);

    let handler: ((enabled: boolean) => void) | undefined;
    jest
      .spyOn(AccessibilityInfo, 'addEventListener')
      .mockImplementation(((event: string, cb: (enabled: boolean) => void) => {
        if (event === 'reduceMotionChanged') handler = cb;
        return { remove: jest.fn() };
      }) as never);

    const view = await renderWithProviders(<Probe />);
    await waitFor(() =>
      expect(view.getByTestId('motion-reduced')).toHaveTextContent('false'),
    );

    await act(async () => {
      handler?.(true);
    });

    expect(view.getByTestId('motion-reduced')).toHaveTextContent('true');
  });
});
