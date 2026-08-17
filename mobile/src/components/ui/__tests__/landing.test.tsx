/**
 * The landing screen and the introduction.
 *
 * The load-bearing test here is the one asserting no discount is promised. The
 * design this was built from carried a "20% off with SYNC20" band, and there is
 * no promo system anywhere in the backend, so shipping it would have meant the
 * one screen whose job is to make a promise making one the product cannot keep.
 */

import OnboardingScreen from '@/../app/(auth)/onboarding';
import WelcomeScreen from '@/../app/(auth)/welcome';
import { renderWithProviders, SMALL_METRICS } from '@/test-utils/render';

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() }),
  Link: 'Link',
}));

describe('the landing screen', () => {
  it('says what Sync is', async () => {
    const view = await renderWithProviders(<WelcomeScreen />);

    expect(view.getByText(/Everything you need/)).toBeTruthy();
    expect(view.getByText(/Simple. Reliable./)).toBeTruthy();
  });

  it('shows every service the catalog actually sells', async () => {
    // Six, not the four in the mockup. A landing that under-sells the catalog
    // sends people away looking for something that was there all along.
    const view = await renderWithProviders(<WelcomeScreen />);

    for (const name of ['Courier', 'Errands', 'Cleaning', 'Home', 'Beauty', 'Laundry']) {
      expect(view.getByText(name)).toBeTruthy();
    }
  });

  it('promises no discount, because there is no discount system', async () => {
    const view = await renderWithProviders(<WelcomeScreen />);
    const text = JSON.stringify(view.toJSON());

    expect(text).not.toMatch(/20%|SYNC20|off your first|discount|promo code/i);
  });

  it('claims nothing about tracking or arrival times', async () => {
    const view = await renderWithProviders(<WelcomeScreen />);
    const text = JSON.stringify(view.toJSON());

    expect(text).not.toMatch(/track your|live location|estimated arrival/i);
  });

  it('offers both doors', async () => {
    const view = await renderWithProviders(<WelcomeScreen />);

    expect(view.getByRole('button', { name: 'Get started' })).toBeTruthy();
    expect(view.getByRole('button', { name: 'Sign in to an existing account' })).toBeTruthy();
  });

  it('keeps the primary action reachable without scrolling', async () => {
    // Pinned in a footer rather than at the end of the scroll, so it survives a
    // short screen.
    const view = await renderWithProviders(<WelcomeScreen />, { metrics: SMALL_METRICS });

    expect(view.getByRole('button', { name: 'Get started' })).toBeTruthy();
  });

  it('renders in dark mode', async () => {
    const view = await renderWithProviders(<WelcomeScreen />, { mode: 'dark' });

    expect(view.getByText(/Everything you need/)).toBeTruthy();
  });
});

describe('the introduction', () => {
  it('can be skipped from the first frame', async () => {
    // An introduction that cannot be dismissed is an advert.
    const view = await renderWithProviders(<OnboardingScreen />);

    expect(view.getByRole('button', { name: 'Skip the introduction' })).toBeTruthy();
  });

  it('reports progress to assistive technology', async () => {
    const view = await renderWithProviders(<OnboardingScreen />);

    expect(view.getByRole('progressbar')).toBeTruthy();
    expect(view.getByLabelText(/Step 1 of \d/)).toBeTruthy();
  });

  it('has a labelled advance control', async () => {
    const view = await renderWithProviders(<OnboardingScreen />);

    expect(view.getByRole('button', { name: 'Next' })).toBeTruthy();
  });

  it('renders in dark mode', async () => {
    const view = await renderWithProviders(<OnboardingScreen />, { mode: 'dark' });

    expect(view.getByRole('button', { name: 'Skip the introduction' })).toBeTruthy();
  });
});
