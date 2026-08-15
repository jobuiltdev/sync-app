/**
 * Mount smoke tests for the tab screens.
 *
 * Bundling proves a screen imports; it does not prove it renders. These mount
 * each destination against stubbed queries and assert the thing a person would
 * look for, which catches the class of failure where a redesign typechecks,
 * bundles, and then throws on first paint.
 *
 * The API layer is stubbed at the feature-hook boundary rather than at fetch,
 * because these are tests of presentation and the hooks already have their own.
 */

import ActivityScreen from '@/../app/(app)/(tabs)/activity';
import HomeScreen from '@/../app/(app)/(tabs)/home';
import ProfileScreen from '@/../app/(app)/(tabs)/profile';
import { renderWithProviders } from '@/test-utils/render';

const pending = { isPending: true, isRefetching: false, error: null, data: undefined };
const settled = <T,>(data: T) => ({ isPending: false, isRefetching: false, error: null, data });

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn(), navigate: jest.fn() }),
  usePathname: () => '/home',
  Link: 'Link',
}));

const mockCategories = jest.fn();
const mockUser = jest.fn();
const mockProvider = jest.fn();
const mockBookings = jest.fn();
const mockJobs = jest.fn();
const mockOffers = jest.fn();

jest.mock('@/features/catalog/hooks', () => ({
  useCategories: () => mockCategories(),
  useAddresses: () => settled({ results: [] }),
}));
jest.mock('@/features/auth/hooks', () => ({
  useCurrentUser: () => mockUser(),
  useSignOut: () => ({ mutate: jest.fn(), isPending: false }),
}));
jest.mock('@/features/providers/hooks', () => ({
  useProviderProfile: () => mockProvider(),
}));
jest.mock('@/features/bookings/hooks', () => ({
  useBookings: () => mockBookings(),
  useJobs: () => mockJobs(),
}));
jest.mock('@/features/offers/hooks', () => ({
  useOffers: () => mockOffers(),
}));

beforeEach(() => {
  mockUser.mockReturnValue(
    settled({
      full_name: 'Ada Okeke',
      first_name: 'Ada',
      email: 'ada@example.com',
      is_phone_verified: true,
      is_email_verified: true,
    }),
  );
  mockProvider.mockReturnValue(settled(undefined));
  mockBookings.mockReturnValue(settled({ results: [] }));
  mockJobs.mockReturnValue(settled({ results: [] }));
  mockOffers.mockReturnValue(settled({ results: [] }));
  mockCategories.mockReturnValue(settled([]));
});

describe('Home', () => {
  it('greets the person by name', async () => {
    const view = await renderWithProviders(<HomeScreen />);

    expect(view.getByText('Ada')).toBeTruthy();
  });

  it('does not greet an undefined name', async () => {
    mockUser.mockReturnValue(settled({ full_name: '', first_name: '', email: 'a@b.c' }));

    const view = await renderWithProviders(<HomeScreen />);

    expect(view.queryByText(/undefined/)).toBeNull();
    expect(view.getByText('Welcome back')).toBeTruthy();
  });

  it('shows a skeleton rather than a blank screen while the catalog loads', async () => {
    mockCategories.mockReturnValue(pending);

    const view = await renderWithProviders(<HomeScreen />);

    expect(view.queryByText(/Nothing available/)).toBeNull();
  });

  it('explains an empty catalog instead of showing nothing', async () => {
    const view = await renderWithProviders(<HomeScreen />);

    expect(view.getByText('Nothing available yet')).toBeTruthy();
  });

  it('renders services with a price from the shared formatter', async () => {
    mockCategories.mockReturnValue(
      settled([
        {
          id: 'c1',
          slug: 'cleaning',
          name: 'Cleaning',
          description: '',
          icon_key: 'cleaning',
          sort_order: 1,
          services: [
            {
              id: 's1',
              slug: 'standard-clean',
              name: 'Standard clean',
              summary: 'A tidy home',
              category_slug: 'cleaning',
              booking_modes: 'BOTH',
              pricing_model: 'FIXED',
              base_price_kobo: 2_000_000,
            },
          ],
        },
      ]),
    );

    const view = await renderWithProviders(<HomeScreen />);

    expect(view.getByText('Standard clean')).toBeTruthy();
    expect(view.getByText('₦20,000')).toBeTruthy();
  });

  it('surfaces a booking already in progress above the catalog', async () => {
    mockBookings.mockReturnValue(
      settled({
        results: [
          {
            id: 'b1',
            reference: 'SY-1',
            status: 'MATCHING',
            service_slug: 'standard-clean',
            service_name: 'Standard clean',
            provider_name: null,
            address_summary: 'VI',
            total_kobo: 2_000_000,
            scheduled_for: null,
            created_at: '2026-08-01T10:00:00Z',
          },
        ],
      }),
    );

    const view = await renderWithProviders(<HomeScreen />);

    expect(view.getByText('Happening now')).toBeTruthy();
    expect(view.getByText('Finding a provider')).toBeTruthy();
  });

  it('renders in dark mode', async () => {
    const view = await renderWithProviders(<HomeScreen />, { mode: 'dark' });

    expect(view.getByText('Ada')).toBeTruthy();
  });
});

describe('Activity', () => {
  it('offers no role switch to a customer', async () => {
    const view = await renderWithProviders(<ActivityScreen />);

    // A segmented control with one meaningful option is noise.
    expect(view.queryByText('Your work')).toBeNull();
  });

  it('offers the role switch once an account has a provider side', async () => {
    mockProvider.mockReturnValue(settled({ id: 'p1', verification_status: 'APPROVED' }));

    const view = await renderWithProviders(<ActivityScreen />);

    expect(view.getByText('Your work')).toBeTruthy();
    expect(view.getByText('Your bookings')).toBeTruthy();
  });

  it('explains an empty activity list', async () => {
    const view = await renderWithProviders(<ActivityScreen />);

    expect(view.getByText('Nothing booked yet')).toBeTruthy();
  });
});

describe('Profile', () => {
  it('groups the account rather than listing everything at once', async () => {
    const view = await renderWithProviders(<ProfileScreen />);

    expect(view.getByText('Account')).toBeTruthy();
    expect(view.getByText('Working with Sync')).toBeTruthy();
    expect(view.getByText('App')).toBeTruthy();
  });

  it('invites a customer to become a provider instead of showing provider controls', async () => {
    const view = await renderWithProviders(<ProfileScreen />);

    expect(view.getByText('Become a provider')).toBeTruthy();
    expect(view.queryByText('Earnings')).toBeNull();
  });

  it('shows the provider controls once there is a provider profile', async () => {
    mockProvider.mockReturnValue(settled({ id: 'p1', verification_status: 'APPROVED' }));

    const view = await renderWithProviders(<ProfileScreen />);

    expect(view.getByText('Provider profile')).toBeTruthy();
    expect(view.getByText('Earnings')).toBeTruthy();
    expect(view.getByText('Approved')).toBeTruthy();
  });

  it('flags unverified contact details as needing action', async () => {
    mockUser.mockReturnValue(
      settled({
        full_name: 'Ada Okeke',
        first_name: 'Ada',
        email: 'ada@example.com',
        is_phone_verified: false,
        is_email_verified: false,
      }),
    );

    const view = await renderWithProviders(<ProfileScreen />);

    expect(view.getByText('Action needed')).toBeTruthy();
  });

  it('shows the current appearance setting', async () => {
    const view = await renderWithProviders(<ProfileScreen />, { mode: 'dark' });

    expect(view.getByText('Appearance')).toBeTruthy();
    expect(view.getByText('Dark')).toBeTruthy();
  });
});
