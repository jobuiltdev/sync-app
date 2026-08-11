import { useQuery } from '@tanstack/react-query';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fetchHealth, healthKeys } from '@/api/endpoints/health';
import { ApiError } from '@/api/errors';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Foundation screen.
 *
 * It exists to prove the whole path end to end: the device resolves the API URL,
 * reaches Django over the LAN, and renders a normalised response or a normalised
 * error. The real customer home screen replaces this in M2.
 */
export default function ConnectionScreen() {
  const { data, error, isPending, isFetching } = useQuery({
    queryKey: healthKeys.root,
    queryFn: ({ signal }) => fetchHealth(signal),
  });

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>Sync</Text>
        <Text style={styles.title}>API connection</Text>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
            <Text style={styles.body}>Contacting the backend</Text>
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not reach the API</Text>
            <Text style={styles.body}>{error.message}</Text>
            {error instanceof ApiError ? <Text style={styles.code}>{error.code}</Text> : null}
          </View>
        ) : (
          <View style={styles.card}>
            <Text style={styles.cardTitle}>Connected</Text>
            <Row label="Service" value={data.status} />
            <Row label="Database" value={data.checks.database} />
            <Row label="Cache" value={data.checks.cache} />
            {isFetching ? <Text style={styles.code}>refreshing</Text> : null}
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.ground,
  },
  content: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xxxl,
    gap: spacing.lg,
  },
  eyebrow: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.accent,
  },
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
  cardError: {
    borderColor: colors.danger,
    backgroundColor: colors.dangerSoft,
  },
  cardTitle: {
    fontSize: fontSizes.callout,
    fontWeight: fontWeights.semibold,
    color: colors.ink,
  },
  body: {
    fontSize: fontSizes.body,
    color: colors.inkSoft,
  },
  code: {
    fontSize: fontSizes.caption,
    color: colors.inkMuted,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  rowLabel: {
    fontSize: fontSizes.footnote,
    color: colors.inkMuted,
  },
  rowValue: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.ink,
  },
});
