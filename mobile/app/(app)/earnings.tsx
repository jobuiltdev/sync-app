import { useRouter } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Settlement } from '@/api/endpoints/payments';
import { Button } from '@/components/ui/Button';
import { useEarnings, useSettlements } from '@/features/payments/hooks';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * What a provider has earned, and what of it they can take out.
 *
 * Every figure comes from the server, including the breakdown. The app does no
 * arithmetic on money at all: it has no way to know about a payout requested on
 * another device, so a locally computed balance would be confidently wrong.
 */
export default function EarningsScreen() {
  const router = useRouter();
  const earnings = useEarnings();
  const settlements = useSettlements();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Earnings</Text>
        </View>

        {earnings.isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : earnings.error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your earnings</Text>
            <Text style={styles.body}>{earnings.error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => earnings.refetch()} />
          </View>
        ) : (
          <>
            <View style={styles.balanceCard}>
              <Text style={styles.balanceLabel}>Available to withdraw</Text>
              <Text
                accessibilityLabel={`Available to withdraw, ${formatNaira(earnings.data.available_kobo)}`}
                style={styles.balance}
              >
                {formatNaira(earnings.data.available_kobo)}
              </Text>
              {earnings.data.reserved_kobo > 0 ? (
                <Text style={styles.balanceNote}>
                  {formatNaira(earnings.data.reserved_kobo)} is in a payout already under way.
                </Text>
              ) : null}
            </View>

            <View style={styles.card}>
              <Text style={styles.cardTitle}>Where it comes from</Text>
              <Row label="Completed jobs" value={String(earnings.data.settlement_count)} />
              <Row label="Customers paid" value={formatNaira(earnings.data.gross_earned_kobo)} />
              <Row label="Sync commission" value={formatNaira(earnings.data.commission_kobo)} />
              <Row label="Your share" value={formatNaira(earnings.data.net_earned_kobo)} />
              <Row label="Already paid out" value={formatNaira(earnings.data.paid_out_kobo)} />
            </View>

            <Button
              label="Request a payout"
              disabled={earnings.data.available_kobo <= 0}
              onPress={() => router.push('/payout-request')}
            />
            <Button
              label="Payout history"
              variant="secondary"
              onPress={() => router.push('/payouts')}
            />
            <Button
              label="Where you are paid"
              variant="secondary"
              onPress={() => router.push('/payout-destination')}
            />
          </>
        )}

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Completed jobs</Text>
          {settlements.isPending ? (
            <View style={styles.card}>
              <ActivityIndicator color={colors.accent} />
            </View>
          ) : settlements.error ? (
            <View style={styles.card}>
              <Text style={styles.body}>{settlements.error.message}</Text>
            </View>
          ) : settlements.data.results.length === 0 ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Nothing yet</Text>
              <Text style={styles.body}>
                Finish a job and what it earned you appears here.
              </Text>
            </View>
          ) : (
            settlements.data.results.map((settlement) => (
              <SettlementRow key={settlement.id} settlement={settlement} />
            ))
          )}
        </View>
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

function SettlementRow({ settlement }: { settlement: Settlement }) {
  return (
    <View style={styles.card}>
      <View style={styles.rowTop}>
        <Text style={styles.cardTitle}>{settlement.service_name}</Text>
        <Text style={styles.amount}>{formatNaira(settlement.provider_amount_kobo)}</Text>
      </View>
      <Text style={styles.muted}>{settlement.booking_reference}</Text>
      <Text style={styles.muted}>
        {formatNaira(settlement.gross_amount_kobo)} paid, less{' '}
        {formatNaira(settlement.commission_amount_kobo)} commission
      </Text>
    </View>
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
  balanceCard: {
    backgroundColor: colors.accentSoft,
    borderRadius: radii.card,
    padding: spacing.xl,
    gap: spacing.xs,
  },
  balanceLabel: { fontSize: fontSizes.footnote, color: colors.inkSoft },
  balance: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.accent,
    // Money lines up in a column, so tabular figures stop it shifting width.
    fontVariant: ['tabular-nums'],
  },
  balanceNote: { fontSize: fontSizes.footnote, color: colors.inkSoft },
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
  section: { gap: spacing.sm, paddingTop: spacing.lg },
  sectionTitle: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: 2,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  rowValue: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.ink,
    fontVariant: ['tabular-nums'],
  },
  amount: {
    fontSize: fontSizes.body,
    fontWeight: fontWeights.semibold,
    color: colors.accent,
    fontVariant: ['tabular-nums'],
  },
});
