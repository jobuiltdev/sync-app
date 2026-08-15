import { Redirect, Stack } from 'expo-router';

import { useSessionStore } from '@/state/session';
import { usePalette } from '@/theme/theme';

/**
 * The signed-in stack.
 *
 * `(tabs)` is one screen in it. Everything else is pushed *over* the tab bar
 * rather than inside it, which is the arrangement that keeps the bar to three
 * destinations: a booking, an offer, a payout and the provider profile are all
 * places you go and come back from, not places you switch between.
 */
export default function AppLayout() {
  const status = useSessionStore((state) => state.status);
  const palette = usePalette();

  // The client-side guard is for the experience only. Every endpoint behind it is
  // enforced server-side, so reaching this screen without a session shows nothing.
  if (status === 'anonymous') return <Redirect href="/welcome" />;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: palette.ground },
        animation: 'slide_from_right',
      }}
    >
      <Stack.Screen name="(tabs)" />
      {/* Presented from the bottom: a sheet-like screen for a single decision,
          which is what both of these are. */}
      <Stack.Screen name="payout-request" options={{ animation: 'slide_from_bottom' }} />
      <Stack.Screen name="appearance" options={{ animation: 'slide_from_bottom' }} />
    </Stack>
  );
}
