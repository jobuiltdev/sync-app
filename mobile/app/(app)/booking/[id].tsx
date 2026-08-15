import { useLocalSearchParams, useRouter } from 'expo-router';
import { StyleSheet, View } from 'react-native';

import { statusLabel } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { DetailList, DetailRow, humaniseKey, humaniseValue } from '@/components/ui/DetailList';
import { Header } from '@/components/ui/Header';
import { IconPlate } from '@/components/ui/Pill';
import { Screen } from '@/components/ui/Screen';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusPill } from '@/components/ui/StatusPill';
import { Card, SectionHeader } from '@/components/ui/Surface';
import { ErrorState, InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useBooking, useCancelBooking, useConfirmBooking } from '@/features/bookings/hooks';
import { bookingStatusView } from '@/features/status/presentation';
import { formatNaira } from '@/lib/money';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

/**
 * One booking, from the customer's side.
 *
 * **Actions come from `allowed_transitions` and nowhere else.** The server
 * decides what a booking can become, and the app renders buttons for exactly
 * what it was told. Deriving them from the status locally would mean two
 * lifecycles, and the one on the phone would be the stale one.
 */
export default function BookingDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const palette = usePalette();
  const { data: booking, isPending, error, refetch, isRefetching } = useBooking(id);
  const cancel = useCancelBooking();
  const confirm = useConfirmBooking();

  if (isPending) {
    return (
      <Screen>
        <Header onBack={() => router.back()} />
        <View style={styles.loading}>
          <Skeleton width="55%" height={30} />
          <Skeleton width="35%" height={20} />
          <Skeleton width="100%" height={120} radius={18} />
          <Skeleton width="100%" height={160} radius={18} />
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

  const view = bookingStatusView(booking.status);
  const canCancel = booking.allowed_transitions.includes('CANCELLED');
  const canConfirm = booking.allowed_transitions.includes('COMPLETED');
  // Offered while there is still a job to pay for. Whether it is accepted is
  // the server's decision: it refuses a cancelled, expired or already-paid one.
  const isPayable = booking.total_kobo > 0 && !['CANCELLED', 'EXPIRED'].includes(booking.status);

  return (
    <Screen refreshing={isRefetching} onRefresh={() => void refetch()}>
      <Header onBack={() => router.back()} />

      <View style={styles.hero}>
        <Text variant="caption" tone="muted" style={styles.reference}>
          {booking.reference}
        </Text>
        <Text variant="title1" accessibilityRole="header">
          {booking.service_name}
        </Text>
        <StatusPill view={view} />
        {view.detail ? (
          <Text variant="footnote" tone="soft">
            {view.detail}
          </Text>
        ) : null}
      </View>

      {booking.provider_name ? (
        <Card>
          <View style={styles.provider}>
            <IconPlate icon="profile" tone="primary" size={44} />
            <View style={styles.providerText}>
              <Text variant="caption" tone="muted">
                Your provider
              </Text>
              <Text variant="body" weight="semibold">
                {booking.provider_name}
              </Text>
            </View>
          </View>
        </Card>
      ) : null}

      <Card>
        <DetailList>
          <DetailRow label="Price" value={formatNaira(booking.total_kobo)} emphasis />
          <Text variant="caption" tone="muted">
            Agreed when you made this booking, and unchanged since.
          </Text>
        </DetailList>
      </Card>

      <View style={styles.section}>
        <SectionHeader title="Where" />
        <Card>
          <View style={styles.address}>
            <Text variant="body" weight="medium">
              {booking.address.street_address}
            </Text>
            {/* The landmark is second but visually equal: in Nigeria it is what
                a provider actually navigates by. */}
            {booking.address.landmark ? (
              <Text variant="footnote" tone="soft">
                {booking.address.landmark}
              </Text>
            ) : null}
            <Text variant="caption" tone="muted">
              {[booking.address.area, booking.address.lga, booking.address.state]
                .filter(Boolean)
                .join(', ')}
            </Text>
            {booking.address.directions_note ? (
              <Text variant="caption" tone="muted">
                {booking.address.directions_note}
              </Text>
            ) : null}
          </View>
        </Card>
      </View>

      {Object.keys(booking.details).length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="What you asked for" />
          <Card>
            <DetailList>
              {Object.entries(booking.details).map(([key, value]) => (
                <DetailRow key={key} label={humaniseKey(key)} value={humaniseValue(value)} />
              ))}
            </DetailList>
          </Card>
        </View>
      ) : null}

      {booking.events.length > 0 ? (
        <View style={styles.section}>
          <SectionHeader title="Progress" />
          <Card>
            <View style={styles.timeline}>
              {booking.events.map((event, index) => (
                <View key={event.id} style={styles.event}>
                  <View style={styles.rail}>
                    <View
                      style={[
                        styles.node,
                        {
                          backgroundColor:
                            index === booking.events.length - 1
                              ? palette.primary
                              : palette.hairline,
                        },
                      ]}
                    />
                    {index < booking.events.length - 1 ? (
                      <View style={[styles.line, { backgroundColor: palette.hairline }]} />
                    ) : null}
                  </View>
                  <View style={styles.eventText}>
                    <Text variant="footnote" weight="medium">
                      {statusLabel(event.to_status)}
                    </Text>
                    <Text variant="caption" tone="muted">
                      {formatWhen(event.created_at)}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          </Card>
        </View>
      ) : null}

      <InlineError error={cancel.error ?? confirm.error} />

      <View style={styles.actions}>
        {isPayable ? (
          <Button label="Pay for this booking" icon="card" onPress={() => router.push(`/pay/${id}`)} />
        ) : null}

        {canConfirm ? (
          <Button
            label="Confirm the work is done"
            icon="check"
            loading={confirm.isPending}
            onPress={() => confirm.mutate({ id })}
          />
        ) : null}

        {canCancel ? (
          <Button
            label="Cancel booking"
            variant={isPayable || canConfirm ? 'ghost' : 'secondary'}
            loading={cancel.isPending}
            onPress={() => cancel.mutate({ id })}
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
  provider: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  providerText: { flex: 1, gap: spacing.xxs },
  address: { gap: spacing.xs },
  timeline: { gap: 0 },
  event: { flexDirection: 'row', gap: spacing.md },
  rail: { alignItems: 'center', width: 10 },
  node: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  line: { width: 2, flex: 1, minHeight: 22 },
  eventText: { flex: 1, gap: 1, paddingBottom: spacing.md },
  actions: { gap: spacing.sm },
});
