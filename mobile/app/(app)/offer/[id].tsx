import { useLocalSearchParams, useRouter } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { offerStatusLabel } from '@/api/endpoints/offers';
import { Button } from '@/components/ui/Button';
import { useAcceptOffer, useDeclineOffer, useOffer } from '@/features/offers/hooks';
import { needsVerification, toOfferOutcome } from '@/features/offers/outcomes';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * One job, and the decision on it.
 *
 * Whether the buttons appear is the server's call, carried on `is_actionable`.
 * Deciding locally would mean a provider tapping accept on something the server
 * has already given to somebody else.
 */
export default function OfferDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { data: offer, isPending, error } = useOffer(id);
  const accept = useAcceptOffer();
  const decline = useDeclineOffer();

  if (isPending) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator color={colors.accent} />
      </SafeAreaView>
    );
  }

  if (error) {
    return (
      <SafeAreaView style={styles.centred}>
        <Text style={styles.body}>{error.message}</Text>
        <Button label="Back to offers" variant="secondary" onPress={() => router.back()} />
      </SafeAreaView>
    );
  }

  const outcome = toOfferOutcome(accept.error) ?? toOfferOutcome(decline.error);
  const accepted = accept.isSuccess;
  const declined = decline.isSuccess;

  // The offer is over, either because it just resolved or because the server said
  // so. Either way the answer is to go back, not to try again.
  const finished = accepted || declined || outcome?.isFinal || !offer.is_actionable;

  const where = [offer.area, offer.lga].filter(Boolean).join(', ');

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.reference}>{offer.booking_reference}</Text>
          <Text style={styles.title}>{offer.service_name}</Text>
          <Text style={styles.muted}>{offerStatusLabel(offer.status)}</Text>
        </View>

        {accepted ? (
          <View accessibilityRole="alert" style={[styles.card, styles.cardGood]}>
            <Text style={styles.cardTitle}>The job is yours</Text>
            <Text style={styles.body}>It is now in your jobs list.</Text>
            <Button label="Go to my jobs" onPress={() => router.replace('/bookings')} />
          </View>
        ) : null}

        {declined ? (
          <View accessibilityRole="alert" style={styles.card}>
            <Text style={styles.cardTitle}>Declined</Text>
            <Text style={styles.body}>This job will not appear in your inbox again.</Text>
          </View>
        ) : null}

        {outcome ? (
          <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
            <Text style={styles.body}>{outcome.message}</Text>
            {needsVerification(outcome) ? (
              <Button
                label="Verify my details"
                onPress={() => router.push('/verify-phone')}
              />
            ) : null}
          </View>
        ) : null}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Where</Text>
          <Text style={styles.body}>{offer.street_address}</Text>
          <Text style={styles.muted}>{offer.landmark}</Text>
          <Text style={styles.muted}>{where || offer.state}</Text>
          {offer.directions_note ? (
            <Text style={styles.muted}>{offer.directions_note}</Text>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>What is being asked for</Text>
          {Object.entries(offer.details).map(([key, value]) => (
            <View key={key} style={styles.detailRow}>
              <Text style={styles.muted}>{humanise(key)}</Text>
              <Text style={styles.detailValue}>{renderValue(value)}</Text>
            </View>
          ))}
        </View>

        {finished ? (
          <Button label="Back to offers" variant="secondary" onPress={() => router.back()} />
        ) : (
          <>
            <Button
              label="Accept this job"
              loading={accept.isPending}
              disabled={decline.isPending}
              onPress={() => accept.mutate({ id })}
            />
            <Button
              label="Decline"
              variant="secondary"
              loading={decline.isPending}
              disabled={accept.isPending}
              onPress={() => decline.mutate({ id })}
            />
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function humanise(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
}

function renderValue(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) return value.join(', ');
  return String(value);
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  centred: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.ground,
    padding: spacing.xl,
    gap: spacing.lg,
  },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.xs, paddingTop: spacing.lg },
  reference: {
    fontSize: fontSizes.footnote,
    color: colors.inkMuted,
    fontVariant: ['tabular-nums'],
  },
  title: {
    fontSize: fontSizes.title2,
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
    gap: spacing.sm,
  },
  cardGood: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  detailValue: {
    fontSize: fontSizes.footnote,
    color: colors.ink,
    fontWeight: fontWeights.medium,
    flexShrink: 1,
    textAlign: 'right',
  },
});
