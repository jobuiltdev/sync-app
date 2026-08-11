import { useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Button } from '@/components/ui/Button';
import { colors, fontSizes, fontWeights, spacing } from '@/theme/tokens';

export default function WelcomeScreen() {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.content}>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>Sync</Text>
          <Text style={styles.title}>Everyday services, one app.</Text>
          <Text style={styles.body}>
            Dispatch, cleaning, errands, home services, beauty and laundry. Booked from one place,
            by people you can trust.
          </Text>
        </View>

        <View style={styles.actions}>
          <Button label="Create an account" onPress={() => router.push('/register')} />
          <Button label="I already have an account" variant="secondary" onPress={() => router.push('/login')} />
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.ground },
  content: { flex: 1, padding: spacing.xl, justifyContent: 'space-between' },
  hero: { paddingTop: spacing.xxxl, gap: spacing.md },
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
    lineHeight: 40,
  },
  body: { fontSize: fontSizes.body, color: colors.inkMuted, lineHeight: 24 },
  actions: { gap: spacing.md, paddingBottom: spacing.lg },
});
