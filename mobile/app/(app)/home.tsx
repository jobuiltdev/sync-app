import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { ServiceSummary } from '@/api/endpoints/catalog';
import { Button } from '@/components/ui/Button';
import { useCurrentUser, useSignOut } from '@/features/auth/hooks';
import { useCategories } from '@/features/catalog/hooks';
import { formatPriceFrom } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Foundation screen.
 *
 * Proves the core domain is consumable end to end: the catalog loads from the
 * API, prices render through one formatter, and the signed-in account is
 * identified. The real customer home, with search and booking entry points,
 * replaces this once the booking flow exists.
 */
export default function HomeScreen() {
  const router = useRouter();
  const { data: user } = useCurrentUser();
  const categories = useCategories();
  const signOut = useSignOut();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>Signed in as {user?.email ?? 'your account'}</Text>
          <Text style={styles.title}>What do you need?</Text>
        </View>

        {categories.isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : categories.error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load services</Text>
            <Text style={styles.body}>{categories.error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => categories.refetch()} />
          </View>
        ) : categories.data.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>No services yet</Text>
            <Text style={styles.body}>Services will appear here once they are published.</Text>
          </View>
        ) : (
          categories.data.map((category) => (
            <View key={category.id} style={styles.section}>
              <Text style={styles.sectionTitle}>{category.name}</Text>
              {category.services.length === 0 ? (
                <Text style={styles.muted}>Nothing available here yet.</Text>
              ) : (
                category.services.map((service) => (
                  <ServiceRow
                    key={service.id}
                    service={service}
                    onPress={() => router.push(`/book/${service.slug}`)}
                  />
                ))
              )}
            </View>
          ))
        )}

        <Button label="Your bookings" variant="secondary" onPress={() => router.push('/bookings')} />

        <Button
          label="Sign out"
          variant="secondary"
          loading={signOut.isPending}
          onPress={() => signOut.mutate()}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function ServiceRow({ service, onPress }: { service: ServiceSummary; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${service.name}, ${formatPriceFrom(service.base_price_kobo, service.pricing_model)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      <View style={styles.rowText}>
        <Text style={styles.rowTitle}>{service.name}</Text>
        {service.summary ? <Text style={styles.muted}>{service.summary}</Text> : null}
      </View>
      <Text style={styles.price}>
        {formatPriceFrom(service.base_price_kobo, service.pricing_model)}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.xl },
  header: { gap: spacing.xs, paddingTop: spacing.lg },
  eyebrow: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  section: { gap: spacing.sm },
  sectionTitle: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.md,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: 64,
  },
  rowPressed: { backgroundColor: colors.surfaceSunk },
  rowText: { flexShrink: 1, gap: 2 },
  rowTitle: { fontSize: fontSizes.body, fontWeight: fontWeights.medium, color: colors.ink },
  price: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.semibold,
    color: colors.accent,
    // Prices line up in a column, so tabular figures stop them shifting width.
    fontVariant: ['tabular-nums'],
    textAlign: 'right',
  },
});
