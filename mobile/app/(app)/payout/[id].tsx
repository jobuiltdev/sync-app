import { useLocalSearchParams, useRouter } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { payoutStageMessage, payoutStatusLabel } from '@/api/endpoints/payments';
import { Button } from '@/components/ui/Button';
import { useCancelPayout, usePayout } from '@/features/payments/hooks';
import { toPayoutOutcome } from '@/features/payments/outcomes';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * One payout, and the only thing its owner may do to it.
 *
 * Whether cancelling is offered comes from the server's `is_cancellable`. The
 * app does not work it out from the status, because the rule about which states
 * a provider may leave lives in the payout lifecycle and a second copy of it
 * here would eventually disagree.
 */
export default function PayoutDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { data: payout, isPending, error, refetch, isFetching } = usePayout(id);
  const cancel = useCancelPayout();

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
        <Button label="Try again" variant="secondary" onPress={() => refetch()} />
      </SafeAreaView>
    );
  }

  const outcome = toPayoutOutcome(cancel.error);

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.amount}>{formatNaira(payout.amount_kobo)}</Text>
          <Text style={styles.status}>{payoutStatusLabel(payout.status)}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.body}>{payoutStageMessage(payout)}</Text>
          {payout.transfer_reference ? (
            <Text style={styles.muted}>Reference {payout.transfer_reference}</Text>
          ) : null}
        </View>

        <View style={styles.card}>
          <Row label="Requested" value={new Date(payout.requested_at).toLocaleString('en-NG')} />
          {payout.submitted_at ? (
            <Row label="Sent" value={new Date(payout.submitted_at).toLocaleString('en-NG')} />
          ) : null}
          {payout.processed_at ? (
            <Row label="Resolved" value={new Date(payout.processed_at).toLocaleString('en-NG')} />
          ) : null}
          <Row label="Currency" value={payout.currency} />
        </View>

        {payout.failure_reason ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Why it failed</Text>
            <Text style={styles.body}>{payout.failure_reason}</Text>
            <Text style={styles.muted}>
              The money is back in your available balance. You can ask again.
            </Text>
          </View>
        ) : null}

        {outcome ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not cancel</Text>
            <Text style={styles.body}>{outcome.message}</Text>
            <Button label="Refresh" variant="secondary" onPress={() => refetch()} />
          </View>
        ) : null}

        <Button
          label="Refresh"
          variant="secondary"
          loading={isFetching}
          onPress={() => refetch()}
        />

        {payout.is_cancellable ? (
          <Button
            label="Cancel this payout"
            variant="secondary"
            loading={cancel.isPending}
            onPress={() => cancel.mutate(payout.id)}
          />
        ) : null}

        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.muted}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  centred: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.ground,
  },
  content: { padding: spacing.xl, gap: spacing.md },
  header: { gap: spacing.xs, paddingTop: spacing.lg, paddingBottom: spacing.sm },
  amount: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
    fontVariant: ['tabular-nums'],
  },
  status: { fontSize: fontSizes.body, color: colors.inkSoft },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.xs,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft, gap: spacing.md },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: 2,
  },
  rowValue: { fontSize: fontSizes.footnote, fontWeight: fontWeights.medium, color: colors.ink },
});
