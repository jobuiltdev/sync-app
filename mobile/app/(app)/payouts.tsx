import { useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { Header } from '@/components/ui/Header';
import { ListRow, RowGroup } from '@/components/ui/ListRow';
import { Screen } from '@/components/ui/Screen';
import { SkeletonList } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card } from '@/components/ui/Surface';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { usePayouts } from '@/features/payments/hooks';
import { payoutStatusView } from '@/features/status/presentation';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/** Money on its way to a bank account, and money that got there. */
export default function PayoutsScreen() {
  const router = useRouter();
  const payouts = usePayouts();

  const rows = payouts.data?.results ?? [];

  return (
    <Screen refreshing={payouts.isRefetching} onRefresh={() => void payouts.refetch()}>
      <Header
        onBack={() => router.back()}
        title="Payouts"
        action={
          <Button
            label="Request"
            icon="plus"
            variant="secondary"
            size="compact"
            fullWidth={false}
            onPress={() => router.push('/payout-request')}
          />
        }
      />

      {payouts.isPending ? (
        <SkeletonList rows={3} showPlate={false} />
      ) : payouts.error ? (
        <ErrorState error={payouts.error} onRetry={() => void payouts.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon="bank"
          title="No payouts yet"
          body="When you withdraw your earnings, each transfer appears here with its progress."
          action={
            <Button
              label="Request a payout"
              fullWidth={false}
              onPress={() => router.push('/payout-request')}
            />
          }
        />
      ) : (
        <Card padding="none">
          <RowGroup>
            {rows.map((payout) => {
              const view = payoutStatusView(payout);

              return (
                <ListRow
                  key={payout.id}
                  title={formatNaira(payout.amount_kobo)}
                  subtitle={formatWhen(payout.requested_at)}
                  icon="bank"
                  iconTone={view.tone === 'live' ? 'primary' : view.tone}
                  chevron
                  accessibilityLabel={`${formatNaira(payout.amount_kobo)}, ${view.label}`}
                  trailing={<StatusPill view={view} />}
                  onPress={() => router.push(`/payout/${payout.id}`)}
                />
              );
            })}
          </RowGroup>
        </Card>
      )}

      <View style={styles.footnote}>
        <Text variant="caption" tone="muted">
          Sync never pays out automatically. Every transfer here was one you asked for.
        </Text>
      </View>
    </Screen>
  );
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('en-NG', { day: 'numeric', month: 'short', year: 'numeric' });
}

const styles = StyleSheet.create({
  footnote: { paddingHorizontal: spacing.xs },
});
