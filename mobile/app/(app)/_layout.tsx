import { Redirect, Stack } from 'expo-router';

import { useSessionStore } from '@/state/session';
import { colors } from '@/theme/tokens';

export default function AppLayout() {
  const status = useSessionStore((state) => state.status);

  // The client-side guard is for the experience only. Every endpoint behind it is
  // enforced server-side, so reaching this screen without a session shows nothing.
  if (status === 'anonymous') return <Redirect href="/welcome" />;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.ground },
      }}
    />
  );
}
