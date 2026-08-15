import { act, render, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

import { secureStorage } from '@/lib/secure-storage';
import {
  THEME_STORAGE_KEY,
  ThemeProvider,
  isThemeMode,
  useTheme,
} from '@/theme/theme';
import { darkPalette, lightPalette } from '@/theme/tokens';

const mockScheme = jest.fn<'light' | 'dark' | null, []>(() => 'light');

jest.mock('react-native/Libraries/Utilities/useColorScheme', () => ({
  __esModule: true,
  default: () => mockScheme(),
}));

function Probe() {
  const { mode, scheme, palette, setMode } = useTheme();

  return (
    <>
      <Text testID="mode">{mode}</Text>
      <Text testID="scheme">{scheme}</Text>
      <Text testID="ground">{palette.ground}</Text>
      <Text testID="set-dark" onPress={() => setMode('dark')}>
        dark
      </Text>
      <Text testID="set-system" onPress={() => setMode('system')}>
        system
      </Text>
    </>
  );
}

beforeEach(async () => {
  await secureStorage.remove(THEME_STORAGE_KEY);
  mockScheme.mockReturnValue('light');
});

describe('theme resolution', () => {
  it('follows the device when the mode is system', async () => {
    mockScheme.mockReturnValue('dark');

    const view = await render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await waitFor(() => expect(view.getByTestId('mode')).toHaveTextContent('system'));
    expect(view.getByTestId('scheme')).toHaveTextContent('dark');
    expect(view.getByTestId('ground')).toHaveTextContent(darkPalette.ground);
  });

  it('overrides the device when a mode is chosen', async () => {
    mockScheme.mockReturnValue('dark');

    const view = await render(
      <ThemeProvider initialMode="light">
        <Probe />
      </ThemeProvider>,
    );

    expect(view.getByTestId('scheme')).toHaveTextContent('light');
    expect(view.getByTestId('ground')).toHaveTextContent(lightPalette.ground);
  });

  it('treats an unset device scheme as light', async () => {
    mockScheme.mockReturnValue(null);

    const view = await render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await waitFor(() => expect(view.getByTestId('scheme')).toHaveTextContent('light'));
  });

  it('gives dark mode its own palette rather than inverting light', () => {
    // Dark is designed, not derived. If these ever match, somebody has replaced
    // the dark palette with a transform of the light one.
    expect(darkPalette.primary).not.toBe(lightPalette.primary);
    expect(darkPalette.onPrimary).not.toBe(lightPalette.onPrimary);
  });
});

describe('theme switching', () => {
  it('applies a new mode immediately', async () => {
    const view = await render(
      <ThemeProvider initialMode="system">
        <Probe />
      </ThemeProvider>,
    );

    await act(async () => {
      view.getByTestId('set-dark').props.onPress();
    });

    expect(view.getByTestId('mode')).toHaveTextContent('dark');
    expect(view.getByTestId('ground')).toHaveTextContent(darkPalette.ground);
  });

  it('persists the choice', async () => {
    const view = await render(
      <ThemeProvider initialMode="system">
        <Probe />
      </ThemeProvider>,
    );

    await act(async () => {
      view.getByTestId('set-dark').props.onPress();
    });

    await waitFor(async () =>
      expect(await secureStorage.get(THEME_STORAGE_KEY)).toBe('dark'),
    );
  });

  it('persists the preference and not the resolved scheme', async () => {
    // Storing "dark" for somebody who picked "system" on a dark device would pin
    // them to dark the first time they switched their phone to light.
    mockScheme.mockReturnValue('dark');

    const view = await render(
      <ThemeProvider initialMode="light">
        <Probe />
      </ThemeProvider>,
    );

    await act(async () => {
      view.getByTestId('set-system').props.onPress();
    });

    await waitFor(async () =>
      expect(await secureStorage.get(THEME_STORAGE_KEY)).toBe('system'),
    );
  });

  it('restores a persisted choice on the next launch', async () => {
    await secureStorage.set(THEME_STORAGE_KEY, 'dark');

    const view = await render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await waitFor(() => expect(view.getByTestId('mode')).toHaveTextContent('dark'));
    expect(view.getByTestId('scheme')).toHaveTextContent('dark');
  });

  it('ignores a stored value that is not a mode', async () => {
    await secureStorage.set(THEME_STORAGE_KEY, 'chartreuse');

    const view = await render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );

    await waitFor(() => expect(view.getByTestId('mode')).toHaveTextContent('system'));
  });
});

describe('isThemeMode', () => {
  it('accepts the three modes and nothing else', () => {
    expect(isThemeMode('system')).toBe(true);
    expect(isThemeMode('light')).toBe(true);
    expect(isThemeMode('dark')).toBe(true);
    expect(isThemeMode('sepia')).toBe(false);
    expect(isThemeMode(null)).toBe(false);
  });
});
