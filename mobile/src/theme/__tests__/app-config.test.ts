/**
 * Native appearance configuration.
 *
 * This exists because of a bug that no test of the theme code could have
 * caught. `ThemeProvider` resolved "system" correctly the whole time, but
 * `app.json` carried `userInterfaceStyle: "light"`, which locks the app's
 * appearance at the native level. `useColorScheme()` therefore always returned
 * light, and choosing "System" on a dark phone flipped the app to light.
 *
 * The setting had been there since M0 and was invisible until there was a dark
 * mode to notice it against. Configuration that silently overrides application
 * behaviour is worth a test precisely because nothing else in the suite reaches
 * it.
 */

import appConfig from '../../../app.json';
import { darkPalette, lightPalette } from '@/theme/tokens';

/** The plugin entry for a package, as a plain shape. The JSON import gives each
 *  entry a precise literal type, which is more than a config assertion needs. */
function pluginConfig(name: string): Record<string, unknown> | null {
  for (const plugin of appConfig.expo.plugins as unknown[]) {
    if (Array.isArray(plugin) && plugin[0] === name) {
      return plugin[1] as Record<string, unknown>;
    }
  }
  return null;
}

describe('app.json appearance', () => {
  it('lets the app follow the device', () => {
    // "light" or "dark" pin the native appearance and make the ThemeProvider's
    // system mode a lie. Only "automatic" allows useColorScheme to report what
    // the device is actually set to.
    expect(appConfig.expo.userInterfaceStyle).toBe('automatic');
  });

  it('asks for location only in the foreground', () => {
    const location = pluginConfig('expo-location');

    expect(location).not.toBeNull();
    // Background location is a different permission, a different review
    // conversation, and something this product has no use for.
    expect(location!.isIosBackgroundLocationEnabled).toBe(false);
    expect(location!.isAndroidBackgroundLocationEnabled).toBe(false);
  });

  it('explains what location is for in the permission dialog', () => {
    const message = String(pluginConfig('expo-location')!.locationWhenInUsePermission);

    // The system dialog is the only place most people read about this, so it
    // says what it is for and what happens to it.
    expect(message).toMatch(/job/i);
    expect(message).toMatch(/never shared|never leaves/i);
  });

  it('stays on the pinned Expo SDK', () => {
    expect(appConfig.expo.name).toBe('Sync');
  });
});

describe('native splash', () => {
  const splash = () => pluginConfig('expo-splash-screen')!;

  it('matches the light ground exactly', () => {
    // The native splash and the first React Native frame have to be the same
    // colour or the handoff shows a seam. These were left on the pre-M9 palette
    // until this milestone.
    expect(splash().backgroundColor).toBe(lightPalette.ground);
  });

  it('has a dark variant matching the dark ground', () => {
    const dark = splash().dark as Record<string, unknown>;

    expect(dark).toBeDefined();
    expect(dark.backgroundColor).toBe(darkPalette.ground);
  });

  it('uses no colour that is not a palette ground', () => {
    const dark = splash().dark as Record<string, unknown>;
    const used = [splash().backgroundColor, dark.backgroundColor];

    expect(used).toEqual([lightPalette.ground, darkPalette.ground]);
  });
});
