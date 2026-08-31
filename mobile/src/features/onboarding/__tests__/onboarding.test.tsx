import { act, waitFor } from '@testing-library/react-native';
import { Text as RNText } from 'react-native';

import { useOnboarding, resetOnboarding } from '@/features/onboarding/hooks';
import { ONBOARDING_STORAGE_KEY, SLIDES } from '@/features/onboarding/slides';
import {
  resetOnboardingHydration,
  useOnboardingStore,
} from '@/features/onboarding/store';
import { secureStorage } from '@/lib/secure-storage';
import { renderWithProviders } from '@/test-utils/render';

function Probe() {
  const { state, complete } = useOnboarding();

  return (
    <>
      <RNText testID="state">{state}</RNText>
      <RNText testID="complete" onPress={() => void complete()}>
        done
      </RNText>
    </>
  );
}

beforeEach(async () => {
  await resetOnboarding();
  // Hydration is now owned by the store and runs once per app launch, driven
  // from the root layout rather than from whichever component happened to call
  // the hook first. Each test starts from a fresh lifecycle.
  resetOnboardingHydration();
  await secureStorage.remove(ONBOARDING_STORAGE_KEY);
});

/** What the root layout does at launch, via `useStartup`. */
async function hydrate() {
  await useOnboardingStore.getState().hydrate();
}

describe('the slides', () => {
  it('describes what the app does rather than how to use it', () => {
    // Somebody who swipes through should be able to explain Sync to a friend.
    expect(SLIDES.length).toBeGreaterThanOrEqual(3);

    for (const slide of SLIDES) {
      expect(slide.title.trim().length).toBeGreaterThan(0);
      expect(slide.body.trim().length).toBeGreaterThan(20);
    }
  });

  it('names the services the catalog actually sells', () => {
    const text = SLIDES.map((s) => `${s.title} ${s.body}`).join(' ').toLowerCase();

    for (const service of ['courier', 'cleaning', 'errand', 'laundry', 'beauty']) {
      expect(text).toContain(service);
    }
  });

  it('promises nothing the backend cannot keep', () => {
    // No discount, no tracking, no ETA. Every one of those would be a claim the
    // system has no way to honour.
    const text = SLIDES.map((s) => `${s.title} ${s.body}`).join(' ').toLowerCase();

    expect(text).not.toMatch(/\d+% off|discount|promo|coupon/);
    expect(text).not.toMatch(/track your provider|live location|eta/);
  });

  it('has a unique key per slide', () => {
    expect(new Set(SLIDES.map((s) => s.key)).size).toBe(SLIDES.length);
  });
});

describe('showing it once', () => {
  it('reports loading until the flag has been read', async () => {
    const view = await renderWithProviders(<Probe />);

    // Consumers no longer trigger their own read, so before the launch
    // hydration runs the honest answer is "not known yet".
    expect(view.getByTestId('state')).toHaveTextContent('loading');
  });

  it('is needed on a first launch', async () => {
    await act(async () => {
      await hydrate();
    });
    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('state')).toHaveTextContent('needed'));
  });

  it('is not needed once it has been seen', async () => {
    await secureStorage.set(ONBOARDING_STORAGE_KEY, 'true');
    await act(async () => {
      await hydrate();
    });

    const view = await renderWithProviders(<Probe />);

    await waitFor(() => expect(view.getByTestId('state')).toHaveTextContent('seen'));
  });

  it('reads the keychain once however many consumers mount', async () => {
    // The reason this became a store. Two components calling the hook used to
    // mean two reads and two independent state machines.
    const spy = jest.spyOn(secureStorage, 'get');

    await act(async () => {
      await Promise.all([hydrate(), hydrate(), hydrate()]);
    });

    const reads = spy.mock.calls.filter(([key]) => key === ONBOARDING_STORAGE_KEY);
    expect(reads).toHaveLength(1);

    spy.mockRestore();
  });

  it('shares one state across every consumer', async () => {
    await act(async () => {
      await hydrate();
    });

    const view = await renderWithProviders(
      <>
        <Probe />
        <Probe />
      </>,
    );

    await act(async () => {
      view.getAllByTestId('complete')[0].props.onPress();
    });

    // Completing in one is observed by the other, which was not true before.
    for (const node of view.getAllByTestId('state')) {
      expect(node).toHaveTextContent('seen');
    }
  });

  it('remembers that it was completed', async () => {
    await act(async () => {
      await hydrate();
    });
    const view = await renderWithProviders(<Probe />);
    await waitFor(() => expect(view.getByTestId('state')).toHaveTextContent('needed'));

    await act(async () => {
      view.getByTestId('complete').props.onPress();
    });

    await waitFor(async () =>
      expect(await secureStorage.get(ONBOARDING_STORAGE_KEY)).toBe('true'),
    );
  });

  it('marks it seen before navigating, so a force quit does not repeat it', async () => {
    await act(async () => {
      await hydrate();
    });
    const view = await renderWithProviders(<Probe />);
    await waitFor(() => expect(view.getByTestId('state')).toHaveTextContent('needed'));

    await act(async () => {
      view.getByTestId('complete').props.onPress();
    });

    expect(view.getByTestId('state')).toHaveTextContent('seen');
  });
});
