import { processColor } from 'react-native';

import { renderWithProviders } from '@/test-utils/render';

import { SyncMark } from '../SyncMark';

describe('SyncMark', () => {
  it('keeps both routes independently addressable', async () => {
    const view = await renderWithProviders(<SyncMark />);

    expect(view.getByTestId('sync-route-upper')).toBeTruthy();
    expect(view.getByTestId('sync-route-lower')).toBeTruthy();
  });

  it('uses the resolved theme accent by default', async () => {
    const light = await renderWithProviders(<SyncMark />);
    const dark = await renderWithProviders(<SyncMark />, { mode: 'dark' });

    expect(light.getByTestId('sync-route-upper').props.stroke.payload).toBe(processColor('#B54A22'));
    expect(dark.getByTestId('sync-route-upper').props.stroke.payload).toBe(processColor('#F0794A'));
  });

  it('accepts presentation overrides', async () => {
    const view = await renderWithProviders(
      <SyncMark accessibilityLabel="Sync loading" color="#000000" size={32} />,
    );

    expect(view.getByLabelText('Sync loading').props.width).toBe(32);
    expect(view.getByTestId('sync-route-lower').props.stroke.payload).toBe(processColor('#000000'));
  });
});
