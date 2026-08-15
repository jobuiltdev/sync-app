import { Redirect } from 'expo-router';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useSessionStore } from '@/state/session';
import { usePalette } from '@/theme/theme';

/**
 * Entry point. Holds the first paint until the keychain has been read, so a
 * returning user is never shown the welcome screen for a frame before being
 * bounced home.
 */
export default function Index() {
  const status = useSessionStore((state) => state.status);
  const palette = usePalette();

  if (status === 'loading') {
    return (
      <View style={[styles.splash, { backgroundColor: palette.ground }]}>
        <ActivityIndicator color={palette.primary} />
      </View>
    );
  }

  return <Redirect href={status === 'authenticated' ? '/home' : '/welcome'} />;
}

const styles = StyleSheet.create({
  splash: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
