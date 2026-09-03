/**
 * The landing hero.
 *
 * ### Dropping in the illustration
 *
 * The designed hero (the van, boxes, laundry, phone and city) is a rendered
 * illustration that does not exist in this repository. To use it:
 *
 *   1. Export it to `assets/images/hero-landing.png`, ideally 1200px wide with
 *      a transparent background so it sits on both the light and dark ground.
 *   2. Uncomment the `require` and the `Image` below.
 *
 * That is the whole change. Nothing else on the landing screen depends on it,
 * which is why the screen is finished and shipping without it rather than
 * blocked behind an asset.
 *
 * Until then this renders a composition from the app's own icon set: the four
 * headline services on warm plates over a soft wash. It is deliberately not
 * pretending to be the illustration. It is a different, simpler thing that
 * belongs to the same design system, and it will not look broken if the
 * illustration never arrives.
 */

import { StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/ui/Icon';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

// import { Image } from 'react-native';
// const HERO = require('@/assets/images/hero-landing.png');

/** The four the mockup leads with. The full six are in the grid below the hero,
 *  so nothing is hidden by choosing four here. */
const LEAD: { icon: IconName; offset: number }[] = [
  { icon: 'dispatch', offset: 0 },
  { icon: 'handyman', offset: 18 },
  { icon: 'laundry', offset: 0 },
  { icon: 'cleaning', offset: 18 },
];

export function HeroArt() {
  const palette = usePalette();

  // When the illustration exists, this whole block becomes:
  //   return <Image source={HERO} style={styles.image} resizeMode="contain" />;

  return (
    <View
      style={styles.frame}
      accessible
      accessibilityRole="image"
      accessibilityLabel="Courier, home services, laundry and cleaning"
    >
      <View style={[styles.wash, { backgroundColor: palette.primarySoft }]} />

      <View style={styles.row}>
        {LEAD.map(({ icon, offset }) => (
          <View
            key={icon}
            style={[
              styles.plate,
              {
                backgroundColor: palette.surface,
                borderColor: palette.hairline,
                marginTop: offset,
              },
            ]}
          >
            <Icon name={icon} size={30} color={palette.primary} strokeWidth={1.6} />
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  frame: { height: 168, justifyContent: 'center', alignItems: 'center' },
  image: { width: '100%', height: 200 },
  wash: {
    ...StyleSheet.absoluteFill,
    // A soft arc behind the plates, echoing the mockup's tinted backdrop
    // without pretending to be its artwork.
    borderRadius: radii.sheet,
    top: 18,
    bottom: 18,
    opacity: 0.55,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  plate: {
    width: 66,
    height: 66,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
});
