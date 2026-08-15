import { useRouter } from 'expo-router';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { BookingSummary } from '@/api/endpoints/bookings';
import { statusLabel } from '@/api/endpoints/bookings';
import { Button } from '@/components/ui/Button';
import { StatusPill } from '@/components/ui/StatusPill';
import { useJobs } from '@/features/bookings/hooks';
import { formatNaira } from '@/lib/money';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/** Work this provider has taken. The customer's own list is `bookings`; this is
 *  the same domain object seen from the other end. */
export default function JobsScreen() {
  const router = useRouter();
  const { data, isPending, error, refetch } = useJobs();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Your jobs</Text>
        </View>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your jobs</Text>
            <Text style={styles.body}>{error.message}</Text>
            <Button label="Try again" variant="secondary" onPress={() => refetch()} />
          </View>
        ) : data.results.length === 0 ? (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Nothing yet</Text>
            <Text style={styles.body}>Jobs you accept will appear here.</Text>
            <Button label="See offers" variant="secondary" onPress={() => router.push('/offers')} />
          </View>
        ) : (
          data.results.map((job) => (
            <JobRow key={job.id} job={job} onPress={() => router.push(`/job/${job.id}`)} />
          ))
        )}

        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

function JobRow({ job, onPress }: { job: BookingSummary; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${job.service_name}, ${statusLabel(job.status)}`}
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
    >
      <View style={styles.rowTop}>
        <Text style={styles.cardTitle}>{job.service_name}</Text>
        <Text style={styles.price}>{formatNaira(job.total_kobo)}</Text>
      </View>
      <Text style={styles.muted}>{job.address_summary}</Text>
      <StatusPill status={job.status} />
      <Text style={styles.reference}>{job.reference}</Text>
    </Pressable>
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
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.hairline,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardPressed: { backgroundColor: colors.surfaceSunk },
  cardError: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  rowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  price: {
    fontSize: fontSizes.body,
    fontWeight: fontWeights.semibold,
    color: colors.accent,
    fontVariant: ['tabular-nums'],
  },
  reference: {
    fontSize: fontSizes.caption,
    color: colors.inkMuted,
    fontVariant: ['tabular-nums'],
  },
});
