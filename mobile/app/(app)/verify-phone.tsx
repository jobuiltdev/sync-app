import { useRouter } from 'expo-router';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { useCurrentUser } from '@/features/auth/hooks';
import { colors, fontSizes, fontWeights, radii, spacing } from '@/theme/tokens';

/**
 * Where a customer lands when booking asks for a verified phone.
 *
 * The SMS provider is not built yet, so this cannot complete the verification. It
 * exists so the refusal leads somewhere that explains itself rather than to a
 * dead end, and it is replaced by the real flow when the verification milestone
 * lands. Nothing here can set the verified state: that happens server-side only.
 */
export default function VerifyPhoneScreen() {
  const router = useRouter();
  const { data: user } = useCurrentUser();

  const verified = user?.is_phone_verified ?? false;

  return (
    <SafeAreaView style={styles.screen}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.title}>Verify your phone</Text>
          <Text style={styles.body}>
            A provider on their way to you needs a number that reaches you. We ask for this
            once, before your first booking.
          </Text>
        </View>

        <View style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.muted}>Number on file</Text>
            <Text style={styles.value}>{user?.phone ?? 'None yet'}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.muted}>Status</Text>
            <Text style={styles.value}>{verified ? 'Verified' : 'Not verified'}</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Not available yet</Text>
          <Text style={styles.body}>
            Sending verification codes is still being set up. Until it is switched on, ask
            support to verify your number.
          </Text>
        </View>

        <Button label="Back" variant="secondary" onPress={() => router.back()} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { padding: spacing.xl, gap: spacing.lg },
  header: { gap: spacing.sm, paddingTop: spacing.lg },
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
  cardTitle: { fontSize: fontSizes.callout, fontWeight: fontWeights.semibold, color: colors.ink },
  body: { fontSize: fontSizes.body, color: colors.inkSoft, lineHeight: 24 },
  muted: { fontSize: fontSizes.footnote, color: colors.inkMuted },
  value: { fontSize: fontSizes.footnote, fontWeight: fontWeights.medium, color: colors.ink },
  row: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.md },
});
