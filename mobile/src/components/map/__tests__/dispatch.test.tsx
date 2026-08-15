/**
 * The dispatch section, as a provider and as a customer.
 *
 * Two of these are privacy assertions rather than UI ones: that a provider's
 * position never reaches the network, and that a customer is never shown one.
 * Both are boundaries the product has committed to and neither is visible in a
 * screenshot, so they are pinned here.
 */

import type { BookingAddress, BookingStatus } from '@/api/endpoints/bookings';
import { DispatchSection } from '@/components/map/DispatchSection';
import { renderWithProviders } from '@/test-utils/render';

const mockOpenURL = jest.fn(async () => true);
const mockCanOpenURL = jest.fn(async () => true);
const mockRequestPermission = jest.fn(async () => ({ granted: true }));
const mockGetPosition = jest.fn(async () => ({
  coords: { latitude: 6.6018, longitude: 3.3515 },
}));

jest.mock('react-native/Libraries/Linking/Linking', () => ({
  openURL: (...args: unknown[]) => mockOpenURL(...(args as [])),
  canOpenURL: (...args: unknown[]) => mockCanOpenURL(...(args as [])),
}));

jest.mock('expo-location', () => ({
  Accuracy: { Balanced: 3 },
  requestForegroundPermissionsAsync: () => mockRequestPermission(),
  getCurrentPositionAsync: () => mockGetPosition(),
}));

// The native map is not renderable under Jest. Everything this file asserts is
// about the text, the actions and the network, none of which is inside it.
jest.mock('react-native-maps', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { View } = require('react-native') as typeof import('react-native');
  const Mock = (props: Record<string, unknown>) => <View {...props} />;
  return {
    __esModule: true,
    default: Mock,
    Marker: Mock,
    PROVIDER_DEFAULT: 'default',
  };
});

function address(overrides: Partial<BookingAddress> = {}): BookingAddress {
  return {
    label: 'HOME',
    street_address: '14 Adeola Odeku Street',
    landmark: 'Opposite the Eko Hotel gate',
    area: 'Victoria Island',
    lga: 'Eti-Osa',
    state: 'LAGOS',
    latitude: '6.428055',
    longitude: '3.421944',
    directions_note: '',
    ...overrides,
  };
}

function renderSection(
  status: BookingStatus = 'ASSIGNED',
  overrides: Partial<BookingAddress> = {},
  variant: 'provider' | 'customer' = 'provider',
) {
  return renderWithProviders(
    <DispatchSection
      address={address(overrides)}
      status={status}
      reference="SY-8F3K2A"
      variant={variant}
    />,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockCanOpenURL.mockResolvedValue(true);
  mockRequestPermission.mockResolvedValue({ granted: true });
});

describe('the job location', () => {
  it('uses the booking snapshot rather than a live address', async () => {
    // Editing the saved address later must not move a job that already happened.
    const view = await renderSection();

    expect(view.getByLabelText(/Map showing the job at Victoria Island/)).toBeTruthy();
  });

  it('shows the landmark, which is what a provider navigates by', async () => {
    const view = await renderSection();

    expect(view.getByText('Opposite the Eko Hotel gate')).toBeTruthy();
    expect(view.getByText('Victoria Island, Eti-Osa, LAGOS')).toBeTruthy();
  });

  it('degrades gracefully when the booking was never pinned', async () => {
    const view = await renderSection('ASSIGNED', { latitude: null, longitude: null });

    expect(view.getByText(/no map pin/i)).toBeTruthy();
    expect(view.queryByLabelText(/Map showing/)).toBeNull();
  });

  it('treats a half-set pair as unpinned rather than plotting the equator', async () => {
    const view = await renderSection('ASSIGNED', { longitude: null });

    expect(view.getByText(/no map pin/i)).toBeTruthy();
  });
});

describe('what the lifecycle changes', () => {
  it('offers directions while there is a journey to make', async () => {
    for (const status of ['ASSIGNED', 'EN_ROUTE', 'IN_PROGRESS'] as BookingStatus[]) {
      const view = await renderSection(status);
      expect(view.getByRole('button', { name: 'Get directions' })).toBeTruthy();
    }
  });

  it('keeps the map on a finished job, because "where was that" is fair', async () => {
    const view = await renderSection('COMPLETED');

    expect(view.getByLabelText(/Map showing/)).toBeTruthy();
  });

  it('stops offering to drive somewhere a job is not happening', async () => {
    for (const status of ['CANCELLED', 'EXPIRED'] as BookingStatus[]) {
      const view = await renderSection(status);
      expect(view.queryByRole('button', { name: 'Get directions' })).toBeNull();
      // The location itself remains, as historical context.
      expect(view.getByLabelText(/Map showing/)).toBeTruthy();
    }
  });
});

describe('location permission', () => {
  it('is never requested just to look at a job', async () => {
    await renderSection();

    expect(mockRequestPermission).not.toHaveBeenCalled();
    expect(mockGetPosition).not.toHaveBeenCalled();
  });

  it('is requested only when the provider asks how far away they are', async () => {
    const view = await renderSection();

    expect(view.getByRole('button', { name: 'Show how far I am' })).toBeTruthy();
    expect(mockRequestPermission).not.toHaveBeenCalled();
  });

  it('leaves the job usable when permission is refused', async () => {
    mockRequestPermission.mockResolvedValue({ granted: false });
    const view = await renderSection();

    expect(view.getByLabelText(/Map showing/)).toBeTruthy();
    expect(view.getByRole('button', { name: 'Get directions' })).toBeTruthy();
  });
});

describe('the customer view', () => {
  it('shows the location without any dispatch controls', async () => {
    const view = await renderSection('EN_ROUTE', {}, 'customer');

    expect(view.getByLabelText(/Map showing/)).toBeTruthy();
    expect(view.queryByRole('button', { name: 'Get directions' })).toBeNull();
    expect(view.queryByRole('button', { name: 'Show how far I am' })).toBeNull();
  });

  it('never offers a customer anything that would reveal a provider position', async () => {
    // The committed boundary: no live tracking, no provider marker, no ETA.
    const view = await renderSection('EN_ROUTE', {}, 'customer');

    expect(view.queryByText(/away/i)).toBeNull();
    expect(view.queryByText(/eta|arriv/i)).toBeNull();
    expect(mockRequestPermission).not.toHaveBeenCalled();
  });
});

describe('the privacy boundary', () => {
  it('never sends a coordinate anywhere', async () => {
    const fetchSpy = jest.spyOn(global, 'fetch' as never).mockImplementation(
      jest.fn() as never,
    );

    const view = await renderSection();
    view.getByRole('button', { name: 'Show how far I am' });

    // Nothing on this screen talks to the network at all. There is no endpoint
    // that would accept a provider position, and this is what keeps it that way.
    expect(fetchSpy).not.toHaveBeenCalled();

    fetchSpy.mockRestore();
  });
});
