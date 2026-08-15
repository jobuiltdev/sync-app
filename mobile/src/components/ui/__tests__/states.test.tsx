import { ApiError } from '@/api/errors';
import { Avatar, initialsOf } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { EmptyState, ErrorState, InlineError } from '@/components/ui/States';
import { StatusPill } from '@/components/ui/StatusPill';
import { bookingStatusView } from '@/features/status/presentation';
import { renderWithProviders } from '@/test-utils/render';

describe('empty states', () => {
  it('says what is missing and what to do about it', async () => {
    const view = await renderWithProviders(
      <EmptyState
        icon="clock"
        title="Nothing booked yet"
        body="When you request a service it will show up here."
        action={<Button label="Browse services" onPress={jest.fn()} />}
      />,
    );

    expect(view.getByText('Nothing booked yet')).toBeTruthy();
    expect(view.getByText(/show up here/)).toBeTruthy();
    expect(view.getByRole('button', { name: 'Browse services' })).toBeTruthy();
  });

  it('works without an action', async () => {
    const view = await renderWithProviders(<EmptyState title="Nothing here" />);

    expect(view.getByText('Nothing here')).toBeTruthy();
  });
});

describe('error states', () => {
  it('shows the message the server actually sent', async () => {
    // The whole point: a domain message is worth more than a generic apology.
    const error = new ApiError({
      code: 'NO_ELIGIBLE_PROVIDERS',
      message: 'No provider covers this service in your area yet.',
      status: 422,
    });

    const view = await renderWithProviders(<ErrorState error={error} />);

    expect(view.getByText('No provider covers this service in your area yet.')).toBeTruthy();
  });

  it('treats a dropped connection as its own thing', async () => {
    const error = new ApiError({
      code: 'NETWORK_UNAVAILABLE',
      message: 'The request never left the device.',
    });

    const view = await renderWithProviders(<ErrorState error={error} />);

    expect(view.getByText('No connection')).toBeTruthy();
    expect(view.getByText(/data or Wi-Fi/)).toBeTruthy();
  });

  it('offers a retry when one is given', async () => {
    const onRetry = jest.fn();
    const view = await renderWithProviders(
      <ErrorState error={new Error('boom')} onRetry={onRetry} />,
    );

    expect(view.getByRole('button', { name: 'Try again' })).toBeTruthy();
  });

  it('announces itself as an alert', async () => {
    const view = await renderWithProviders(<ErrorState error={new Error('boom')} />);

    expect(view.getByRole('alert')).toBeTruthy();
  });
});

describe('inline errors', () => {
  it('renders nothing when there is no error', async () => {
    const view = await renderWithProviders(<InlineError error={null} />);

    expect(view.queryByRole('alert')).toBeNull();
  });

  it('carries the server message verbatim', async () => {
    const error = new ApiError({
      code: 'INSUFFICIENT_BALANCE',
      message: 'That is more than your available balance.',
      status: 422,
    });

    const view = await renderWithProviders(<InlineError error={error} />);

    expect(view.getByText('That is more than your available balance.')).toBeTruthy();
  });
});

describe('status pills', () => {
  it('shows the written label, not the raw status code', async () => {
    const view = await renderWithProviders(
      <StatusPill view={bookingStatusView('AWAITING_CONFIRMATION')} />,
    );

    expect(view.getByText('Confirm it is done')).toBeTruthy();
    expect(view.queryByText('AWAITING_CONFIRMATION')).toBeNull();
  });

  it('renders a status that opens every booking', async () => {
    const view = await renderWithProviders(<StatusPill view={bookingStatusView('MATCHING')} />);

    expect(view.getByText('Finding a provider')).toBeTruthy();
  });
});

describe('avatar initials', () => {
  it('takes the first and last initial of a full name', () => {
    expect(initialsOf('Ada Nwosu Okeke')).toBe('AO');
  });

  it('takes two letters from a single name', () => {
    expect(initialsOf('Ada')).toBe('AD');
  });

  it('does not crash on an empty name', () => {
    expect(initialsOf('   ')).toBe('?');
  });

  it('ignores punctuation-only parts', () => {
    expect(initialsOf('Ada - Okeke')).toBe('AO');
  });

  it('is hidden from assistive technology, being decorative', async () => {
    // The initials duplicate a name that is already read out beside them.
    // Announcing "A O" before every provider's name is noise, so the avatar is
    // excluded from the accessibility tree and only found when hidden elements
    // are included.
    const view = await renderWithProviders(<Avatar name="Ada Okeke" />);

    expect(view.queryByText('AO')).toBeNull();
    expect(view.queryByText('AO', { includeHiddenElements: true })).toBeTruthy();
  });
});
