/**
 * The system Reduce Motion preference.
 *
 * The behaviour worth protecting here is the three-valued answer. An earlier
 * version reported `false` while the query was in flight, which meant somebody
 * who had asked for less motion could receive the opening frames of a cinematic
 * sequence before their preference resolved. Those are precisely the frames that
 * cause harm, so "not known yet" is now distinguishable from "known to be off".
 */

import { act, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Text as RNText } from 'react-native';

import { useReducedMotion } from '@/features/accessibility/reduced-motion';
import { renderWithProviders } from '@/test-utils/render';

function Probe() {
  const { isReducedMotion, isHydrated } = useReducedMotion();

  return (
    <>
      <RNText testID="reduced">{String(isReducedMotion)}</RNText>
      <RNText testID="hydrated">{String(isHydrated)}</RNText>
    </>
  );
}

/** Captures the listener React Native was given, so a preference change can be
 *  simulated without reaching into platform internals. */
function captureListener() {
  let handler: ((enabled: boolean) => void) | undefined;

  jest
    .spyOn(AccessibilityInfo, 'addEventListener')
    .mockImplementation(((event: string, cb: (enabled: boolean) => void) => {
      if (event === 'reduceMotionChanged') handler = cb;
      return { remove: jest.fn() };
    }) as never);

  return { fire: (enabled: boolean) => handler?.(enabled) };
}

/** A query that never settles, for observing the unresolved state. */
function pending() {
  jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockReturnValue(new Promise(() => undefined) as never);
}

beforeEach(() => {
  jest.restoreAllMocks();
});

describe('before the preference is known', () => {
  it('reports itself as not hydrated', async () => {
    pending();

    const view = await renderWithProviders(<Probe />);

    expect(view.getByTestId('hydrated')).toHaveTextContent('false');
  });

  it('is distinguishable from the preference being off', async () => {
    // The whole point of the change. A caller must be able to tell "nobody has
    // told me yet" apart from "the user does want motion".
    pending();

    const view = await renderWithProviders(<Probe />);

    expect(view.getByTestId('hydrated')).toHaveTextContent('false');
    expect(view.getByTestId('reduced')).toHaveTextContent('true');
  });

  it('defaults towards less motion, not more', async () => {
    // A caller that forgets to check isHydrated should still fail safe. The
    // cost of a wrongly-static launch is a dull second; the cost of wrongly
    // playing it is somebody feeling ill.
    pending();

    const view = await renderWithProviders(<Probe />);

    expect(view.getByTestId('reduced')).toHaveTextContent('true');
  });
});

describe('once the preference resolves', () => {
  it('reports reduced motion when the OS setting is on', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('hydrated')).toHaveTextContent('true'));
    expect(view.getByTestId('reduced')).toHaveTextContent('true');
  });

  it('reports normal motion when the OS setting is off', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false);

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('reduced')).toHaveTextContent('false'));
    expect(view.getByTestId('hydrated')).toHaveTextContent('true');
  });

  it('marks itself hydrated either way', async () => {
    for (const enabled of [true, false]) {
      jest.restoreAllMocks();
      jest
        .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
        .mockResolvedValue(enabled);

      const view = await renderWithProviders(<Probe />);

      await waitFor(() => expect(view.getByTestId('hydrated')).toHaveTextContent('true'));
    }
  });
});

describe('changes while the app is running', () => {
  it('follows the preference being turned on', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false);
    const { fire } = captureListener();

    const view = await renderWithProviders(<Probe />);
    await waitFor(() => expect(view.getByTestId('reduced')).toHaveTextContent('false'));

    // Changed from Control Centre while Sync was backgrounded. A value captured
    // once at launch would be wrong for the rest of the session.
    await act(async () => {
      fire(true);
    });

    expect(view.getByTestId('reduced')).toHaveTextContent('true');
  });

  it('follows the preference being turned off', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
    const { fire } = captureListener();

    const view = await renderWithProviders(<Probe />);
    await waitFor(() => expect(view.getByTestId('reduced')).toHaveTextContent('true'));

    await act(async () => {
      fire(false);
    });

    expect(view.getByTestId('reduced')).toHaveTextContent('false');
  });

  it('counts a change event as hydration', async () => {
    // If the initial query is still hanging when the OS volunteers an answer,
    // that answer is as authoritative as the one we asked for.
    pending();
    const { fire } = captureListener();

    const view = await renderWithProviders(<Probe />);
    expect(view.getByTestId('hydrated')).toHaveTextContent('false');

    await act(async () => {
      fire(false);
    });

    expect(view.getByTestId('hydrated')).toHaveTextContent('true');
    expect(view.getByTestId('reduced')).toHaveTextContent('false');
  });
});

describe('when the platform cannot answer', () => {
  it('resolves rather than hanging for ever', async () => {
    // Holding a launch surface static permanently because an API is missing
    // would be a worse outcome than playing the animation.
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockRejectedValue(new Error('unsupported'));

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('hydrated')).toHaveTextContent('true'));
    expect(view.getByTestId('reduced')).toHaveTextContent('false');
  });
});

describe('teardown', () => {
  it('unsubscribes when it goes away', async () => {
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(false);
    const remove = jest.fn();
    jest
      .spyOn(AccessibilityInfo, 'addEventListener')
      .mockReturnValue({ remove } as never);

    const view = await renderWithProviders(<Probe />);
    await act(async () => {
      view.unmount();
    });

    expect(remove).toHaveBeenCalled();
  });
});
