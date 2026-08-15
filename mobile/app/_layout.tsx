import { QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { setAccessTokenProvider, setTokenRefresher } from '@/api/client';
import { createQueryClient } from '@/lib/query-client';
import { getAccessToken, renewSession, useSessionStore } from '@/state/session';
import { ThemeProvider, useTheme } from '@/theme/theme';

// Registered at module scope so the API layer is wired before any request can be
// made, including one fired by a screen that mounts on the very first frame.
setAccessTokenProvider(getAccessToken);
setTokenRefresher(renewSession);

export default function RootLayout() {
  // One client for the lifetime of the app. A lazy initialiser rather than module
  // scope keeps each test file isolated from the last, and builds it only once.
  const [queryClient] = useState(createQueryClient);
  const hydrate = useSessionStore((state) => state.hydrate);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          {/* Above the navigator, so every screen and every modal resolves the
              same palette and a theme change repaints all of them at once. */}
          <ThemeProvider>
            <ThemedNavigator />
          </ThemeProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

/**
 * Separated so it can call `useTheme`, which is only available below the
 * provider. It also owns the status bar: the bar's content colour has to invert
 * with the scheme or it disappears into the background in one of the two modes.
 */
function ThemedNavigator() {
  const { palette, scheme } = useTheme();

  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: palette.ground },
          // Screens are written with their own header, so the platform default
          // slide is all that is wanted here.
          animation: 'slide_from_right',
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(app)" />
      </Stack>
    </>
  );
}
