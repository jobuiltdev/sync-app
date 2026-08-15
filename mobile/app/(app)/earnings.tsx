import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { DetailList, DetailRow } from '@/components/ui/DetailList';
import { Header } from '@/components/ui/Header';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { Skeleton, SkeletonList } from '@/components/ui/Skeleton';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useEarnings, useSettlements } from '@/features/payments/hooks';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * What a provider has made.
 *
 * **Every figure here is the server's.** The balance is derived there from
 * immutable settlements and payouts on each request, and this screen renders
 * exactly what it was given. It does not add anything up: two devices that each
 * did their own arithmetic would eventually disagree about what can be
 * withdrawn, and one of them would be wrong at the moment somebody tapped
 * withdraw.
 */
export default function EarningsScreen() {
  const router = useRouter();
  const earnings = useEarnings();
  const settlements = useSettlements();

  const rows = settlements.data?.results ?? [];

  return (
    <Screen
      refreshing={earnings.isRefetching}
      onRefresh={() => {
        void earnings.refetch();
        void settlements.refetch();
      }}
    >
      <Header onBack={() => router.back()} title="Earnings" />

      {earnings.isPending ? (
        <Skeleton width="100%" height={180} radius={18} />
      ) : earnings.error ? (
        <ErrorState error={earnings.error} onRetry={() => void earnings.refetch()} />
      ) : (
        <>
          <Card>
            <View style={styles.balance}>
              <Text variant="overline" tone="muted">
                Available to withdraw
              </Text>
              <Text
                variant="display"
                accessibilityLabel={`Available to withdraw, ${formatNaira(earnings.data.available_kobo)}`}
              >
                {formatNaira(earnings.data.available_kobo)}
              </Text>
              {earnings.data.reserved_kobo > 0 ? (
                <Text variant="caption" tone="muted">
                  {formatNaira(earnings.data.reserved_kobo)} is reserved by a payout you have
                  already requested.
                </Text>
              ) : null}
            </View>

            <View style={styles.action}>
              <Button
                label="Request a payout"
                icon="bank"
                disabled={earnings.data.available_kobo <= 0}
                onPress={() => router.push('/payout-request')}
              />
              {earnings.data.available_kobo <= 0 ? (
                <Text variant="caption" tone="muted" center>
                  Nothing available yet. Money becomes available when a customer confirms a
                  job they have paid for.
                </Text>
              ) : null}
            </View>
          </Card>

          <View style={styles.section}>
            <SectionHeader title="All time" />
            <Card>
              <DetailList>
                <DetailRow
                  label="Earned before commission"
                  value={formatNaira(earnings.data.gross_earned_kobo)}
                />
                <DetailRow
                  label="Sync commission"
                  value={`- ${formatNaira(earnings.data.commission_kobo)}`}
                />
                <DetailRow
                  label="Your earnings"
                  value={formatNaira(earnings.data.net_earned_kobo)}
                  emphasis
                />
                <DetailRow label="Paid out" value={formatNaira(earnings.data.paid_out_kobo)} />
                <DetailRow
                  label="Completed jobs"
                  value={String(earnings.data.settlement_count)}
                />
              </DetailList>
            </Card>
          </View>
        </>
      )}

      <View style={styles.section}>
        <SectionHeader
          title="Job by job"
          action={
            <Button
              label="Payouts"
              variant="ghost"
              size="compact"
              fullWidth={false}
              onPress={() => router.push('/payouts')}
            />
          }
        />

        {settlements.isPending ? (
          <SkeletonList rows={3} showPlate={false} />
        ) : settlements.error ? (
          <ErrorState error={settlements.error} onRetry={() => void settlements.refetch()} />
        ) : rows.length === 0 ? (
          <EmptyState
            icon="wallet"
            title="No earnings yet"
            body="A job earns once the customer confirms it and their payment has landed."
          />
        ) : (
          <Card padding="none">
            <RowGroup>
              {rows.map((settlement) => (
                <ListRow
                  key={settlement.id}
                  title={settlement.service_name}
                  subtitle={settlement.booking_reference}
                  meta={`${formatNaira(settlement.gross_amount_kobo)} less ${formatNaira(settlement.commission_amount_kobo)} commission`}
                  accessibilityLabel={`${settlement.service_name}, you earned ${formatNaira(settlement.provider_amount_kobo)}`}
                  trailing={
                    <Text variant="price" tone="success">
                      {formatNaira(settlement.provider_amount_kobo)}
                    </Text>
                  }
                />
              ))}
            </RowGroup>
          </Card>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  balance: { gap: spacing.xs },
  action: { marginTop: spacing.lg, gap: spacing.sm },
  section: { gap: spacing.md },
});
