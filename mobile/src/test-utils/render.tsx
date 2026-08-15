/**
 * Rendering a component the way the app does.
 *
 * Everything visual depends on a theme and on safe-area insets, so a test that
 * renders a bare component is testing something the app never shows. This wraps
 * both, with fixed insets, so layout that depends on a notch is deterministic
 * rather than dependent on whatever the test renderer defaults to.
 */

import { render } from '@testing-library/react-native';
import type { ReactElement } from 'react';
import { SafeAreaProvider, type Metrics } from 'react-native-safe-area-context';

import { ThemeProvider, type ThemeMode } from '@/theme/theme';

/** A tall phone with a notch and a home indicator, which is the case where
 *  bottom-bar clearance is easiest to get wrong. */
export const METRICS: Metrics = {
  frame: { x: 0, y: 0, width: 390, height: 844 },
  insets: { top: 47, left: 0, right: 0, bottom: 34 },
};

/** A small phone with neither, for checking nothing depends on an inset. */
export const SMALL_METRICS: Metrics = {
  frame: { x: 0, y: 0, width: 320, height: 568 },
  insets: { top: 20, left: 0, right: 0, bottom: 0 },
};

export function renderWithProviders(
  ui: ReactElement,
  options: { mode?: ThemeMode; metrics?: Metrics } = {},
) {
  const { mode = 'light', metrics = METRICS } = options;

  return render(
    <SafeAreaProvider initialMetrics={metrics}>
      <ThemeProvider initialMode={mode}>{ui}</ThemeProvider>
    </SafeAreaProvider>,
  );
}
