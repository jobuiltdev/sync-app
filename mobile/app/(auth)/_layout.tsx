import { Redirect, Stack } from 'expo-router';

import { useSessionStore } from '@/state/session';
import { usePalette } from '@/theme/theme';

export default function AuthLayout() {
  const status = useSessionStore((state) => state.status);
  const palette = usePalette();

  // Someone already signed in has no business on the sign-in screens, and landing
  // here from a deep link or the back gesture should bounce them home.
  if (status === 'authenticated') return <Redirect href="/home" />;

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: palette.ground },
        animation: 'slide_from_right',
      }}
    />
  );
}
