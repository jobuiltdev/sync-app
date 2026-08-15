import { useLocalSearchParams, useRouter } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { statusLabel } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import {
  useFinishJob,
  useJob,
  useMarkEnRoute,
  useStartJob,
} from '@/features/bookings/hooks';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

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

  const { data: job, isPending, error, refetch } = useJob(id);
  const enRoute = useMarkEnRoute();
  const start = useStartJob();
  const finish = useFinishJob();

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

  const can = (target: string) => job.allowed_transitions.includes(target as never);
  const actionError = enRoute.error ?? start.error ?? finish.error;
  const busy = enRoute.isPending || start.isPending || finish.isPending;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.reference}>{job.reference}</Text>
          <Text style={styles.title}>{job.service_name}</Text>
          <StatusPill status={job.status} />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>You earn</Text>
          <Text style={styles.price}>{formatNaira(job.total_kobo)}</Text>
          <Text style={styles.muted}>
            Before Sync&apos;s commission. Your share appears in earnings once the
            customer confirms and has paid.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Where</Text>
          <Text style={styles.body}>{job.address.street_address}</Text>
          <Text style={styles.muted}>{job.address.landmark}</Text>
          {job.address.area ? <Text style={styles.muted}>{job.address.area}</Text> : null}
          {job.address.directions_note ? (
            <Text style={styles.muted}>{job.address.directions_note}</Text>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Customer</Text>
          <Text style={styles.body}>{job.customer_name}</Text>
          {job.scheduled_for ? (
            <Text style={styles.muted}>
              Scheduled for {new Date(job.scheduled_for).toLocaleString('en-NG')}
            </Text>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>What they asked for</Text>
          {Object.entries(job.details).map(([key, value]) => (
            <View key={key} style={styles.detailRow}>
              <Text style={styles.muted}>{humanise(key)}</Text>
              <Text style={styles.detailValue}>{renderValue(value)}</Text>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Progress</Text>
          {job.events.map((event) => (
            <View key={event.id} style={styles.detailRow}>
              <Text style={styles.muted}>{statusLabel(event.to_status)}</Text>
              <Text style={styles.detailValue}>
                {new Date(event.created_at).toLocaleString('en-NG')}
              </Text>
            </View>
          ))}
        </View>

        {actionError ? (
          <View accessibilityRole="alert" style={[styles.card, styles.cardError]}>
            <Text style={styles.body}>{actionError.message}</Text>
          </View>
        ) : null}

        {can('EN_ROUTE') ? (
          <Button
            label="I am on the way"
            loading={enRoute.isPending}
            disabled={busy}
            onPress={() => enRoute.mutate(id)}
          />
        ) : null}

        {can('IN_PROGRESS') ? (
          <Button
            label="Start the job"
            loading={start.isPending}
            disabled={busy}
            onPress={() => start.mutate(id)}
          />
        ) : null}

        {can('AWAITING_CONFIRMATION') ? (
          <Button
            label="Mark the work finished"
            loading={finish.isPending}
            disabled={busy}
            onPress={() => finish.mutate(id)}
          />
        ) : null}

        {job.status === 'AWAITING_CONFIRMATION' ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Waiting on the customer</Text>
            <Text style={styles.body}>
              They confirm the work is done. You cannot close a job yourself, which is
              what makes their confirmation worth something.
            </Text>
          </View>
        ) : null}

        {job.status === 'COMPLETED' ? (
          <Button label="See earnings" variant="secondary" onPress={() => router.push('/earnings')} />
        ) : null}

        <Button label="Back" variant="secondary" onPress={() => router.back()} />
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
    gap: spacing.md,
    padding: spacing.xl,
    backgroundColor: colors.ground,
  },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.sm, paddingTop: spacing.lg, alignItems: 'flex-start' },
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
    gap: spacing.xs,
  },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  price: {
    fontSize: fontSizes.title3,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
    fontVariant: ['tabular-nums'],
  },
  detailRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: 2,
  },
  detailValue: { fontSize: fontSizes.footnote, fontWeight: fontWeights.medium, color: colors.ink },
});
