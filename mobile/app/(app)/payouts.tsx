import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Payout } from '@/api/endpoints/payments';
import { payoutStatusLabel } from '@/api/endpoints/payments';
import { Button } from '@/components/ui/Button';
import { usePayouts } from '@/features/payments/hooks';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

export default function PayoutsScreen() {
  const router = useRouter();
  const { data, isPending, error, refetch } = usePayouts();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Payouts</Text>
        </View>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your payouts</Text>
            <Text style={styles.body}>{error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => refetch()} />
          </View>
        ) : data.results.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Nothing yet</Text>
            <Text style={styles.body}>Payouts you ask for will be listed here.</Text>
          </View>
        ) : (
          data.results.map((payout) => (
            <PayoutRow
              key={payout.id}
              payout={payout}
              onPress={() => router.push(`/payout/${payout.id}`)}
            />
          ))
        )}

        <Button label="Back to earnings" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function PayoutRow({ payout, onPress }: { payout: Payout; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${formatNaira(payout.amount_kobo)}, ${payoutStatusLabel(payout.status)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
    >
      <View style={styles.rowTop}>
        <Text style={styles.amount}>{formatNaira(payout.amount_kobo)}</Text>
        <Text style={styles.status}>{payoutStatusLabel(payout.status)}</Text>
      </View>
      <Text style={styles.muted}>{new Date(payout.requested_at).toLocaleString('en-NG')}</Text>
      {payout.failure_reason ? (
        <Text style={styles.failure}>{payout.failure_reason}</Text>
      ) : null}
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
  failure: { fontSize: fontSizes.footnote, color: colors.danger },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  amount: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
    fontVariant: ['tabular-nums'],
  },
  // Status is spelled out rather than shown as a colour, so it survives a colour
  // vision deficiency and reads the same in bright sun.
  status: { fontSize: fontSizes.footnote, fontWeight: fontWeights.medium, color: colors.inkSoft },
});
