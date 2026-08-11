import { QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { setAccessTokenProvider, setTokenRefresher } from '@/api/client';
import { createQueryClient } from '@/lib/query-client';
import { getAccessToken, renewSession, useSessionStore } from '@/state/session';
import { colors } from '@/theme/tokens';

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
          <StatusBar style="dark" />
          <Stack
            screenOptions={{
              headerShadowVisible: false,
              headerStyle: { backgroundColor: colors.ground },
              headerTintColor: colors.ink,
              contentStyle: { backgroundColor: colors.ground },
            }}
          >
            <Stack.Screen name="index" options={{ headerShown: false }} />
            <Stack.Screen name="(auth)" options={{ headerShown: false }} />
            <Stack.Screen name="(app)" options={{ headerShown: false }} />
          </Stack>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
