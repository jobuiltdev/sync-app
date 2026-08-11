import { useQuery } from '@tanstack/react-query';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fetchHealth, healthKeys } from '@/api/endpoints/health';
import { Button } from '@/components/ui/Button';
import { useCurrentUser, useSignOut } from '@/features/auth/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Foundation screen for a signed-in user.
 *
 * It exists to prove the authentication path end to end: a stored session
 * authenticates a request, the server identifies the caller, and signing out
 * clears both sides. The real customer home replaces this in M2.
 */
export default function HomeScreen() {
  const { data: user, isPending, error } = useCurrentUser();
  const health = useQuery({ queryKey: healthKeys.root, queryFn: ({ signal }) => fetchHealth(signal) });
  const signOut = useSignOut();

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.eyebrow}>Signed in</Text>
          <Text style={styles.title}>{user?.full_name || user?.email || 'Your account'}</Text>
        </View>

        {isPending ? (
          <View style={styles.card}>
            <ActivityIndicator color={colors.accent} />
          </View>
        ) : error ? (
          <View style={[styles.card, styles.cardError]}>
            <Text style={styles.cardTitle}>Could not load your account</Text>
            <Text style={styles.body}>{error.message}</Text>
          </View>
        ) : (
          <View style={styles.card}>
            <Row label="Email" value={user.email} />
            <Row label="Phone" value={user.phone ?? 'Not added'} />
            <Row label="Email verified" value={user.is_email_verified ? 'Yes' : 'Not yet'} />
            <Row label="Phone verified" value={user.is_phone_verified ? 'Yes' : 'Not yet'} />
          </View>
        )}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>API</Text>
          <Row label="Service" value={health.data?.status ?? 'checking'} />
        </View>

        <Button
          label="Sign out"
          variant="secondary"
          loading={signOut.isPending}
          onPress={() => signOut.mutate()}
        />
      </ScrollView>
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
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.xs, paddingTop: spacing.lg },
  eyebrow: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
    color: colors.accent,
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
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
    gap: spacing.md,
  },
  rowLabel: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  rowValue: {
    fontSize: fontSizes.footnote,
    fontWeight: fontWeights.medium,
    color: colors.ink,
    flexShrink: 1,
    textAlign: 'right',
  },
});
