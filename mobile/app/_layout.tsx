import { QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { setAccessTokenProvider, setTokenRefresher } from '@/api/client';
import { handoffTransition } from '@/features/startup/handoff';
import { useStartup } from '@/features/startup/hooks';
import { createQueryClient } from '@/lib/query-client';
import { getAccessToken, renewSession } from '@/state/session';
import { ThemeProvider, useTheme } from '@/theme/theme';

// Registered at module scope so the API layer is wired before any request can be
// made, including one fired by a screen that mounts on the very first frame.
setAccessTokenProvider(getAccessToken);
setTokenRefresher(renewSession);

/**
 * Hold the native splash.
 *
 * Without this the splash disappears the moment the JS bundle finishes loading,
 * which is before any stored state has been read. The app then paints a spinner
 * on a background whose colour it is still deciding. Holding the splash turns
 * that flicker into a single, deliberate handoff.
 *
 * The rejection is swallowed on purpose. This throws when the splash has already
 * gone, which is not a failure worth crashing a launch over.
 */
void SplashScreen.preventAutoHideAsync().catch(() => undefined);

export default function RootLayout() {
  // One client for the lifetime of the app. A lazy initialiser rather than module
  // scope keeps each test file isolated from the last, and builds it only once.
  const [queryClient] = useState(createQueryClient);

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
 * provider. It owns three things: the status bar, the navigator, and the moment
 * the native splash goes away.
 *
 * ### When the splash is hidden
 *
 * Once every local read the first frame depends on has finished, and then on the
 * next layout pass. Both halves matter. Hiding on readiness alone can reveal a
 * frame React has decided on but not yet drawn; waiting for `onLayout` means the
 * view underneath is genuinely on screen, so the two images swap rather than
 * flashing through anything in between.
 *
 * **Only local reads are waited on.** Three keychain values: the session tokens,
 * the onboarding flag and the theme preference. No request is made and nothing
 * here depends on the network, so a launch on a dead connection is exactly as
 * fast as one on Wi-Fi.
 */
function ThemedNavigator() {
  const { palette, scheme } = useTheme();
  const { isReady, motion } = useStartup();

  // How the launch surface gives way to whichever group it routes into. Read
  // here rather than in `LaunchScreen` because it is a property of the incoming
  // screen, and the navigator is the only thing that knows about both.
  //
  // It never gates navigation. An unresolved preference simply means no
  // transition, exactly as it means no animation on the launch surface itself.
  const handoff = handoffTransition(motion);

  const [hasLaidOut, setHasLaidOut] = useState(false);
  // Hiding twice is harmless but pointless, and the second call rejects.
  const hidden = useRef(false);

  const onLayout = useCallback(() => setHasLaidOut(true), []);

  useEffect(() => {
    // Both conditions, watched rather than handled inside `onLayout`. Layout
    // fires once and readiness usually lands after it, so hiding from the
    // callback alone would leave the splash up for ever on most launches. That
    // is the failure mode worth guarding hardest against: a person staring at a
    // static image with no way forward.
    if (!isReady || !hasLaidOut || hidden.current) return;

    hidden.current = true;
    // Never awaited and never allowed to throw.
    void SplashScreen.hideAsync().catch(() => undefined);
  }, [isReady, hasLaidOut]);

  return (
    <View style={{ flex: 1, backgroundColor: palette.ground }} onLayout={onLayout}>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          // Every screen, including both groups, paints the same ground. During
          // the handoff the outgoing launch surface and the incoming destination
          // are therefore the same colour, so the crossfade cannot flash a
          // contrasting frame between them.
          contentStyle: { backgroundColor: palette.ground },
          // Screens are written with their own header, so the platform default
          // slide is all that is wanted here.
          animation: 'slide_from_right',
        }}
      >
        {/* The launch surface. It is never navigated *to*, only away from. */}
        <Stack.Screen name="index" />
        {/* Both groups are entered by `router.replace` from the launch screen,
            so both carry the handoff. What happens once inside them is the
            business of their own layouts, which still slide as they always did. */}
        <Stack.Screen name="(auth)" options={handoff} />
        <Stack.Screen name="(app)" options={handoff} />
      </Stack>
    </View>
  );
}
