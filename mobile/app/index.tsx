import { Redirect } from 'expo-router';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useOnboarding } from '@/features/onboarding/hooks';
import { useSessionStore } from '@/state/session';
import { usePalette } from '@/theme/theme';

/**
 * Entry point. Holds the first paint until the keychain has been read, so a
 * returning user is never shown the welcome screen for a frame before being
 * bounced home.
 *
 * Three destinations, in priority order: somebody signed in goes home,
 * somebody who has never seen the introduction gets it, and everybody else
 * lands on the welcome screen. The introduction is never shown to a signed-in
 * user, who has self-evidently already been through it.
 */
export default function Index() {
  const status = useSessionStore((state) => state.status);
  const onboarding = useOnboarding();
  const palette = usePalette();

  if (status === 'loading' || onboarding.state === 'loading') {
    return (
      <View style={[styles.splash, { backgroundColor: palette.ground }]}>
        <ActivityIndicator color={palette.primary} />
      </View>
    );
  }

  if (status === 'authenticated') return <Redirect href="/home" />;

  return <Redirect href={onboarding.state === 'needed' ? '/onboarding' : '/welcome'} />;
}

const styles = StyleSheet.create({
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
