import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { OfferSummary } from '@/api/endpoints/offers';
import { offerStatusLabel } from '@/api/endpoints/offers';
import { Button } from '@/components/ui/Button';
import { useOffers } from '@/features/offers/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Provider inbox.
 *
 * Polled rather than pushed, because there is no notification infrastructure yet
 * and an offer nobody sees is a job lost. Everything shown comes from the server,
 * including whether an offer can still be answered.
 */
export default function OffersScreen() {
  const router = useRouter();
  const { data, isPending, error, refetch, isFetching } = useOffers();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Jobs offered to you</Text>
          {isFetching && !isPending ? <Text style={styles.muted}>Checking for new jobs</Text> : null}
        </View>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your offers</Text>
            <Text style={styles.body}>{error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => refetch()} />
          </View>
        ) : data.results.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Nothing waiting</Text>
            <Text style={styles.body}>
              New jobs matching your services and areas will appear here.
            </Text>
          </View>
        ) : (
          data.results.map((offer) => (
            <OfferRow
              key={offer.id}
              offer={offer}
              onPress={() => router.push(`/offer/${offer.id}`)}
            />
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function OfferRow({ offer, onPress }: { offer: OfferSummary; onPress: () => void }) {
  const where = [offer.area, offer.lga].filter(Boolean).join(', ');

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${offer.service_name} in ${where || offer.state}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
    >
      <View style={styles.rowTop}>
        <Text style={styles.cardTitle}>{offer.service_name}</Text>
        {offer.kind === 'DIRECT' ? (
          <View style={styles.pill}>
            <Text style={styles.pillText}>Asked for you</Text>
          </View>
        ) : null}
      </View>
      <Text style={styles.muted}>{where || offer.state}</Text>
      <Text style={styles.muted}>{offerStatusLabel(offer.status)}</Text>
      <Text style={styles.reference}>{offer.booking_reference}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.md },
  header: { gap: spacing.xs, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  cardPressed: { backgroundColor: colors.surfaceSunk },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft, gap: spacing.md },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  reference: {
    fontSize: fontSizes.caption,
    color: colors.inkMuted,
    fontVariant: ['tabular-nums'],
    paddingTop: spacing.xs,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radii.pill,
    backgroundColor: colors.accentSoft,
  },
  pillText: { fontSize: fontSizes.caption, fontWeight: fontWeights.medium, color: colors.accent },
});
