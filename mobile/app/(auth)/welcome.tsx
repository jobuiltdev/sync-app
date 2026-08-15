import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { usePalette } from '@/theme/theme';
import { radii, spacing } from '@/theme/tokens';

/** The six verticals, as the marketing line already promises them. Static on
 *  purpose: this screen renders before there is a session, so it cannot fetch
 *  the catalog, and a spinner is a poor first impression of a product. */
const VERTICALS: { icon: IconName; label: string }[] = [
  { icon: 'dispatch', label: 'Courier' },
  { icon: 'cleaning', label: 'Cleaning' },
  { icon: 'errands', label: 'Errands' },
  { icon: 'handyman', label: 'Home services' },
  { icon: 'beauty', label: 'Beauty' },
  { icon: 'laundry', label: 'Laundry' },
];

/**
 * The first screen anybody sees.
 *
 * Type carries it. No hero image, because there is no photography in this
 * product and a stock photo would be the least honest thing on the screen. The
 * six category tiles do the work an image would: they say what this is for,
 * immediately and specifically.
 */
export default function WelcomeScreen() {
  const router = useRouter();
  const palette = usePalette();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: palette.ground }]}>
      <View style={styles.content}>
        <View style={styles.hero}>
          <Text variant="overline" tone="primary">
            Sync
          </Text>
          <Text variant="title1" accessibilityRole="header">
            Everyday services, one app.
          </Text>
          <Text variant="body" tone="muted">
            Booked from one place, done by people you can trust.
          </Text>
        </View>

        <View
          accessibilityRole="list"
          accessibilityLabel="Services available on Sync"
          style={styles.grid}
        >
          {VERTICALS.map((vertical) => (
            <View
              key={vertical.label}
              accessibilityRole="text"
              style={[styles.tile, { backgroundColor: palette.surface, borderColor: palette.hairline }]}
            >
              <Icon name={vertical.icon} size={22} color={palette.primary} />
              <Text variant="caption" tone="soft" weight="medium" numberOfLines={1}>
                {vertical.label}
              </Text>
            </View>
          ))}
        </View>

        <View style={styles.actions}>
          <Button label="Create an account" onPress={() => router.push('/register')} />
          <Button
            label="I already have an account"
            variant="secondary"
            onPress={() => router.push('/login')}
          />
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { flex: 1, padding: spacing.xl, justifyContent: 'space-between', gap: spacing.xl },
  hero: { paddingTop: spacing.xxl, gap: spacing.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  tile: {
    // Three across on a small phone, and it stays three across on a large one
    // rather than stretching into letterboxes.
    flexBasis: '31%',
    flexGrow: 1,
    alignItems: 'flex-start',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.card,
    borderWidth: StyleSheet.hairlineWidth * 2,
  },
  actions: { gap: spacing.md, paddingBottom: spacing.sm },
});
