import { useLocalSearchParams } from 'expo-router';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { statusLabel } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { useBooking, useCancelBooking, useConfirmBooking } from '@/features/bookings/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

export default function BookingDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { data: booking, isPending, error } = useBooking(id);
  const cancel = useCancelBooking();
  const confirm = useConfirmBooking();

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
      </SafeAreaView>
    );
  }

  // The server says what may happen next. The app renders actions from that
  // rather than deciding for itself, so a stale build cannot offer a move the
  // lifecycle would refuse.
  const canCancel = booking.allowed_transitions.includes('CANCELLED');
  const canConfirm = booking.allowed_transitions.includes('COMPLETED');
  const actionError = cancel.error ?? confirm.error;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.reference}>{booking.reference}</Text>
          <Text style={styles.title}>{booking.service_name}</Text>
          <StatusPill status={booking.status} />
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Where</Text>
          <Text style={styles.body}>{booking.address.street_address}</Text>
          <Text style={styles.muted}>{booking.address.landmark}</Text>
          {booking.address.directions_note ? (
            <Text style={styles.muted}>{booking.address.directions_note}</Text>
          ) : null}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>What you asked for</Text>
          {Object.entries(booking.details).map(([key, value]) => (
            <View key={key} style={styles.detailRow}>
              <Text style={styles.muted}>{humanise(key)}</Text>
              <Text style={styles.detailValue}>{renderValue(value)}</Text>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Progress</Text>
          {booking.events.map((event) => (
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

        {canConfirm ? (
          <Button
            label="Confirm the work is done"
            loading={confirm.isPending}
            onPress={() => confirm.mutate({ id })}
          />
        ) : null}

        {canCancel ? (
          <Button
            label="Cancel booking"
            variant="secondary"
            loading={cancel.isPending}
            onPress={() => cancel.mutate({ id })}
          />
        ) : null}
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
    gap: spacing.sm,
  },
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
