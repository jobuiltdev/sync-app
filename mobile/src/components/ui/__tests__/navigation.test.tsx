import { TabBar, type TabItem } from '@/components/navigation/TabBar';
import { Segmented } from '@/components/ui/Segmented';
import { renderWithProviders } from '@/test-utils/render';

const ITEMS: TabItem[] = [
  { key: 'home', label: 'Home', icon: 'home' },
  { key: 'activity', label: 'Activity', icon: 'activity' },
  { key: 'profile', label: 'Profile', icon: 'profile' },
];

function withTheme(node: React.ReactElement, mode: 'light' | 'dark' = 'light') {
  return renderWithProviders(node, { mode });
}

describe('the glass tab bar', () => {
  it('renders the three destinations and no more', async () => {
    const view = await withTheme(<TabBar items={ITEMS} activeKey="home" onSelect={jest.fn()} />);

    expect(view.getAllByRole('tab')).toHaveLength(3);
  });

  it('labels every tab in text as well as with an icon', async () => {
    // Icons are never the only carrier of meaning.
    const view = await withTheme(<TabBar items={ITEMS} activeKey="home" onSelect={jest.fn()} />);

    expect(view.getByText('Home')).toBeTruthy();
    expect(view.getByText('Activity')).toBeTruthy();
    expect(view.getByText('Profile')).toBeTruthy();
  });

  it('marks the active tab as selected for assistive technology', async () => {
    const view = await withTheme(
      <TabBar items={ITEMS} activeKey="activity" onSelect={jest.fn()} />,
    );

    const tabs = view.getAllByRole('tab');
    const selected = tabs.filter((tab) => tab.props.accessibilityState?.selected);

    expect(selected).toHaveLength(1);
    expect(selected[0].props.accessibilityLabel).toBe('Activity');
  });

  it('reports a pending count in the accessible name', async () => {
    const view = await withTheme(
      <TabBar
        items={[ITEMS[0], { ...ITEMS[1], badge: 3 }, ITEMS[2]]}
        activeKey="home"
        onSelect={jest.fn()}
      />,
    );

    expect(view.getByLabelText('Activity, 3 waiting')).toBeTruthy();
  });

  it('shows no badge when nothing is waiting', async () => {
    const view = await withTheme(
      <TabBar
        items={[ITEMS[0], { ...ITEMS[1], badge: 0 }, ITEMS[2]]}
        activeKey="home"
        onSelect={jest.fn()}
      />,
    );

    expect(view.queryByLabelText(/waiting/)).toBeNull();
  });

  it('moves to the tapped destination', async () => {
    const onSelect = jest.fn();
    const view = await withTheme(<TabBar items={ITEMS} activeKey="home" onSelect={onSelect} />);

    view.getByLabelText('Profile').props.onClick?.();
    const profile = view.getAllByRole('tab')[2];
    profile.props.onStartShouldSetResponder?.();
    profile.props.onResponderRelease?.({ nativeEvent: {} });

    expect(onSelect).toHaveBeenCalledWith('profile');
  });

  it('renders in dark mode without losing its labels', async () => {
    const view = await withTheme(
      <TabBar items={ITEMS} activeKey="home" onSelect={jest.fn()} />,
      'dark',
    );

    expect(view.getAllByRole('tab')).toHaveLength(3);
    expect(view.getByText('Home')).toBeTruthy();
  });
});

describe('the segmented control', () => {
  const SEGMENTS = [
    { value: 'customer' as const, label: 'Your bookings' },
    { value: 'provider' as const, label: 'Your work' },
  ];

  it('marks the selected segment', async () => {
    const view = await withTheme(
      <Segmented segments={SEGMENTS} value="provider" onChange={jest.fn()} />,
    );

    const tabs = view.getAllByRole('tab');
    const selected = tabs.filter((tab) => tab.props.accessibilityState?.selected);

    expect(selected).toHaveLength(1);
    expect(selected[0].props.accessibilityLabel).toBe('Your work');
  });

  it('announces a badge count in the accessible name', async () => {
    const view = await withTheme(
      <Segmented
        segments={[SEGMENTS[0], { ...SEGMENTS[1], badge: 2 }]}
        value="customer"
        onChange={jest.fn()}
      />,
    );

    expect(view.getByLabelText('Your work, 2 waiting')).toBeTruthy();
  });
});
