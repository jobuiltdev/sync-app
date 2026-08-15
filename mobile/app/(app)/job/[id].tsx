import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { statusLabel } from '@/api/endpoints/bookings';
import { Avatar } from '@/components/ui/Avatar';
import { Button } from '@/components/ui/Button';
import { DetailList, DetailRow, humaniseKey, humaniseValue } from '@/components/ui/DetailList';
import { Header } from '@/components/ui/Header';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useFinishJob, useJob, useMarkEnRoute, useStartJob } from '@/features/bookings/hooks';
import { jobStatusView } from '@/features/status/presentation';
import { formatNaira } from '@/lib/money';
import { spacing } from '@/theme/tokens';

/**
 * A job a provider has taken, and the work of doing it.
 *
 * Which actions appear comes from the server's `allowed_transitions`. The app
 * does not work them out from the status, because the lifecycle decides both the
 * edge and who may take it, and a second copy of those rules here would
 * eventually disagree about which button to show.
 *
 * A provider moves work forward. They never close a job: only the customer
 * confirms it was done, which is what makes the confirmation mean anything.
 */
export default function JobScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const { data: job, isPending, error, refetch, isRefetching } = useJob(id);
  const enRoute = useMarkEnRoute();
  const start = useStartJob();
  const finish = useFinishJob();

  if (isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="55%" height={30} />
          <Skeleton width="100%" height={120} radius={18} />
          <Skeleton width="100%" height={140} radius={18} />
        </View>
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <ErrorState error={error} onRetry={() => void refetch()} retrying={isRefetching} />
      </Screen>
    );
  }

  const can = (target: string) => job.allowed_transitions.includes(target as never);
  const busy = enRoute.isPending || start.isPending || finish.isPending;
  const view = jobStatusView(job.status);

  return (
    <Screen refreshing={isRefetching} onRefresh={() => void refetch()}>
      <Header onBack={() => router.back()} />

      <View style={styles.hero}>
        <Text variant="caption" tone="muted" style={styles.reference}>
          {job.reference}
        </Text>
        <Text variant="title1" accessibilityRole="header">
          {job.service_name}
        </Text>
        <StatusPill view={view} />
        {view.detail ? (
          <Text variant="footnote" tone="soft">
            {view.detail}
          </Text>
        ) : null}
      </View>

      <Card>
        <View style={styles.earn}>
          <Text variant="overline" tone="muted">
            Job value
          </Text>
          <Text variant="priceLarge">{formatNaira(job.total_kobo)}</Text>
          <Text variant="caption" tone="muted">
            Before Sync&apos;s commission. Your share appears in earnings once the customer
            confirms and has paid.
          </Text>
        </View>
      </Card>

      <View style={styles.section}>
        <SectionHeader title="Where" />
        <Card>
          <View style={styles.address}>
            <Text variant="body" weight="medium">
              {job.address.street_address}
            </Text>
            {job.address.landmark ? (
              <Text variant="footnote" tone="soft">
                {job.address.landmark}
              </Text>
            ) : null}
            <Text variant="caption" tone="muted">
              {[job.address.area, job.address.lga, job.address.state].filter(Boolean).join(', ')}
            </Text>
            {job.address.directions_note ? (
              <Text variant="caption" tone="muted">
                {job.address.directions_note}
              </Text>
            ) : null}
          </View>
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title="Customer" />
        <Card>
          <View style={styles.customer}>
            <Avatar name={job.customer_name} size={40} />
            <View style={styles.customerText}>
              <Text variant="body" weight="medium">
                {job.customer_name}
              </Text>
              {job.scheduled_for ? (
                <Text variant="caption" tone="muted">
                  Scheduled for {formatWhen(job.scheduled_for)}
                </Text>
              ) : null}
            </View>
          </View>
        </Card>
      </View>

      {Object.keys(job.details).length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="What they asked for" />
          <Card>
            <DetailList>
              {Object.entries(job.details).map(([key, value]) => (
                <DetailRow key={key} label={humaniseKey(key)} value={humaniseValue(value)} />
              ))}
            </DetailList>
          </Card>
        </View>
      ) : null}

      {job.events.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Progress" />
          <Card>
            <DetailList>
              {job.events.map((event) => (
                <DetailRow
                  key={event.id}
                  label={statusLabel(event.to_status)}
                  value={formatWhen(event.created_at)}
                />
              ))}
            </DetailList>
          </Card>
        </View>
      ) : null}

      <InlineError error={enRoute.error ?? start.error ?? finish.error} />

      <View style={styles.actions}>
        {can('EN_ROUTE') ? (
          <Button
            label="I am on my way"
            icon="pin"
            loading={enRoute.isPending}
            disabled={busy}
            onPress={() => enRoute.mutate(id)}
          />
        ) : null}

        {can('IN_PROGRESS') ? (
          <Button
            label="Start work"
            loading={start.isPending}
            disabled={busy}
            onPress={() => start.mutate(id)}
          />
        ) : null}

        {can('AWAITING_CONFIRMATION') ? (
          <Button
            label="Mark as finished"
            icon="check"
            loading={finish.isPending}
            disabled={busy}
            onPress={() => finish.mutate(id)}
          />
        ) : null}
      </View>
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
  hero: { gap: spacing.sm, alignItems: 'flex-start' },
  reference: { fontVariant: ['tabular-nums'] },
  section: { gap: spacing.md },
  earn: { gap: spacing.xs },
  address: { gap: spacing.xs },
  customer: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  customerText: { flex: 1, gap: spacing.xxs },
  actions: { gap: spacing.sm },
});
