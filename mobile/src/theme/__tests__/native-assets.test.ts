/**
 * Native icon and splash packaging.
 *
 * The artwork itself is rasterised from `assets/brand/sync-mark.svg`, so its
 * geometry is already guarded by the brand tests. What this covers is the wiring
 * around it: that every path the config names actually exists, that the
 * placeholders are gone rather than merely unreferenced, and that the identifiers
 * and platform settings nothing in this milestone should have touched are intact.
 *
 * A missing icon path does not fail a build until a native one is produced,
 * which is the sort of thing that is discovered at the worst possible moment.
 */

import { existsSync } from 'node:fs';
import { join } from 'node:path';

import appConfig from '../../../app.json';
import { darkPalette, lightPalette } from '@/theme/tokens';

const expo = appConfig.expo;
const root = join(__dirname, '..', '..', '..');
const asset = (path: string) => join(root, path.replace('./', ''));

function pluginConfig(name: string): Record<string, unknown> {
  for (const plugin of expo.plugins as unknown[]) {
    if (Array.isArray(plugin) && plugin[0] === name) {
      return plugin[1] as Record<string, unknown>;
    }
  }
  throw new Error(`no plugin config for ${name}`);
}

const splash = () => pluginConfig('expo-splash-screen');

describe('every configured asset exists', () => {
  it('resolves every icon path', () => {
    const ios = expo.ios.icon as Record<string, string>;
    const adaptive = expo.android.adaptiveIcon as Record<string, string>;

    for (const path of [
      expo.icon,
      ios.light,
      ios.dark,
      ios.tinted,
      expo.android.icon,
      adaptive.foregroundImage,
      adaptive.monochromeImage,
      expo.web.favicon,
    ]) {
      expect(existsSync(asset(path))).toBe(true);
    }
  });

  it('resolves both splash images', () => {
    const dark = splash().dark as Record<string, unknown>;

    expect(existsSync(asset(splash().image as string))).toBe(true);
    expect(existsSync(asset(dark.image as string))).toBe(true);
  });
});

describe('the placeholders are gone', () => {
  it('has deleted the obsolete files rather than leaving them unreferenced', () => {
    // An unreferenced placeholder is still shipped in the bundle and still turns
    // up in a search for the real asset.
    for (const name of ['android-icon-background.png', 'splash-icon.png']) {
      expect(existsSync(join(root, 'assets', 'images', name))).toBe(false);
    }
  });

  it('names neither of them anywhere in the config', () => {
    const body = JSON.stringify(appConfig);

    expect(body).not.toContain('android-icon-background');
    expect(body).not.toContain('splash-icon.png');
  });

  it('no longer declares an adaptive background image', () => {
    // A flat colour is what the adaptive spec wants; a background image was the
    // template's placeholder artwork.
    expect(expo.android.adaptiveIcon).not.toHaveProperty('backgroundImage');
  });
});

describe('the icon configuration', () => {
  it('gives iOS all three appearances', () => {
    const ios = expo.ios.icon as Record<string, string>;

    expect(Object.keys(ios).sort()).toEqual(['dark', 'light', 'tinted']);
  });

  it('keeps the top-level icon as the light artwork', () => {
    expect(expo.icon).toBe('./assets/images/icon.png');
  });

  it('gives older Android launchers the same fallback', () => {
    // Launchers below the adaptive era use this and nothing else.
    expect(expo.android.icon).toBe(expo.icon);
  });

  it('sets the adaptive background to the light ground', () => {
    const adaptive = expo.android.adaptiveIcon as Record<string, string>;

    expect(adaptive.backgroundColor).toBe(lightPalette.ground);
  });

  it('carries a monochrome layer for themed icons', () => {
    const adaptive = expo.android.adaptiveIcon as Record<string, string>;

    expect(adaptive.monochromeImage).toContain('android-icon-monochrome');
  });
});

describe('the splash configuration', () => {
  it('draws the light and dark marks on their own grounds', () => {
    const dark = splash().dark as Record<string, unknown>;

    expect(splash().backgroundColor).toBe(lightPalette.ground);
    expect(dark.backgroundColor).toBe(darkPalette.ground);
    expect(splash().image).toContain('splash-icon-light');
    expect(dark.image).toContain('splash-icon-dark');
  });

  it('matches the mark size the launch screen draws', () => {
    // The animated mark is 86 points. The splash image maps the same 64 unit
    // viewBox, so an equal width makes the native mark and the first animated
    // frame the same size in the same place.
    const dark = splash().dark as Record<string, unknown>;

    expect(splash().imageWidth).toBe(86);
    expect(dark.imageWidth).toBe(86);
  });

  it('contains rather than crops', () => {
    const dark = splash().dark as Record<string, unknown>;

    expect(splash().resizeMode).toBe('contain');
    expect(dark.resizeMode).toBe('contain');
  });
});

describe('nothing unrelated moved', () => {
  it('keeps both platform identifiers', () => {
    expect(expo.ios.bundleIdentifier).toBe('ng.sync.app');
    expect(expo.android.package).toBe('ng.sync.app');
  });

  it('keeps the predictive back setting', () => {
    expect(expo.android.predictiveBackGestureEnabled).toBe(false);
  });

  it('keeps tablet support off and the appearance automatic', () => {
    expect(expo.ios.supportsTablet).toBe(false);
    expect(expo.userInterfaceStyle).toBe('automatic');
  });
});
