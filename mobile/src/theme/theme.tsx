/**
 * Theme resolution and persistence.
 *
 * Three modes, which is what a person expects from a modern app: follow the
 * device, or override it in either direction. The override is persisted, so the
 * choice survives a restart; without that, "dark" is a setting the app forgets
 * every time it is closed, which is worse than not offering it.
 *
 * The stored value is the *preference*, never the resolved scheme. Persisting
 * "dark" when the user picked "system" on a dark device would silently pin them
 * to dark the first time they switched their phone to light.
 */

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useColorScheme } from 'react-native';

import { secureStorage } from '@/lib/secure-storage';
import { type Palette, darkPalette, lightPalette } from '@/theme/tokens';

export type ThemeMode = 'system' | 'light' | 'dark';
export type ColorScheme = 'light' | 'dark';

export const THEME_MODES: ThemeMode[] = ['system', 'light', 'dark'];

/** Kept beside the session keys rather than in AsyncStorage, which would mean a
 *  second storage dependency for one short string. Nothing here is secret; the
 *  keychain is simply the storage this app already has. */
export const THEME_STORAGE_KEY = 'sync.appearance';

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'system' || value === 'light' || value === 'dark';
}

interface ThemeContextValue {
  /** What the person chose. */
  mode: ThemeMode;
  /** What that resolves to right now, once the device is taken into account. */
  scheme: ColorScheme;
  palette: Palette;
  setMode: (mode: ThemeMode) => void;
  /** False until the stored preference has been read. Screens do not need to
   *  wait for it: the device scheme is a good enough first paint, and the
   *  correction lands within a frame or two. */
  isHydrated: boolean;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({
  children,
  /** Test seam. Lets a test render a known scheme without mocking the OS. */
  initialMode,
}: {
  children: ReactNode;
  initialMode?: ThemeMode;
}) {
  const deviceScheme = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>(initialMode ?? 'system');
  const [isHydrated, setHydrated] = useState(initialMode !== undefined);

  useEffect(() => {
    if (initialMode !== undefined) return;

    let cancelled = false;

    void (async () => {
      const stored = await secureStorage.get(THEME_STORAGE_KEY);
      if (cancelled) return;
      if (isThemeMode(stored)) setModeState(stored);
      setHydrated(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [initialMode]);

  const setMode = useCallback((next: ThemeMode) => {
    // Applied immediately and persisted in the background. Waiting on the
    // keychain before repainting would make a theme tap feel broken.
    setModeState(next);
    void secureStorage.set(THEME_STORAGE_KEY, next);
  }, []);

  const scheme: ColorScheme = mode === 'system' ? (deviceScheme ?? 'light') : mode;

  const value = useMemo<ThemeContextValue>(
    () => ({
      mode,
      scheme,
      palette: scheme === 'dark' ? darkPalette : lightPalette,
      setMode,
      isHydrated,
    }),
    [mode, scheme, setMode, isHydrated],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (value === null) {
    throw new Error('useTheme must be used inside a ThemeProvider.');
  }
  return value;
}

/** The common case: a component wants colours and nothing else. */
export function usePalette(): Palette {
  return useTheme().palette;
}

export const THEME_MODE_LABELS: Record<ThemeMode, string> = {
  system: 'System',
  light: 'Light',
  dark: 'Dark',
};

export const THEME_MODE_HINTS: Record<ThemeMode, string> = {
  system: 'Follows your device setting',
  light: 'Always light',
  dark: 'Always dark',
};
