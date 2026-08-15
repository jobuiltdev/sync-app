import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useRouter } from 'expo-router';
import { Controller, useForm } from 'react-hook-form';
import { StyleSheet, View } from 'react-native';
import { z } from 'zod';

import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Header } from '@/components/ui/Header';
import { Screen } from '@/components/ui/Screen';
import { InlineError } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { toFormErrors } from '@/features/auth/form-errors';
import { useLogin } from '@/features/auth/hooks';
import { usePalette } from '@/theme/theme';
import { spacing } from '@/theme/tokens';

const schema = z.object({
  email: z.email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
});

type FormValues = z.infer<typeof schema>;

export default function LoginScreen() {
  const router = useRouter();
  const palette = usePalette();
  const { mutate, isPending, error } = useLogin();
  const { control, handleSubmit } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: '', password: '' },
  });

  const apiErrors = toFormErrors(error);

  return (
    <Screen>
      <Header onBack={() => router.back()} />

      <View style={styles.head}>
        <Text variant="title1" accessibilityRole="header">
          Welcome back
        </Text>
        <Text variant="body" tone="muted">
          Sign in to continue.
        </Text>
      </View>

      {apiErrors.message ? <InlineError error={error} /> : null}

      <View style={styles.form}>
        <Controller
          control={control}
          name="email"
          render={({ field, fieldState }) => (
            <Field
              label="Email"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message ?? apiErrors.fields.email}
              autoCapitalize="none"
              autoComplete="email"
              keyboardType="email-address"
              textContentType="emailAddress"
              placeholder="you@example.com"
            />
          )}
        />

        <Controller
          control={control}
          name="password"
          render={({ field, fieldState }) => (
            <Field
              label="Password"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message ?? apiErrors.fields.password}
              secureTextEntry
              autoComplete="current-password"
              textContentType="password"
              placeholder="Your password"
            />
          )}
        />

        <Button
          label="Sign in"
          loading={isPending}
          onPress={handleSubmit((values) => mutate(values))}
        />
      </View>

      <Text variant="footnote" tone="muted" center>
        New to Sync?{' '}
        <Link href="/register" style={{ color: palette.primary, fontWeight: '600' }}>
          Create an account
        </Link>
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  head: { gap: spacing.xs },
  form: { gap: spacing.lg },
});
