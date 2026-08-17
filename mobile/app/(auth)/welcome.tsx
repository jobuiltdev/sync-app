import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { HeroArt } from '@/components/brand/HeroArt';
import { Button } from '@/components/ui/Button';
import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { Card } from '@/components/ui/Surface';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * The landing screen.
 *
 * The first thing anybody sees, and the only screen in the app whose job is to
 * sell rather than to work. It answers four questions in order: what is this,
 * what can I get, why should I trust you, and what happens if I start.
 *
 * **Every claim on it is one the product can keep.** The designed version
 * carried a "20% off with SYNC20" band; there is no promo, coupon or discount
 * anywhere in the backend, so a customer who copied that code would have been
 * charged full price. It is left out rather than mocked up, because the one
 * screen whose purpose is to make a promise is the worst place to make one the
 * system cannot honour.
 */

/** All six, because all six are bookable. The mockup showed four, which would
 *  have under-sold the catalog to somebody deciding whether to sign up. */
const SERVICES: { icon: IconName; name: string; blurb: string }[] = [
  { icon: 'dispatch', name: 'Courier', blurb: 'Send anything, anywhere' },
  { icon: 'errands', name: 'Errands', blurb: 'Shopping and pickups' },
  { icon: 'cleaning', name: 'Cleaning', blurb: 'Home and office' },
  { icon: 'handyman', name: 'Home', blurb: 'Repairs and fittings' },
  { icon: 'beauty', name: 'Beauty', blurb: 'Hair, nails and skin' },
  { icon: 'laundry', name: 'Laundry', blurb: 'Washed and pressed' },
];

const TRUST: { icon: IconName; label: string }[] = [
  { icon: 'profile', label: 'Vetted\nprofessionals' },
  { icon: 'shield', label: 'Secure\npayments' },
  { icon: 'clock', label: 'You confirm\nthe work' },
];

const STEPS: { icon: IconName; title: string; body: string }[] = [
  { icon: 'search', title: 'Choose a service', body: 'Pick what you need' },
  { icon: 'clock', title: 'Book and confirm', body: 'At a time that works' },
  { icon: 'check', title: 'We get it done', body: 'You confirm when it is' },
];

export default function WelcomeScreen() {
  const router = useRouter();
  const palette = usePalette();

  return (
    <SafeAreaView style={[styles.screen, { backgroundColor: palette.ground }]} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.wordmark}>
          <View style={[styles.mark, { backgroundColor: palette.primary }]}>
            <Text variant="body" weight="bold" style={{ color: palette.onPrimary }}>
              S
            </Text>
          </View>
          <Text variant="title3" weight="bold" style={styles.wordmarkText}>
            SYNC
          </Text>
        </View>

        <View style={styles.hero}>
          <Text variant="display" accessibilityRole="header">
            Everything you need.{'\n'}All in{' '}
            <Text variant="display" tone="primary">
              Sync.
            </Text>
          </Text>
          <Text variant="body" tone="muted">
            Courier, home services, laundry, cleaning and more. Simple. Reliable.
            On your time.
          </Text>
        </View>

        <HeroArt />

        <Card padding="none">
          <View style={styles.grid}>
            {SERVICES.map((service) => (
              <View key={service.name} style={styles.tile}>
                <View style={[styles.tilePlate, { backgroundColor: palette.primarySoft }]}>
                  <Icon name={service.icon} size={24} color={palette.primary} />
                </View>
                <Text variant="footnote" weight="semibold" center numberOfLines={1}>
                  {service.name}
                </Text>
                <Text variant="caption" tone="muted" center numberOfLines={2}>
                  {service.blurb}
                </Text>
              </View>
            ))}
          </View>

          <View style={[styles.trust, { borderTopColor: palette.hairlineSoft }]}>
            {TRUST.map((item) => (
              <View key={item.label} style={styles.trustItem}>
                <Icon name={item.icon} size={18} color={palette.primary} />
                <Text variant="caption" tone="soft" center>
                  {item.label}
                </Text>
              </View>
            ))}
          </View>
        </Card>

        <View style={styles.how}>
          <Text variant="title3">How it works</Text>
          <View style={styles.steps}>
            {STEPS.map((step, index) => (
              <View key={step.title} style={styles.step}>
                <View style={[styles.stepPlate, { backgroundColor: palette.surface, borderColor: palette.hairline }]}>
                  <Icon name={step.icon} size={20} color={palette.primary} />
                  <View style={[styles.stepNumber, { backgroundColor: palette.primary }]}>
                    <Text variant="micro" weight="bold" style={{ color: palette.onPrimary }}>
                      {index + 1}
                    </Text>
                  </View>
                </View>
                <Text variant="caption" weight="semibold" center numberOfLines={2}>
                  {step.title}
                </Text>
                <Text variant="caption" tone="muted" center numberOfLines={2}>
                  {step.body}
                </Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      {/* Pinned rather than scrolled to. The point of this screen is the next
          step, and making somebody reach the bottom to find it is a worse
          landing page however good the copy above it is. */}
      <View style={[styles.footer, { backgroundColor: palette.ground, borderTopColor: palette.hairlineSoft }]}>
        <Button label="Get started" onPress={() => router.push('/register')} />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Sign in to an existing account"
          onPress={() => router.push('/login')}
          hitSlop={spacing.sm}
          style={styles.signIn}
        >
          <Text variant="footnote" tone="muted">
            Already have an account?{' '}
            <Text variant="footnote" tone="primary" weight="semibold">
              Sign in
            </Text>
          </Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: spacing.xl, paddingBottom: spacing.xl, gap: spacing.xl },
  wordmark: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  mark: {
    width: 30,
    height: 30,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wordmarkText: { letterSpacing: 4 },
  hero: { gap: spacing.md },
  grid: { flexDirection: 'row', flexWrap: 'wrap', padding: spacing.md },
  tile: {
    // Three across, two rows. Percentage basis so it holds on a 320pt phone
    // and does not stretch into letterboxes on a large one.
    width: '33.33%',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.xs,
  },
  tilePlate: {
    width: 46,
    height: 46,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xxs,
  },
  trust: {
    flexDirection: 'row',
    borderTopWidth: StyleSheet.hairlineWidth * 2,
    paddingVertical: spacing.md,
  },
  trustItem: { flex: 1, alignItems: 'center', gap: spacing.xs },
  how: { gap: spacing.lg },
  steps: { flexDirection: 'row', gap: spacing.sm },
  step: { flex: 1, alignItems: 'center', gap: spacing.xs },
  stepPlate: {
    width: 48,
    height: 48,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth * 2,
    marginBottom: spacing.xs,
  },
  stepNumber: {
    position: 'absolute',
    bottom: -6,
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footer: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
    gap: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth * 2,
  },
  signIn: { alignItems: 'center', paddingBottom: spacing.xs },
});
