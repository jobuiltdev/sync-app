import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { type BookingSummary, statusLabel } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { useBookings } from '@/features/bookings/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

export default function BookingsScreen() {
  const router = useRouter();
  const { data, isPending, error, refetch } = useBookings();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title}>Your bookings</Text>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your bookings</Text>
            <Text style={styles.body}>{error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => refetch()} />
          </View>
        ) : data.results.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Nothing booked yet</Text>
            <Text style={styles.body}>When you book a service it will show up here.</Text>
            <Button label="Browse services" onPress={() => router.push('/home')} />
          </View>
        ) : (
          data.results.map((booking) => (
            <BookingRow
              key={booking.id}
              booking={booking}
              onPress={() => router.push(`/booking/${booking.id}`)}
            />
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function BookingRow({ booking, onPress }: { booking: BookingSummary; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${booking.service_name}, ${statusLabel(booking.status)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
    >
      <View style={styles.rowTop}>
        <Text style={styles.cardTitle}>{booking.service_name}</Text>
        <StatusPill status={booking.status} />
      </View>
      <Text style={styles.muted}>{booking.provider_name}</Text>
      <Text style={styles.muted}>{booking.address_summary}</Text>
      <Text style={styles.reference}>{booking.reference}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.md },
  title: {
    fontSize: fontSizes.title1,
    fontWeight: fontWeights.bold,
    color: colors.ink,
    letterSpacing: -0.5,
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
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
  reference: {
    fontSize: fontSizes.caption,
    color: colors.inkMuted,
    fontVariant: ['tabular-nums'],
    paddingTop: spacing.xs,
  },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
});
