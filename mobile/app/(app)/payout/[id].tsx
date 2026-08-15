import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { Button } from '@/components/ui/Button';
import { DetailList, DetailRow } from '@/components/ui/DetailList';
import { Header } from '@/components/ui/Header';
import { IconPlate } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useCancelPayout, usePayout } from '@/features/payments/hooks';
import { payoutStatusView } from '@/features/status/presentation';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * One payout.
 *
 * Whether cancelling is offered comes from the server's `is_cancellable`. The
 * app does not work it out from the status, because a payout that has been
 * submitted must never be cancellable and that rule belongs in one place.
 *
 * The five stages are visually distinct and honestly named. `PROCESSING` in
 * particular means two different things depending on whether a transfer
 * reference exists, and the distinction matters: one of them means the money
 * may already have left.
 */
export default function PayoutScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { data: payout, isPending, error, refetch, isFetching } = usePayout(id);
  const cancel = useCancelPayout();

  if (isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="50%" height={36} />
          <Skeleton width="100%" height={150} radius={18} />
        </View>
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Screen>
    );
  }

  const view = payoutStatusView(payout);

  return (
    <Screen refreshing={isFetching} onRefresh={() => void refetch()}>
      <Header onBack={() => router.back()} />

      <Card tone={view.tone === 'success' ? 'success' : view.tone === 'danger' ? 'danger' : 'default'}>
        <View style={styles.hero}>
          <IconPlate
            icon={
              payout.status === 'PAID'
                ? 'check'
                : payout.status === 'FAILED'
                  ? 'alert'
                  : payout.status === 'CANCELLED'
                    ? 'close'
                    : 'clock'
            }
            tone={view.tone === 'live' ? 'primary' : view.tone}
            size={48}
          />
          <Text
            variant="display"
            accessibilityLabel={`${formatNaira(payout.amount_kobo)}, ${view.label}`}
          >
            {formatNaira(payout.amount_kobo)}
          </Text>
          <StatusPill view={view} />
          {view.detail ? (
            <Text variant="footnote" tone="soft">
              {view.detail}
            </Text>
          ) : null}
        </View>
      </Card>

      <View style={styles.section}>
        <SectionHeader title="Details" />
        <Card>
          <DetailList>
            <DetailRow label="Requested" value={formatWhen(payout.requested_at)} />
            {payout.submitted_at ? (
              <DetailRow label="Sent to bank" value={formatWhen(payout.submitted_at)} />
            ) : null}
            {payout.processed_at ? (
              <DetailRow label="Resolved" value={formatWhen(payout.processed_at)} />
            ) : null}
            {payout.transfer_reference ? (
              // Worth showing: it is the reference support would ask for, and
              // the one the bank can be asked about.
              <DetailRow label="Reference" value={payout.transfer_reference} />
            ) : null}
          </DetailList>
        </Card>
      </View>

      <InlineError error={cancel.error} />

      {payout.is_cancellable ? (
        <Button
          label="Cancel this payout"
          variant="secondary"
          loading={cancel.isPending}
          onPress={() => cancel.mutate(payout.id)}
        />
      ) : null}

      {payout.status === 'PROCESSING' && payout.transfer_reference ? (
        <Text variant="caption" tone="muted">
          This cannot be cancelled. It has been sent to your bank and Sync never sends the
          same transfer twice.
        </Text>
      ) : null}
    </Screen>
  );
}

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('en-NG', {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  });
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg },
  hero: { alignItems: 'flex-start', gap: spacing.sm },
  section: { gap: spacing.md },
});
